#define _GNU_SOURCE

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl31.h>
#include <gbm.h>

#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef EGL_OPENGL_ES3_BIT
#define EGL_OPENGL_ES3_BIT 0x0040
#endif

struct kernel_desc {
    const char *name;
    const char *source;
    uint32_t groups_x;
    uint32_t groups_y;
    uint32_t groups_z;
    double ops;
    size_t bytes_moved;
};

struct stats {
    uint64_t min;
    uint64_t max;
    uint64_t total;
};

static const char *gemm_shader =
    "#version 310 es\n"
    "precision highp float;\n"
    "layout(local_size_x = 8, local_size_y = 8) in;\n"
    "layout(std430, binding = 0) readonly buffer ABuffer { float a[]; };\n"
    "layout(std430, binding = 1) readonly buffer BBuffer { float b[]; };\n"
    "layout(std430, binding = 2) writeonly buffer CBuffer { float c[]; };\n"
    "uniform uint u_n;\n"
    "void main() {\n"
    "    uint row = gl_GlobalInvocationID.y;\n"
    "    uint col = gl_GlobalInvocationID.x;\n"
    "    if (row >= u_n || col >= u_n)\n"
    "        return;\n"
    "    float sum = 0.0;\n"
    "    for (uint i = 0u; i < u_n; ++i)\n"
    "        sum += a[row * u_n + i] * b[i * u_n + col];\n"
    "    c[row * u_n + col] = sum;\n"
    "}\n";

static const char *conv2d_shader =
    "#version 310 es\n"
    "layout(local_size_x = 8, local_size_y = 8) in;\n"
    "layout(std430, binding = 0) readonly buffer InputBuffer { float x[]; };\n"
    "layout(std430, binding = 1) readonly buffer WeightBuffer { float w[]; };\n"
    "layout(std430, binding = 2) writeonly buffer OutputBuffer { float y[]; };\n"
    "uniform uint u_width;\n"
    "uniform uint u_height;\n"
    "uniform uint u_channels;\n"
    "void main() {\n"
    "    int ox = int(gl_GlobalInvocationID.x);\n"
    "    int oy = int(gl_GlobalInvocationID.y);\n"
    "    uint oc = gl_GlobalInvocationID.z;\n"
    "    if (ox >= int(u_width) || oy >= int(u_height))\n"
    "        return;\n"
    "    float sum = 0.0;\n"
    "    for (uint ic = 0u; ic < u_channels; ++ic) {\n"
    "        for (int ky = 0; ky < 3; ++ky) {\n"
    "            for (int kx = 0; kx < 3; ++kx) {\n"
    "                int ix = ox + kx - 1;\n"
    "                int iy = oy + ky - 1;\n"
    "                if (ix < 0 || iy < 0 || ix >= int(u_width) || iy >= int(u_height))\n"
    "                    continue;\n"
    "                uint ii = (uint(iy) * u_width + uint(ix)) * u_channels + ic;\n"
    "                uint wi = ((oc * u_channels + ic) * 3u + uint(ky)) * 3u + uint(kx);\n"
    "                sum += x[ii] * w[wi];\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    y[(uint(oy) * u_width + uint(ox)) * u_channels + oc] = sum;\n"
    "}\n";

static const char *depthwise_shader =
    "#version 310 es\n"
    "layout(local_size_x = 8, local_size_y = 8) in;\n"
    "layout(std430, binding = 0) readonly buffer InputBuffer { float x[]; };\n"
    "layout(std430, binding = 1) readonly buffer WeightBuffer { float w[]; };\n"
    "layout(std430, binding = 2) writeonly buffer OutputBuffer { float y[]; };\n"
    "uniform uint u_width;\n"
    "uniform uint u_height;\n"
    "uniform uint u_channels;\n"
    "void main() {\n"
    "    int ox = int(gl_GlobalInvocationID.x);\n"
    "    int oy = int(gl_GlobalInvocationID.y);\n"
    "    uint c = gl_GlobalInvocationID.z;\n"
    "    if (ox >= int(u_width) || oy >= int(u_height))\n"
    "        return;\n"
    "    float sum = 0.0;\n"
    "    for (int ky = 0; ky < 3; ++ky) {\n"
    "        for (int kx = 0; kx < 3; ++kx) {\n"
    "            int ix = ox + kx - 1;\n"
    "            int iy = oy + ky - 1;\n"
    "            if (ix < 0 || iy < 0 || ix >= int(u_width) || iy >= int(u_height))\n"
    "                continue;\n"
    "            uint ii = (uint(iy) * u_width + uint(ix)) * u_channels + c;\n"
    "            uint wi = c * 9u + uint(ky) * 3u + uint(kx);\n"
    "            sum += x[ii] * w[wi];\n"
    "        }\n"
    "    }\n"
    "    y[(uint(oy) * u_width + uint(ox)) * u_channels + c] = sum;\n"
    "}\n";

