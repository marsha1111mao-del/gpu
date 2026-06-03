#define _GNU_SOURCE

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl31.h>
#include <gbm.h>

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef EGL_OPENGL_ES3_BIT
#define EGL_OPENGL_ES3_BIT 0x00000040
#endif

static const char *shader_src =
    "#version 310 es\n"
    "layout(local_size_x = 128) in;\n"
    "layout(std430, binding = 0) buffer Data { uint values[]; };\n"
    "uniform uint u_count;\n"
    "uniform uint u_alu_iters;\n"
    "void main() {\n"
    "    uint i = (gl_WorkGroupID.y * gl_NumWorkGroups.x + gl_WorkGroupID.x) * gl_WorkGroupSize.x + gl_LocalInvocationID.x;\n"
    "    if (i >= u_count)\n"
    "        return;\n"
    "    uint v = values[i] * 3u + 7u;\n"
    "    for (uint step = 1u; step < u_alu_iters; step++) {\n"
    "        v = v * 1664525u + 1013904223u;\n"
    "        v ^= v >> 16;\n"
    "        v *= 2246822519u;\n"
    "    }\n"
    "    values[i] = v;\n"
    "}\n";

#define COMPUTE_LOCAL_SIZE_X 128u
#define COMPUTE_DISPATCH_GROUPS_X 32768u

static void stage(const char *name)
{
    printf("STAGE=%s\n", name);
    fflush(stdout);
}

static uint64_t now_us(void)
{
    struct timespec ts;

    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ull + (uint64_t)ts.tv_nsec / 1000ull;
}

struct perf_stats {
    uint64_t min_us;
    uint64_t max_us;
    uint64_t total_us;
};

static void perf_stats_init(struct perf_stats *stats)
{
    stats->min_us = UINT64_MAX;
    stats->max_us = 0;
    stats->total_us = 0;
}

static void perf_stats_add(struct perf_stats *stats, uint64_t value)
{
    if (value < stats->min_us)
        stats->min_us = value;
    if (value > stats->max_us)
        stats->max_us = value;
    stats->total_us += value;
}

static void perf_stats_print(const char *name, const struct perf_stats *stats,
                             unsigned samples)
{
    if (!samples) {
        printf("PERF_PHASE_US name=%s samples=0 min=0 avg=0.00 max=0 total=0\n",
               name);
        return;
    }

    printf("PERF_PHASE_US name=%s samples=%u min=%llu avg=%.2f max=%llu total=%llu\n",
           name, samples,
           (unsigned long long)stats->min_us,
           (double)stats->total_us / (double)samples,
           (unsigned long long)stats->max_us,
           (unsigned long long)stats->total_us);
}

static int parse_uint0_arg(const char *name, const char *value, unsigned *out)
{
    char *end = NULL;
    unsigned long parsed;

    errno = 0;
    parsed = strtoul(value, &end, 0);
    if (errno || !end || *end || parsed > UINT_MAX) {
        fprintf(stderr, "invalid %s: %s\n", name, value);
        return -1;
    }

    *out = (unsigned)parsed;
    return 0;
}

static int parse_uint_arg(const char *name, const char *value, unsigned *out)
{
    char *end = NULL;
    unsigned long parsed;

    errno = 0;
    parsed = strtoul(value, &end, 0);
    if (errno || !end || *end || parsed == 0 || parsed > UINT_MAX) {
        fprintf(stderr, "invalid %s: %s\n", name, value);
        return -1;
    }

    *out = (unsigned)parsed;
	return 0;
}

static void compute_dispatch_dims(unsigned count, unsigned *groups_x,
                                  unsigned *groups_y)
{
    unsigned groups = (count + COMPUTE_LOCAL_SIZE_X - 1) /
                      COMPUTE_LOCAL_SIZE_X;

    *groups_x = groups;
    if (*groups_x > COMPUTE_DISPATCH_GROUPS_X)
        *groups_x = COMPUTE_DISPATCH_GROUPS_X;
    *groups_y = (groups + *groups_x - 1) / *groups_x;
}