static const char *reduction_shader =
    "#version 310 es\n"
    "precision highp float;\n"
    "layout(local_size_x = 64) in;\n"
    "layout(std430, binding = 0) readonly buffer InputBuffer { float x[]; };\n"
    "layout(std430, binding = 1) writeonly buffer OutputBuffer { float y[]; };\n"
    "uniform uint u_count;\n"
    "void main() {\n"
    "    uint begin = gl_GlobalInvocationID.x * 256u;\n"
    "    float sum = 0.0;\n"
    "    for (uint offset = 0u; offset < 256u; ++offset) {\n"
    "        uint i = begin + offset;\n"
    "        if (i < u_count)\n"
    "            sum += x[i];\n"
    "    }\n"
    "    y[gl_GlobalInvocationID.x] = sum;\n"
    "}\n";

static const char *softmax_shader =
    "#version 310 es\n"
    "precision highp float;\n"
    "layout(local_size_x = 64) in;\n"
    "layout(std430, binding = 0) readonly buffer InputBuffer { float x[]; };\n"
    "layout(std430, binding = 1) writeonly buffer OutputBuffer { float y[]; };\n"
    "void main() {\n"
    "    uint row = gl_GlobalInvocationID.x;\n"
    "    float maximum = -1e30;\n"
    "    for (uint lane = 0u; lane < 256u; ++lane) {\n"
    "        maximum = max(maximum, x[row * 256u + lane]);\n"
    "    }\n"
    "    float denominator = 0.0;\n"
    "    for (uint lane = 0u; lane < 256u; ++lane) {\n"
    "        denominator += exp(x[row * 256u + lane] - maximum);\n"
    "    }\n"
    "    for (uint lane = 0u; lane < 256u; ++lane)\n"
    "        y[row * 256u + lane] = exp(x[row * 256u + lane] - maximum) / denominator;\n"
    "}\n";

static const char *attention_shader =
    "#version 310 es\n"
    "#define ATTENTION_SEQ %uu\n"
    "precision highp float;\n"
    "layout(local_size_x = 64) in;\n"
    "layout(std430, binding = 0) readonly buffer QBuffer { float q[]; };\n"
    "layout(std430, binding = 1) readonly buffer KBuffer { float k[]; };\n"
    "layout(std430, binding = 2) readonly buffer VBuffer { float v[]; };\n"
    "layout(std430, binding = 3) writeonly buffer OBuffer { float o[]; };\n"
    "void main() {\n"
    "    uint row = gl_GlobalInvocationID.x;\n"
    "    float maximum = -1e30;\n"
    "    for (uint j = 0u; j < ATTENTION_SEQ; ++j) {\n"
    "        float dot = 0.0;\n"
    "        for (uint e = 0u; e < 64u; ++e)\n"
    "            dot += q[row * 64u + e] * k[j * 64u + e];\n"
    "        dot /= 8.0;\n"
    "        maximum = max(maximum, dot);\n"
    "    }\n"
    "    float denominator = 0.0;\n"
    "    for (uint j = 0u; j < ATTENTION_SEQ; ++j) {\n"
    "        float dot = 0.0;\n"
    "        for (uint e = 0u; e < 64u; ++e)\n"
    "            dot += q[row * 64u + e] * k[j * 64u + e];\n"
    "        dot /= 8.0;\n"
    "        denominator += exp(dot - maximum);\n"
    "    }\n"
    "    for (uint d = 0u; d < 64u; ++d) {\n"
    "        float result = 0.0;\n"
    "        for (uint j = 0u; j < ATTENTION_SEQ; ++j)\n"
    "        {\n"
    "            float dot = 0.0;\n"
    "            for (uint e = 0u; e < 64u; ++e)\n"
    "                dot += q[row * 64u + e] * k[j * 64u + e];\n"
    "            dot /= 8.0;\n"
    "            result += exp(dot - maximum) / denominator * v[j * 64u + d];\n"
    "        }\n"
    "        o[row * 64u + d] = result;\n"
    "    }\n"
    "}\n";

static uint64_t now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ull + (uint64_t)ts.tv_nsec / 1000ull;
}

static void stats_init(struct stats *s)
{
    s->min = UINT64_MAX;
    s->max = 0;
    s->total = 0;
}

static void stats_add(struct stats *s, uint64_t value)
{
    if (value < s->min)
        s->min = value;
    if (value > s->max)
        s->max = value;
    s->total += value;
}

static int open_drm(char *path, size_t len)
{
    static const char *candidates[] = {
        "/dev/dri/renderD128", "/dev/dri/card0", "/dev/dri/card1", NULL
    };
    for (unsigned i = 0; candidates[i]; ++i) {
        int fd = open(candidates[i], O_RDWR | O_CLOEXEC);
        if (fd >= 0) {
            snprintf(path, len, "%s", candidates[i]);
            return fd;
        }
    }
    return -1;
}

static int check_gl(const char *what)
{
    GLenum err = glGetError();
    if (err == GL_NO_ERROR)
        return 0;
    fprintf(stderr, "%s: GL error 0x%04x\n", what, err);
    return -1;
}

static GLuint make_program(const char *source)
{
    GLuint shader = glCreateShader(GL_COMPUTE_SHADER);
    GLuint program = 0;
    GLint ok = GL_FALSE;
    char log[4096];
    GLsizei len = 0;

    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        glGetShaderInfoLog(shader, sizeof(log), &len, log);
        fprintf(stderr, "ML shader compile failed:\n%.*s\n", (int)len, log);
        glDeleteShader(shader);
        return 0;
    }
    program = glCreateProgram();
    glAttachShader(program, shader);
    glLinkProgram(program);
    glGetProgramiv(program, GL_LINK_STATUS, &ok);
    glDeleteShader(shader);
    if (!ok) {
        glGetProgramInfoLog(program, sizeof(log), &len, log);
        fprintf(stderr, "ML program link failed:\n%.*s\n", (int)len, log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

static GLuint make_ssbo(const void *data, size_t bytes)
{
    GLuint buffer = 0;
    glGenBuffers(1, &buffer);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffer);
    glBufferData(GL_SHADER_STORAGE_BUFFER, (GLsizeiptr)bytes, data, GL_DYNAMIC_COPY);
    if (check_gl("glBufferData")) {
        glDeleteBuffers(1, &buffer);
        return 0;
    }
    return buffer;
}

static const float *map_ssbo(GLuint buffer, size_t bytes)
{
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffer);
    return (const float *)glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0,
                                           (GLsizeiptr)bytes, GL_MAP_READ_BIT);
}

static void unmap_ssbo(GLuint buffer)
{
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, buffer);
    glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
}

static int close_enough(float got, float expected, double tolerance)
{
    double diff = fabs((double)got - (double)expected);
    double scale = fabs((double)expected) > 1.0 ? fabs((double)expected) : 1.0;
    return diff <= tolerance * scale;
}

static float source_value(unsigned index)
{
    return (float)((int)(index % 251u) - 125) / 64.0f;
}

static unsigned gemm_size = 512u;
static unsigned attention_size = 256u;

static void debug_output(const char *what, const float *values, unsigned count)
{
    unsigned finite_values = 0;
    unsigned nonzero_values = 0;
    unsigned show = count < 8u ? count : 8u;

    for (unsigned i = 0; i < count; ++i) {
        if (isfinite(values[i]))
            ++finite_values;
        if (values[i] != 0.0f)
            ++nonzero_values;
    }
    fprintf(stderr, "%s debug finite=%u/%u nonzero=%u first=", what,
            finite_values, count, nonzero_values);
    for (unsigned i = 0; i < show; ++i)
        fprintf(stderr, "%s%g", i ? " " : "", values[i]);
    fputc('\n', stderr);
}

static int validate_gemm(const float *c)
{
    const unsigned n = gemm_size, k = gemm_size;
    for (unsigned sample = 0; sample < 4; ++sample) {
        unsigned row = sample * 137u % n;
        unsigned col = sample * 209u % n;
        float expected = 0.0f;
        for (unsigned i = 0; i < k; ++i)
            expected += source_value(row * k + i) * source_value(i * n + col);
        if (!close_enough(c[row * n + col], expected, 2e-4)) {
            debug_output("GEMM", c, n * n);
            fprintf(stderr, "GEMM mismatch row=%u col=%u got=%f expected=%f\n",
                    row, col, c[row * n + col], expected);
            return -1;
        }
    }
    return 0;
}

static int validate_conv(const float *y)
{
    const unsigned w = 64u, h = 64u, c = 32u;
    unsigned ox = 13u, oy = 29u, oc = 17u;
    float expected = 0.0f;
    for (unsigned ic = 0; ic < c; ++ic)
        for (unsigned ky = 0; ky < 3; ++ky)
            for (unsigned kx = 0; kx < 3; ++kx) {
                int ix = (int)ox + (int)kx - 1;
                int iy = (int)oy + (int)ky - 1;
                if (ix < 0 || iy < 0 || ix >= (int)w || iy >= (int)h)
                    continue;
                unsigned ii = ((unsigned)iy * w + (unsigned)ix) * c + ic;
                unsigned wi = ((oc * c + ic) * 3u + ky) * 3u + kx;
                expected += source_value(ii) * source_value(1000000u + wi);
            }
    unsigned oi = (oy * w + ox) * c + oc;
    if (!close_enough(y[oi], expected, 2e-4)) {
        fprintf(stderr, "Conv2D mismatch got=%f expected=%f\n", y[oi], expected);
        return -1;
    }
    return 0;
}

static int validate_depthwise(const float *y)
{
    const unsigned w = 128u, h = 128u, c = 128u;
    unsigned ox = 67u, oy = 31u, channel = 93u;
    float expected = 0.0f;
    for (unsigned ky = 0; ky < 3; ++ky)
        for (unsigned kx = 0; kx < 3; ++kx) {
            int ix = (int)ox + (int)kx - 1;
            int iy = (int)oy + (int)ky - 1;
            if (ix < 0 || iy < 0 || ix >= (int)w || iy >= (int)h)
                continue;
            unsigned ii = ((unsigned)iy * w + (unsigned)ix) * c + channel;
            unsigned wi = channel * 9u + ky * 3u + kx;
            expected += source_value(ii) * source_value(2000000u + wi);
        }
    unsigned oi = (oy * w + ox) * c + channel;
    if (!close_enough(y[oi], expected, 2e-4)) {
        fprintf(stderr, "Depthwise mismatch got=%f expected=%f\n", y[oi], expected);
        return -1;
    }
    return 0;
}