static int has_bad_renderer(const char *renderer)
{
    return renderer &&
           (strstr(renderer, "llvmpipe") ||
            strstr(renderer, "softpipe") ||
            strstr(renderer, "Software Rasterizer"));
}

static uint32_t expected_value(uint32_t base, unsigned alu_iters)
{
    uint32_t v = base * 3u + 7u;

    for (unsigned step = 1; step < alu_iters; step++) {
        v = v * 1664525u + 1013904223u;
        v ^= v >> 16;
        v *= 2246822519u;
    }

    return v;
}

static const char *egl_error_name(EGLint err)
{
    switch (err) {
    case EGL_SUCCESS:
        return "EGL_SUCCESS";
    case EGL_NOT_INITIALIZED:
        return "EGL_NOT_INITIALIZED";
    case EGL_BAD_ACCESS:
        return "EGL_BAD_ACCESS";
    case EGL_BAD_ALLOC:
        return "EGL_BAD_ALLOC";
    case EGL_BAD_ATTRIBUTE:
        return "EGL_BAD_ATTRIBUTE";
    case EGL_BAD_CONTEXT:
        return "EGL_BAD_CONTEXT";
    case EGL_BAD_CONFIG:
        return "EGL_BAD_CONFIG";
    case EGL_BAD_CURRENT_SURFACE:
        return "EGL_BAD_CURRENT_SURFACE";
    case EGL_BAD_DISPLAY:
        return "EGL_BAD_DISPLAY";
    case EGL_BAD_SURFACE:
        return "EGL_BAD_SURFACE";
    case EGL_BAD_MATCH:
        return "EGL_BAD_MATCH";
    case EGL_BAD_PARAMETER:
        return "EGL_BAD_PARAMETER";
    case EGL_BAD_NATIVE_PIXMAP:
        return "EGL_BAD_NATIVE_PIXMAP";
    case EGL_BAD_NATIVE_WINDOW:
        return "EGL_BAD_NATIVE_WINDOW";
    case EGL_CONTEXT_LOST:
        return "EGL_CONTEXT_LOST";
    default:
        return "unknown";
    }
}

static void fail_egl(const char *what)
{
    EGLint err = eglGetError();
    fprintf(stderr, "%s failed: 0x%04x (%s)\n", what, err, egl_error_name(err));
}

static int check_gl(const char *what)
{
    GLenum err = glGetError();
    if (err == GL_NO_ERROR)
        return 0;

    fprintf(stderr, "%s: GL error 0x%04x\n", what, err);
    return -1;
}

static int open_default_drm_node(char *path, size_t path_len)
{
    int fd;

    for (int i = 128; i < 144; i++) {
        snprintf(path, path_len, "/dev/dri/renderD%d", i);
        fd = open(path, O_RDWR | O_CLOEXEC);
        if (fd >= 0)
            return fd;
    }

    for (int i = 0; i < 8; i++) {
        snprintf(path, path_len, "/dev/dri/card%d", i);
        fd = open(path, O_RDWR | O_CLOEXEC);
        if (fd >= 0)
            return fd;
    }

    snprintf(path, path_len, "/dev/dri/renderD128");
    return -1;
}

static GLuint compile_shader(void)
{
    GLuint shader = glCreateShader(GL_COMPUTE_SHADER);
    GLint ok = GL_FALSE;

    glShaderSource(shader, 1, &shader_src, NULL);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        GLsizei len = 0;
        glGetShaderInfoLog(shader, sizeof(log), &len, log);
        fprintf(stderr, "compute shader compile failed:\n%.*s\n", (int)len, log);
        glDeleteShader(shader);
        return 0;
    }

    return shader;
}