static int validate_reduction(const float *partials)
{
    const unsigned count = 8u * 1024u * 1024u;
    double total = 0.0;
    for (unsigned g = 0; g < count / 256u; ++g)
        total += partials[g];
    double expected = 0.0;
    for (unsigned i = 0; i < count; ++i)
        expected += source_value(i);
    if (!close_enough((float)total, (float)expected, 2e-4)) {
        debug_output("Reduction", partials, count / 256u);
        fprintf(stderr, "Reduction mismatch got=%f expected=%f\n", (float)total, (float)expected);
        return -1;
    }
    return 0;
}

static int validate_softmax(const float *x)
{
    unsigned row = 37u;
    float values[256], maximum = -1e30f, denominator = 0.0f;
    for (unsigned i = 0; i < 256; ++i) {
        values[i] = source_value(row * 256u + i);
        if (values[i] > maximum)
            maximum = values[i];
    }
    for (unsigned i = 0; i < 256; ++i) {
        values[i] = expf(values[i] - maximum);
        denominator += values[i];
    }
    for (unsigned i = 0; i < 256; i += 64) {
        float expected = values[i] / denominator;
        if (!close_enough(x[row * 256u + i], expected, 3e-4)) {
            debug_output("Softmax", x + row * 256u, 256u);
            fprintf(stderr, "Softmax mismatch lane=%u got=%f expected=%f\n",
                    i, x[row * 256u + i], expected);
            return -1;
        }
    }
    return 0;
}

static int validate_attention(const float *o)
{
    const unsigned row = 73u;
    float scores[1024], maximum = -1e30f, denominator = 0.0f;
    for (unsigned j = 0; j < attention_size; ++j) {
        float dot = 0.0f;
        for (unsigned e = 0; e < 64; ++e)
            dot += source_value(row * 64u + e) * source_value(3000000u + j * 64u + e);
        scores[j] = dot / 8.0f;
        if (scores[j] > maximum)
            maximum = scores[j];
    }
    for (unsigned j = 0; j < attention_size; ++j) {
        scores[j] = expf(scores[j] - maximum);
        denominator += scores[j];
    }
    for (unsigned d = 0; d < 64; d += 16) {
        float expected = 0.0f;
        for (unsigned j = 0; j < attention_size; ++j)
            expected += scores[j] / denominator * source_value(4000000u + j * 64u + d);
        if (!close_enough(o[row * 64u + d], expected, 3e-4)) {
            debug_output("Attention", o + row * 64u, 64u);
            fprintf(stderr, "Attention mismatch d=%u got=%f expected=%f\n",
                    d, o[row * 64u + d], expected);
            return -1;
        }
    }
    return 0;
}

struct egl_state {
    int fd;
    struct gbm_device *gbm;
    EGLDisplay display;
    EGLContext context;
    EGLSurface surface;
};

static int setup_egl(struct egl_state *state, const char *requested_node)
{
    char node[64];
    EGLint major = 0, minor = 0, configs = 0;
    EGLConfig config = NULL;
    PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform_display =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    const EGLint config_attrs[] = {
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_NONE
    };
    const EGLint fallback_attrs[] = {
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
        EGL_NONE
    };
    const EGLint context_attrs[] = {
        EGL_CONTEXT_CLIENT_VERSION, 3,
        EGL_NONE
    };

    memset(state, 0, sizeof(*state));
    if (requested_node) {
        snprintf(node, sizeof(node), "%s", requested_node);
        state->fd = open(node, O_RDWR | O_CLOEXEC);
    } else {
        state->fd = open_drm(node, sizeof(node));
    }
    if (state->fd < 0) {
        fprintf(stderr, "open DRM node failed: %s\n", strerror(errno));
        return -1;
    }
    printf("DRM_NODE=%s\n", node);
    state->gbm = gbm_create_device(state->fd);
    if (!state->gbm) {
        fprintf(stderr, "gbm_create_device failed\n");
        return -1;
    }
    printf("GBM_BACKEND=%s\n", gbm_device_get_backend_name(state->gbm));
    if (get_platform_display)
        state->display = get_platform_display(EGL_PLATFORM_GBM_MESA, state->gbm, NULL);
    if (!state->display)
        state->display = eglGetDisplay((EGLNativeDisplayType)state->gbm);
    if (!eglInitialize(state->display, &major, &minor)) {
        fprintf(stderr, "eglInitialize failed: 0x%04x\n", eglGetError());
        return -1;
    }
    if (!eglBindAPI(EGL_OPENGL_ES_API) ||
        !eglChooseConfig(state->display, config_attrs, &config, 1, &configs) ||
        configs < 1) {
        if (!eglChooseConfig(state->display, fallback_attrs, &config, 1, &configs) ||
            configs < 1) {
        fprintf(stderr, "EGL configuration failed: 0x%04x\n", eglGetError());
        return -1;
    }
    }
    state->context = eglCreateContext(state->display, config, EGL_NO_CONTEXT, context_attrs);
    if (state->context == EGL_NO_CONTEXT) {
        fprintf(stderr, "eglCreateContext failed: 0x%04x\n", eglGetError());
        return -1;
    }
    if (!eglMakeCurrent(state->display, EGL_NO_SURFACE, EGL_NO_SURFACE, state->context)) {
        fprintf(stderr, "eglMakeCurrent failed: 0x%04x\n", eglGetError());
        return -1;
    }
    printf("EGL_VERSION=%d.%d\n", major, minor);
    printf("GL_VENDOR=%s\n", glGetString(GL_VENDOR));
    printf("GL_RENDERER=%s\n", glGetString(GL_RENDERER));
    printf("GL_VERSION=%s\n", glGetString(GL_VERSION));
    {
        GLint value = 0;
        glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS, &value);
        printf("ML_LIMIT_MAX_COMPUTE_WORK_GROUP_INVOCATIONS=%d\n", value);
        glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT, 0, &value);
        printf("ML_LIMIT_MAX_COMPUTE_WORK_GROUP_COUNT_X=%d\n", value);
        glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT, 1, &value);
        printf("ML_LIMIT_MAX_COMPUTE_WORK_GROUP_COUNT_Y=%d\n", value);
        glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT, 2, &value);
        printf("ML_LIMIT_MAX_COMPUTE_WORK_GROUP_COUNT_Z=%d\n", value);
        glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE, 0, &value);
        printf("ML_LIMIT_MAX_COMPUTE_WORK_GROUP_SIZE_X=%d\n", value);
        glGetIntegerv(GL_MAX_COMPUTE_SHADER_STORAGE_BLOCKS, &value);
        printf("ML_LIMIT_MAX_COMPUTE_SSBO_BLOCKS=%d\n", value);
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    if (!renderer || strstr(renderer, "llvmpipe") || strstr(renderer, "softpipe") ||
        strstr(renderer, "Software Rasterizer")) {
        fprintf(stderr, "software renderer detected\n");
        return -1;
    }
    return 0;
}

static void teardown_egl(struct egl_state *state)
{
    if (state->display) {
        eglMakeCurrent(state->display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (state->context)
            eglDestroyContext(state->display, state->context);
        if (state->surface)
            eglDestroySurface(state->display, state->surface);
        eglTerminate(state->display);
    }
    if (state->gbm)
        gbm_device_destroy(state->gbm);
    if (state->fd >= 0)
        close(state->fd);
}

static int parse_uint(const char *value, unsigned *out)
{
    char *end = NULL;
    errno = 0;
    unsigned long parsed = strtoul(value, &end, 0);
    if (errno || !end || *end || parsed > UINT32_MAX)
        return -1;
    *out = (unsigned)parsed;
    return 0;
}

static int run_shader(const struct kernel_desc *kernel, GLuint program, GLuint *buffers,
                      unsigned buffer_count, size_t output_bytes,
                      int (*validate)(const float *), unsigned iterations,
                      unsigned warmup, double *avg_us_out)
{
    struct stats timing;
    uint64_t setup_start = now_us();
    uint64_t setup_done;
    int failed = 0;
    const float *output;

    stats_init(&timing);
    for (unsigned i = 0; i < buffer_count; ++i)
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, i, buffers[i]);
    setup_done = now_us();
    glUseProgram(program);
    if (check_gl("ML bind buffers"))
        return -1;
    for (unsigned i = 0; i < buffer_count; ++i) {
        GLint bound = 0;
        glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING, (GLenum)i, &bound);
        printf("ML_DEBUG_SSBO binding=%u buffer=%u\n", i, (unsigned)bound);
    }

    for (unsigned iter = 0; iter < warmup + iterations; ++iter) {
        uint64_t start = now_us();
        glDispatchCompute(kernel->groups_x, kernel->groups_y, kernel->groups_z);
        if (check_gl("glDispatchCompute"))
            return -1;
        glMemoryBarrier(GL_ALL_BARRIER_BITS);
        /* Panfrost/Mesa does not make a read-only SSBO map here reliably wait
         * for all compute shaders. Finish explicitly before correctness readback. */
        glFinish();
        output = map_ssbo(buffers[buffer_count - 1], output_bytes);
        if (!output) {
            fprintf(stderr, "%s: output map failed\n", kernel->name);
            return -1;
        }
        if (iter + 1 == warmup + iterations && validate && validate(output))
            failed = -1;
        unmap_ssbo(buffers[buffer_count - 1]);
        if (failed)
            return -1;
        if (iter >= warmup)
            stats_add(&timing, now_us() - start);
    }

    *avg_us_out = (double)timing.total / (double)iterations;
    printf("ML_KERNEL=%s\n", kernel->name);
    printf("ML_CHECK=PASS samples=%u warmup=%u\n", iterations, warmup);
    printf("ML_ITER_US min=%llu avg=%.2f max=%llu total=%llu\n",
           (unsigned long long)timing.min, *avg_us_out,
           (unsigned long long)timing.max, (unsigned long long)timing.total);
    printf("ML_PHASE_US name=dispatch_barrier_map min=%llu avg=%.2f max=%llu total=%llu\n",
           (unsigned long long)timing.min, *avg_us_out,
           (unsigned long long)timing.max, (unsigned long long)timing.total);
    printf("ML_PHASE_US name=buffer_bind total=%llu\n",
           (unsigned long long)(setup_done - setup_start));
    printf("ML_WORK_OPS=%.0f\n", kernel->ops);
    printf("ML_BYTES_MOVED=%zu\n", kernel->bytes_moved);
    printf("ML_OPS_PER_SEC=%.2f\n", kernel->ops / (*avg_us_out / 1000000.0));
    fflush(stdout);
    return 0;
}