static GLuint link_program(GLuint shader)
{
    GLuint prog = glCreateProgram();
    GLint ok = GL_FALSE;

    glAttachShader(prog, shader);
    glLinkProgram(prog);
    glGetProgramiv(prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        GLsizei len = 0;
        glGetProgramInfoLog(prog, sizeof(log), &len, log);
        fprintf(stderr, "program link failed:\n%.*s\n", (int)len, log);
        glDeleteProgram(prog);
        return 0;
    }

    return prog;
}

int main(int argc, char **argv)
{
    char path[64];
    const char *requested_path = NULL;
    int fd = -1;
    struct gbm_device *gbm = NULL;
    EGLDisplay dpy = EGL_NO_DISPLAY;
    EGLContext ctx = EGL_NO_CONTEXT;
    EGLSurface surf = EGL_NO_SURFACE;
    EGLConfig cfg = NULL;
    EGLint major = 0, minor = 0, ncfg = 0;
    GLuint shader = 0, prog = 0, ssbo = 0;
    GLint count_loc = -1;
    GLint alu_iters_loc = -1;
    int rc = 1;
    int perf = 0;
    int iterations_set = 0;
    int warmup_set = 0;
    unsigned count = 64;
    unsigned iterations = 1;
    unsigned warmup = 0;
    unsigned alu_iters = 1;
    unsigned total_loops;
    uint32_t *input = NULL;
    uint64_t program_start_us;
    uint64_t open_start_us = 0, open_done_us = 0;
    uint64_t gbm_start_us = 0, gbm_done_us = 0;
    uint64_t egl_display_start_us = 0, egl_display_done_us = 0;
    uint64_t egl_init_start_us = 0, egl_init_done_us = 0;
    uint64_t egl_config_start_us = 0, egl_config_done_us = 0;
    uint64_t egl_context_start_us = 0, egl_context_done_us = 0;
    uint64_t egl_current_start_us = 0, egl_current_done_us = 0;
    uint64_t gl_query_start_us = 0, gl_query_done_us = 0;
    uint64_t shader_compile_start_us = 0, shader_compile_done_us = 0;
    uint64_t program_link_start_us = 0, program_link_done_us = 0;
    uint64_t buffer_setup_start_us = 0, buffer_setup_done_us = 0;
    uint64_t init_done_us;
    uint64_t loop_start_us;
    uint64_t measured_loop_start_us = 0;
    uint64_t loop_end_us;
    uint64_t total_iter_us = 0;
    uint64_t min_iter_us = UINT64_MAX;
    uint64_t max_iter_us = 0;
    unsigned dispatch_groups_x;
    unsigned dispatch_groups_y;
    struct perf_stats cpu_prepare_stats;
    struct perf_stats buffer_upload_stats;
    struct perf_stats dispatch_call_stats;
    struct perf_stats memory_barrier_stats;
    struct perf_stats map_wait_stats;
    struct perf_stats unmap_stats;
    struct perf_stats iter_total_stats;

    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--perf")) {
            perf = 1;
        } else if (!strcmp(argv[i], "--iterations")) {
            if (++i >= argc || parse_uint_arg("--iterations", argv[i], &iterations))
                return 2;
            iterations_set = 1;
        } else if (!strcmp(argv[i], "--warmup")) {
            if (++i >= argc || parse_uint0_arg("--warmup", argv[i], &warmup))
                return 2;
            warmup_set = 1;
        } else if (!strcmp(argv[i], "--count")) {
            if (++i >= argc || parse_uint_arg("--count", argv[i], &count))
                return 2;
        } else if (!strcmp(argv[i], "--alu-iters")) {
            if (++i >= argc || parse_uint_arg("--alu-iters", argv[i], &alu_iters))
                return 2;
        } else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            fprintf(stderr,
                    "usage: %s [--perf] [--alu-iters N] [--iterations N] [--warmup N] [--count N] [drm-node]\n",
                    argv[0]);
            return 0;
        } else if (!requested_path) {
            requested_path = argv[i];
        } else {
            fprintf(stderr,
                    "usage: %s [--perf] [--alu-iters N] [--iterations N] [--warmup N] [--count N] [drm-node]\n",
                    argv[0]);
            return 2;
        }
    }

    if (perf && !iterations_set)
        iterations = 50;
    if (perf && !warmup_set)
        warmup = 5;
    if (warmup > UINT_MAX - iterations) {
        fprintf(stderr, "invalid loop count: warmup + iterations overflows\n");
        return 2;
    }
    total_loops = warmup + iterations;
    compute_dispatch_dims(count, &dispatch_groups_x, &dispatch_groups_y);

    perf_stats_init(&cpu_prepare_stats);
    perf_stats_init(&buffer_upload_stats);
    perf_stats_init(&dispatch_call_stats);
    perf_stats_init(&memory_barrier_stats);
    perf_stats_init(&map_wait_stats);
    perf_stats_init(&unmap_stats);
    perf_stats_init(&iter_total_stats);

    input = calloc(count, sizeof(*input));
    if (!input) {
        fprintf(stderr, "failed to allocate input buffer for count=%u\n",
                count);
        return 2;
    }
    program_start_us = now_us();

    open_start_us = now_us();
    stage("open-drm");
    if (requested_path) {
        snprintf(path, sizeof(path), "%s", requested_path);
        fd = open(path, O_RDWR | O_CLOEXEC);
    } else {
        fd = open_default_drm_node(path, sizeof(path));
    }
    open_done_us = now_us();

    if (fd < 0) {
        fprintf(stderr, "open %s failed: %s\n", path, strerror(errno));
        return 2;
    }

    printf("DRM_NODE=%s\n", path);

    gbm_start_us = now_us();
    stage("gbm-create-device");
    gbm = gbm_create_device(fd);
    if (!gbm) {
        fprintf(stderr, "gbm_create_device failed\n");
        goto out;
    }
    gbm_done_us = now_us();

    printf("GBM_BACKEND=%s\n", gbm_device_get_backend_name(gbm));

    egl_display_start_us = now_us();
    stage("egl-get-display");
    PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform_display =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (get_platform_display)
        dpy = get_platform_display(EGL_PLATFORM_GBM_MESA, gbm, NULL);
    if (dpy == EGL_NO_DISPLAY)
        dpy = eglGetDisplay((EGLNativeDisplayType)gbm);
    if (dpy == EGL_NO_DISPLAY) {
        fail_egl("eglGetDisplay");
        goto out;
    }
    egl_display_done_us = now_us();

    egl_init_start_us = now_us();
    stage("egl-initialize");
    if (!eglInitialize(dpy, &major, &minor)) {
        fail_egl("eglInitialize");
        goto out;
    }
    egl_init_done_us = now_us();

    printf("EGL_VERSION=%d.%d\n", major, minor);
    printf("EGL_VENDOR=%s\n", eglQueryString(dpy, EGL_VENDOR));
    printf("EGL_EXTENSIONS=%s\n", eglQueryString(dpy, EGL_EXTENSIONS));

    if (!eglBindAPI(EGL_OPENGL_ES_API)) {
        fail_egl("eglBindAPI");
        goto out;
    }

    egl_config_start_us = now_us();
    stage("egl-choose-config");
    const EGLint cfg_attrs[] = {
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
        EGL_SURFACE_TYPE, EGL_WINDOW_BIT | EGL_PBUFFER_BIT,
        EGL_RED_SIZE, 8,
        EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8,
        EGL_NONE,
    };

    if (!eglChooseConfig(dpy, cfg_attrs, &cfg, 1, &ncfg) || ncfg < 1) {
        const EGLint fallback_attrs[] = {
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
            EGL_NONE,
        };
        if (!eglChooseConfig(dpy, fallback_attrs, &cfg, 1, &ncfg) || ncfg < 1) {
            fail_egl("eglChooseConfig");
            goto out;
        }
    }
    egl_config_done_us = now_us();

    const EGLint ctx_attrs[] = {
        EGL_CONTEXT_CLIENT_VERSION, 3,
        EGL_NONE,
    };

    egl_context_start_us = now_us();
    stage("egl-create-context");
    ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attrs);
    if (ctx == EGL_NO_CONTEXT) {
        fail_egl("eglCreateContext");
        goto out;
    }
    egl_context_done_us = now_us();

    egl_current_start_us = now_us();
    stage("egl-make-current");
    if (!eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
        const EGLint pbuf_attrs[] = {
            EGL_WIDTH, 1,
            EGL_HEIGHT, 1,
            EGL_NONE,
        };
        surf = eglCreatePbufferSurface(dpy, cfg, pbuf_attrs);
        if (surf == EGL_NO_SURFACE) {
            fail_egl("eglCreatePbufferSurface");
            goto out;
        }
        if (!eglMakeCurrent(dpy, surf, surf, ctx)) {
            fail_egl("eglMakeCurrent");
            goto out;
        }
    }
    egl_current_done_us = now_us();

    gl_query_start_us = now_us();
    stage("gl-query");
    const char *vendor = (const char *)glGetString(GL_VENDOR);
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    const char *version = (const char *)glGetString(GL_VERSION);
    const char *glsl = (const char *)glGetString(GL_SHADING_LANGUAGE_VERSION);
    GLint gl_major = 0, gl_minor = 0;
    glGetIntegerv(GL_MAJOR_VERSION, &gl_major);
    glGetIntegerv(GL_MINOR_VERSION, &gl_minor);

    printf("GL_VENDOR=%s\n", vendor ? vendor : "(null)");
    printf("GL_RENDERER=%s\n", renderer ? renderer : "(null)");
    printf("GL_VERSION=%s\n", version ? version : "(null)");
    printf("GLSL_VERSION=%s\n", glsl ? glsl : "(null)");
    printf("GL_NUM_VERSION=%d.%d\n", gl_major, gl_minor);

    if (has_bad_renderer(renderer)) {
        fprintf(stderr, "software renderer detected; refusing to count this as GPU passthrough\n");
        rc = 20;
        goto out;
    }

    if (gl_major < 3 || (gl_major == 3 && gl_minor < 1)) {
        fprintf(stderr, "OpenGL ES 3.1 is required for compute shaders\n");
        rc = 21;
        goto out;
    }
    gl_query_done_us = now_us();

    shader_compile_start_us = now_us();
    stage("compile-shader");
    shader = compile_shader();
    if (!shader)
        goto out;
    shader_compile_done_us = now_us();

    program_link_start_us = now_us();
    stage("link-program");
    prog = link_program(shader);
    if (!prog)
        goto out;
    count_loc = glGetUniformLocation(prog, "u_count");
    if (count_loc < 0) {
        fprintf(stderr, "missing shader uniform u_count\n");
        goto out;
    }
    alu_iters_loc = glGetUniformLocation(prog, "u_alu_iters");
    if (alu_iters_loc < 0) {
        fprintf(stderr, "missing shader uniform u_alu_iters\n");
        goto out;
    }
    program_link_done_us = now_us();

    buffer_setup_start_us = now_us();
    stage("buffer-setup");
    glGenBuffers(1, &ssbo);
    if (check_gl("glGenBuffers"))
        goto out;
    buffer_setup_done_us = now_us();

    init_done_us = now_us();
    if (perf) {
        printf("PERF_CONFIG iterations=%u warmup=%u count=%u bytes=%zu alu_iters=%u\n",
               iterations, warmup, count, (size_t)count * sizeof(*input),
               alu_iters);
        printf("PERF_INIT_PHASE_US name=open_drm total=%llu\n",
               (unsigned long long)(open_done_us - open_start_us));
        printf("PERF_INIT_PHASE_US name=gbm_create_device total=%llu\n",
               (unsigned long long)(gbm_done_us - gbm_start_us));
        printf("PERF_INIT_PHASE_US name=egl_get_display total=%llu\n",
               (unsigned long long)(egl_display_done_us - egl_display_start_us));
        printf("PERF_INIT_PHASE_US name=egl_initialize total=%llu\n",
               (unsigned long long)(egl_init_done_us - egl_init_start_us));
        printf("PERF_INIT_PHASE_US name=egl_choose_config total=%llu\n",
               (unsigned long long)(egl_config_done_us - egl_config_start_us));
        printf("PERF_INIT_PHASE_US name=egl_create_context total=%llu\n",
               (unsigned long long)(egl_context_done_us - egl_context_start_us));
        printf("PERF_INIT_PHASE_US name=egl_make_current total=%llu\n",
               (unsigned long long)(egl_current_done_us - egl_current_start_us));
        printf("PERF_INIT_PHASE_US name=gl_query total=%llu\n",
               (unsigned long long)(gl_query_done_us - gl_query_start_us));
        printf("PERF_INIT_PHASE_US name=shader_compile total=%llu\n",
               (unsigned long long)(shader_compile_done_us - shader_compile_start_us));
        printf("PERF_INIT_PHASE_US name=program_link total=%llu\n",
               (unsigned long long)(program_link_done_us - program_link_start_us));
        printf("PERF_INIT_PHASE_US name=buffer_create total=%llu\n",
               (unsigned long long)(buffer_setup_done_us - buffer_setup_start_us));
        printf("PERF_INIT_US=%llu\n",
               (unsigned long long)(init_done_us - program_start_us));
        stage("perf-loop");
    }

    loop_start_us = now_us();
    for (unsigned iter = 0; iter < total_loops; iter++) {
        int measured = iter >= warmup;
        uint64_t iter_start_us;
        uint64_t iter_end_us;
        uint64_t cpu_prepare_done_us;
        uint64_t buffer_upload_done_us;
        uint64_t dispatch_done_us;
        uint64_t barrier_done_us;
        uint64_t map_done_us;
        uint32_t *mapped;

        if (iter == warmup)
            measured_loop_start_us = now_us();

        iter_start_us = now_us();
        for (unsigned i = 0; i < count; i++)
            input[i] = i;
        cpu_prepare_done_us = now_us();

        glBindBuffer(GL_SHADER_STORAGE_BUFFER, ssbo);
        glBufferData(GL_SHADER_STORAGE_BUFFER, (GLsizeiptr)count * sizeof(*input),
                     input, GL_DYNAMIC_COPY);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, ssbo);
        if (check_gl("buffer setup"))
            goto out;
        buffer_upload_done_us = now_us();

        if (!perf)
            stage("dispatch");
        glUseProgram(prog);
        glUniform1ui(count_loc, count);
        glUniform1ui(alu_iters_loc, alu_iters);
        glDispatchCompute(dispatch_groups_x, dispatch_groups_y, 1);
        dispatch_done_us = now_us();
        glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT | GL_BUFFER_UPDATE_BARRIER_BIT);
        if (check_gl("compute dispatch"))
            goto out;
        barrier_done_us = now_us();

        if (!perf)
            stage("map-result");
        mapped = glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0,
                                  (GLsizeiptr)count * sizeof(*input),
                                  GL_MAP_READ_BIT);
        if (!mapped) {
            fprintf(stderr, "glMapBufferRange failed\n");
            check_gl("glMapBufferRange");
            goto out;
        }
        map_done_us = now_us();

        glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);

        iter_end_us = now_us();
        if (measured) {
            uint64_t iter_total = iter_end_us - iter_start_us;

            perf_stats_add(&cpu_prepare_stats, cpu_prepare_done_us - iter_start_us);
            perf_stats_add(&buffer_upload_stats, buffer_upload_done_us - cpu_prepare_done_us);
            perf_stats_add(&dispatch_call_stats, dispatch_done_us - buffer_upload_done_us);
            perf_stats_add(&memory_barrier_stats, barrier_done_us - dispatch_done_us);
            perf_stats_add(&map_wait_stats, map_done_us - barrier_done_us);
            perf_stats_add(&unmap_stats, iter_end_us - map_done_us);
            perf_stats_add(&iter_total_stats, iter_total);

            if (iter_total < min_iter_us)
                min_iter_us = iter_total;
            if (iter_total > max_iter_us)
                max_iter_us = iter_total;
            total_iter_us += iter_total;
        }
    }
    loop_end_us = now_us();
    if (!measured_loop_start_us)
        measured_loop_start_us = loop_end_us;

    glBindBuffer(GL_SHADER_STORAGE_BUFFER, ssbo);
    {
        uint32_t *mapped = glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0,
                                            (GLsizeiptr)count * sizeof(*input),
                                            GL_MAP_READ_BIT);
        unsigned sample_count = count < 16 ? count : 16;

        if (!mapped) {
            fprintf(stderr, "final validation glMapBufferRange failed\n");
            check_gl("final validation glMapBufferRange");
            goto out;
        }

        for (unsigned sample = 0; sample < sample_count; sample++) {
            unsigned i = sample_count == 1 ?
                         0 :
                         (unsigned)(((uint64_t)sample * (uint64_t)(count - 1)) /
                                    (uint64_t)(sample_count - 1));
            uint32_t expected = expected_value(i, alu_iters);

            if (mapped[i] != expected) {
                fprintf(stderr,
                        "mismatch at final check index %u: got %u expected %u alu_iters=%u\n",
                        i, mapped[i], expected, alu_iters);
                glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
                rc = 22;
                goto out;
            }
        }

        glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
    }

    printf("COMPUTE_CHECK=PASS count=%u samples=%u formula=x*3+7+alu_mix alu_iters=%u\n",
           count, count < 16 ? count : 16, alu_iters);
    if (perf) {
        printf("PERF_ITER_US min=%llu avg=%.2f max=%llu total=%llu\n",
               (unsigned long long)min_iter_us,
               (double)total_iter_us / (double)iterations,
               (unsigned long long)max_iter_us,
               (unsigned long long)total_iter_us);
        perf_stats_print("cpu_prepare", &cpu_prepare_stats, iterations);
        perf_stats_print("buffer_upload", &buffer_upload_stats, iterations);
        perf_stats_print("dispatch_call", &dispatch_call_stats, iterations);
        perf_stats_print("memory_barrier", &memory_barrier_stats, iterations);
        perf_stats_print("map_wait", &map_wait_stats, iterations);
        perf_stats_print("unmap", &unmap_stats, iterations);
        perf_stats_print("iter_total", &iter_total_stats, iterations);
        printf("PERF_WARMUP_US=%llu\n",
               (unsigned long long)(measured_loop_start_us - loop_start_us));
        printf("PERF_MEASURED_LOOP_US=%llu\n",
               (unsigned long long)(loop_end_us - measured_loop_start_us));
        printf("PERF_LOOP_US=%llu\n",
               (unsigned long long)(loop_end_us - loop_start_us));
        printf("PERF_TOTAL_US=%llu\n",
               (unsigned long long)(loop_end_us - program_start_us));
    }
    rc = 0;

out:
    if (ssbo)
        glDeleteBuffers(1, &ssbo);
    if (prog)
        glDeleteProgram(prog);
    if (shader)
        glDeleteShader(shader);
    if (dpy != EGL_NO_DISPLAY) {
        eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (ctx != EGL_NO_CONTEXT)
            eglDestroyContext(dpy, ctx);
        if (surf != EGL_NO_SURFACE)
            eglDestroySurface(dpy, surf);
        eglTerminate(dpy);
    }
    if (gbm)
        gbm_device_destroy(gbm);
    if (fd >= 0)
        close(fd);
    free(input);

    return rc;
}