static int run_gemm(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned n = gemm_size, k = gemm_size;
    const size_t count = (size_t)n * n;
    static char gemm_name[64];
    float *a = malloc(count * sizeof(float));
    float *b = malloc(count * sizeof(float));
    float *c = calloc(count, sizeof(float));
    GLuint buffers[3] = {0};
    GLuint program = 0;
    GLint n_loc;
    int rc;
    struct kernel_desc desc = {
        .name = gemm_name,
        /* Use the global-ID addressing model of the verified conv kernels. */
        .groups_x = (n + 7u) / 8u,
        .groups_y = (n + 7u) / 8u,
        .groups_z = 1u,
        .ops = 2.0 * n * n * k,
        .bytes_moved = count * sizeof(float) * 3,
    };
    snprintf(gemm_name, sizeof(gemm_name), "gemm_%u_fp32", n);
    if (!a || !b || !c)
        goto fail;
    for (size_t i = 0; i < count; ++i) {
        a[i] = source_value((unsigned)i);
        b[i] = source_value((unsigned)i);
    }
    program = make_program(gemm_shader);
    if (!program)
        goto fail;
    buffers[0] = make_ssbo(a, count * sizeof(float));
    buffers[1] = make_ssbo(b, count * sizeof(float));
    buffers[2] = make_ssbo(c, count * sizeof(float));
    if (!buffers[0] || !buffers[1] || !buffers[2])
        goto fail;
    n_loc = glGetUniformLocation(program, "u_n");
    glUseProgram(program);
    {
        GLuint value = 0;
        printf("ML_DEBUG_UNIFORM n_loc=%d", n_loc);
        if (n_loc >= 0) { glUniform1ui(n_loc, n); glGetUniformuiv(program, n_loc, &value); printf(" n=%u", value); }
        putchar('\n');
    }
    (void)k;
    rc = run_shader(&desc, program, buffers, 3, count * sizeof(float), validate_gemm,
                    iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(a); free(b); free(c);
    glDeleteBuffers(3, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

static int run_conv(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned w = 64u, h = 64u, c = 32u;
    const size_t input_count = (size_t)w * h * c;
    const size_t output_count = input_count;
    const size_t weight_count = (size_t)c * c * 3u * 3u;
    float *input = malloc(input_count * sizeof(float));
    float *weight = malloc(weight_count * sizeof(float));
    float *output = calloc(output_count, sizeof(float));
    GLuint buffers[3] = {0}, program = 0;
    GLint width_loc, height_loc, channel_loc;
    int rc;
    struct kernel_desc desc = {
        .name = "conv2d_64x64x32_3x3_fp32",
        .groups_x = (w + 7u) / 8u,
        .groups_y = (h + 7u) / 8u,
        .groups_z = c,
        .ops = 2.0 * w * h * c * c * 9.0,
        .bytes_moved = (input_count + weight_count + output_count) * sizeof(float),
    };
    if (!input || !weight || !output)
        goto fail;
    for (size_t i = 0; i < input_count; ++i) input[i] = source_value((unsigned)i);
    for (size_t i = 0; i < weight_count; ++i) weight[i] = source_value(1000000u + (unsigned)i);
    program = make_program(conv2d_shader);
    if (!program) goto fail;
    buffers[0] = make_ssbo(input, input_count * sizeof(float));
    buffers[1] = make_ssbo(weight, weight_count * sizeof(float));
    buffers[2] = make_ssbo(output, output_count * sizeof(float));
    if (!buffers[0] || !buffers[1] || !buffers[2]) goto fail;
    width_loc = glGetUniformLocation(program, "u_width");
    height_loc = glGetUniformLocation(program, "u_height");
    channel_loc = glGetUniformLocation(program, "u_channels");
    glUseProgram(program);
    glUniform1ui(width_loc, w);
    glUniform1ui(height_loc, h);
    glUniform1ui(channel_loc, c);
    rc = run_shader(&desc, program, buffers, 3, output_count * sizeof(float), validate_conv,
                    iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(input); free(weight); free(output);
    glDeleteBuffers(3, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

static int run_depthwise(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned w = 128u, h = 128u, c = 128u;
    const size_t input_count = (size_t)w * h * c;
    const size_t weight_count = c * 9u;
    float *input = malloc(input_count * sizeof(float));
    float *weight = malloc(weight_count * sizeof(float));
    float *output = calloc(input_count, sizeof(float));
    GLuint buffers[3] = {0}, program = 0;
    GLint width_loc, height_loc, channel_loc;
    int rc;
    struct kernel_desc desc = {
        .name = "depthwise_conv_128x128x128_3x3_fp32",
        .groups_x = (w + 7u) / 8u,
        .groups_y = (h + 7u) / 8u,
        .groups_z = c,
        .ops = 2.0 * w * h * c * 9.0,
        .bytes_moved = (input_count * 2u + weight_count) * sizeof(float),
    };
    if (!input || !weight || !output) goto fail;
    for (size_t i = 0; i < input_count; ++i) input[i] = source_value((unsigned)i);
    for (size_t i = 0; i < weight_count; ++i) weight[i] = source_value(2000000u + (unsigned)i);
    program = make_program(depthwise_shader);
    if (!program) goto fail;
    buffers[0] = make_ssbo(input, input_count * sizeof(float));
    buffers[1] = make_ssbo(weight, weight_count * sizeof(float));
    buffers[2] = make_ssbo(output, input_count * sizeof(float));
    if (!buffers[0] || !buffers[1] || !buffers[2]) goto fail;
    width_loc = glGetUniformLocation(program, "u_width");
    height_loc = glGetUniformLocation(program, "u_height");
    channel_loc = glGetUniformLocation(program, "u_channels");
    glUseProgram(program);
    glUniform1ui(width_loc, w);
    glUniform1ui(height_loc, h);
    glUniform1ui(channel_loc, c);
    rc = run_shader(&desc, program, buffers, 3, input_count * sizeof(float), validate_depthwise,
                    iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(input); free(weight); free(output);
    glDeleteBuffers(3, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

static int run_reduction(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned count = 8u * 1024u * 1024u;
    const unsigned groups = count / 256u;
    float *input = malloc((size_t)count * sizeof(float));
    float *output = calloc(groups, sizeof(float));
    GLuint buffers[2] = {0}, program = 0;
    GLint count_loc;
    int rc;
    struct kernel_desc desc = {
        .name = "block_reduction_32mib_fp32",
        /* Mali/Panfrost did not execute writes from the original one-invocation
         * workgroups.  Keep one output per invocation, but pack outputs into
         * 64-invocation workgroups. */
        .groups_x = (groups + 63u) / 64u,
        .groups_y = 1u,
        .groups_z = 1u,
        .ops = count,
        .bytes_moved = (size_t)(count + groups) * sizeof(float),
    };
    if (!input || !output) goto fail;
    for (unsigned i = 0; i < count; ++i) input[i] = source_value(i);
    program = make_program(reduction_shader);
    if (!program) goto fail;
    buffers[0] = make_ssbo(input, (size_t)count * sizeof(float));
    buffers[1] = make_ssbo(output, (size_t)groups * sizeof(float));
    if (!buffers[0] || !buffers[1]) goto fail;
    count_loc = glGetUniformLocation(program, "u_count");
    glUseProgram(program);
    glUniform1ui(count_loc, count);
    rc = run_shader(&desc, program, buffers, 2, (size_t)groups * sizeof(float),
                    validate_reduction, iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(input); free(output);
    glDeleteBuffers(2, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

static int run_softmax(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned rows = 16384u, lanes = 256u;
    const size_t count = (size_t)rows * lanes;
    float *data = malloc(count * sizeof(float));
    float *output = calloc(count, sizeof(float));
    GLuint buffers[2] = {0}, program = 0;
    int rc;
    struct kernel_desc desc = {
        .name = "row_softmax_16384x256_fp32",
        .groups_x = (rows + 63u) / 64u,
        .groups_y = 1u,
        .groups_z = 1u,
        .ops = lanes * 5.0 * rows,
        .bytes_moved = count * sizeof(float) * 2u,
    };
    if (!data || !output) goto fail;
    for (size_t i = 0; i < count; ++i) data[i] = source_value((unsigned)i);
    program = make_program(softmax_shader);
    if (!program) goto fail;
    buffers[0] = make_ssbo(data, count * sizeof(float));
    buffers[1] = make_ssbo(output, count * sizeof(float));
    if (!buffers[0] || !buffers[1]) goto fail;
    rc = run_shader(&desc, program, buffers, 2, count * sizeof(float), validate_softmax,
                    iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(data); free(output);
    glDeleteBuffers(2, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

static int run_attention(unsigned iterations, unsigned warmup, double *avg)
{
    const unsigned seq = attention_size, dim = 64u;
    char attention_name[64], shader_source[4096];
    const size_t count = (size_t)seq * dim;
    float *q = malloc(count * sizeof(float));
    float *k = malloc(count * sizeof(float));
    float *v = malloc(count * sizeof(float));
    float *o = calloc(count, sizeof(float));
    GLuint buffers[4] = {0}, program = 0;
    int rc;
    struct kernel_desc desc = {
        .name = attention_name,
        .groups_x = (seq + 63u) / 64u,
        .groups_y = 1u,
        .groups_z = 1u,
        .ops = 2.0 * seq * seq * dim * 2.0 + seq * seq * 3.0,
        .bytes_moved = count * sizeof(float) * 5u,
    };
    snprintf(attention_name, sizeof(attention_name),
             "single_head_attention_%ux64_fp32", seq);
    if (!q || !k || !v || !o) goto fail;
    for (size_t i = 0; i < count; ++i) {
        q[i] = source_value((unsigned)i);
        k[i] = source_value(3000000u + (unsigned)i);
        v[i] = source_value(4000000u + (unsigned)i);
    }
    if (snprintf(shader_source, sizeof(shader_source), attention_shader, seq) >=
        (int)sizeof(shader_source))
        goto fail;
    program = make_program(shader_source);
    if (!program) goto fail;
    buffers[0] = make_ssbo(q, count * sizeof(float));
    buffers[1] = make_ssbo(k, count * sizeof(float));
    buffers[2] = make_ssbo(v, count * sizeof(float));
    buffers[3] = make_ssbo(o, count * sizeof(float));
    if (!buffers[0] || !buffers[1] || !buffers[2] || !buffers[3]) goto fail;
    rc = run_shader(&desc, program, buffers, 4, count * sizeof(float), validate_attention,
                    iterations, warmup, avg);
    goto out;
fail:
    rc = -1;
out:
    free(q); free(k); free(v); free(o);
    glDeleteBuffers(4, buffers);
    if (program) glDeleteProgram(program);
    return rc;
}

int main(int argc, char **argv)
{
    struct egl_state state;
    const char *node = NULL;
    const char *kernel = "all";
    unsigned iterations = 5u, warmup = 1u;
    double avg = 0.0;
    int failed = 0;

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--iterations") && i + 1 < argc) {
            if (parse_uint(argv[++i], &iterations) || !iterations) return 2;
        } else if (!strcmp(argv[i], "--warmup") && i + 1 < argc) {
            if (parse_uint(argv[++i], &warmup)) return 2;
        } else if (!strcmp(argv[i], "--kernel") && i + 1 < argc) {
            kernel = argv[++i];
        } else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
            printf("usage: %s [--iterations N] [--warmup N] [--gemm-size N] [--attention-size N (128..1024, multiple of 64)] [--kernel all|gemm|conv|depthwise|reduction|softmax|attention] [drm-node]\n",
                   argv[0]);
            return 0;
        } else if (!strcmp(argv[i], "--gemm-size") && i + 1 < argc) {
            ++i;
            if (parse_uint(argv[i], &gemm_size) || gemm_size < 8u || gemm_size % 8u)
                return 2;
        } else if (!strcmp(argv[i], "--attention-size") && i + 1 < argc) {
            if (parse_uint(argv[++i], &attention_size) ||
                attention_size < 128u || attention_size > 1024u ||
                attention_size % 64u)
                return 2;
        } else if (!node) {
            node = argv[i];
        } else {
            return 2;
        }
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    if (setup_egl(&state, node))
        return 20;
    printf("ML_CONFIG iterations=%u warmup=%u\n", iterations, warmup);
    printf("ML_HARNESS_VERSION=8\n");
    if (!strcmp(kernel, "all") || !strcmp(kernel, "gemm"))
        failed |= run_gemm(iterations, warmup, &avg);
    if (!strcmp(kernel, "all") || !strcmp(kernel, "conv"))
        failed |= run_conv(iterations, warmup, &avg);
    if (!strcmp(kernel, "all") || !strcmp(kernel, "depthwise"))
        failed |= run_depthwise(iterations, warmup, &avg);
    if (!strcmp(kernel, "all") || !strcmp(kernel, "reduction"))
        failed |= run_reduction(iterations, warmup, &avg);
    if (!strcmp(kernel, "all") || !strcmp(kernel, "softmax"))
        failed |= run_softmax(iterations, warmup, &avg);
    if (!strcmp(kernel, "all") || !strcmp(kernel, "attention"))
        failed |= run_attention(iterations, warmup, &avg);
    if (strcmp(kernel, "all") && strcmp(kernel, "gemm") && strcmp(kernel, "conv") &&
        strcmp(kernel, "depthwise") && strcmp(kernel, "reduction") &&
        strcmp(kernel, "softmax") && strcmp(kernel, "attention")) {
        fprintf(stderr, "unknown kernel: %s\n", kernel);
        return 2;
    }
    printf("ML_RESULT=%s\n", failed ? "FAIL" : "PASS");
    teardown_egl(&state);
    return failed ? 1 : 0;
}
