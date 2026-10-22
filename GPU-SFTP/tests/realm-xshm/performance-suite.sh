#!/bin/sh
# Identical workload dispatcher for native Panthor and RMM-backed P42 Clients.
set -eu
profile=${1:?profile required}
barrier=0
case "$profile" in
ml-*-barrier|attention-320-barrier|ncnn-*-barrier)
    barrier=1
    profile=${profile%-barrier} ;;
esac
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export MESA_SHADER_CACHE_DISABLE=true
export LIBGL_ALWAYS_SOFTWARE=0
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
printf 'PERFORMANCE_CASE=%s\n' "$profile"
cat > /tmp/performance.env <<'ENV'
GPU_SMOKE_DRM_NODE=/dev/dri/renderD128
GPU_SMOKE_QUIET_CONSOLE=1
GPU_SMOKE_GUEST_SUBMIT_STATS=0
GPU_SMOKE_GUEST_IRQ_STATS=0
GPU_SMOKE_GLMARK_FLAVOR=null-noop
GPU_SMOKE_GLMARK_FRAME_END=finish
GPU_SMOKE_GLMARK_SKIP_VALIDATE=0
GPU_SMOKE_GLMARK_BENCHMARKS=''
GPU_SMOKE_GLMARK_EXTRA_ARGS=''
ENV
case "$profile" in
ioctl)
    /tmp/ioctl-perf
    rc=$?
    if [ "$rc" = 0 ]; then echo PERFORMANCE_CASE_RESULT=PASS; else echo PERFORMANCE_CASE_RESULT=FAIL; fi
    exit "$rc" ;;
compute-4|compute-16|compute-64|compute-128|dual-compute)
    mib=${profile#compute-}; iterations=100
    [ "$profile" != dual-compute ] || mib=4
    [ "$mib" -lt 64 ] || iterations=20
    count=$((mib * 262144))
    exclude=--exclude-cpu-prepare
    [ "$profile" != dual-compute ] || exclude=
    printf "GPU_SMOKE_TEST=compute\nGPU_SMOKE_ARGS='--count %s --iterations %s --warmup 5 --perf %s'\n" "$count" "$iterations" "$exclude" >> /tmp/performance.env ;;
ml-all)
    printf "GPU_SMOKE_TEST=ml\nGPU_SMOKE_ARGS='--kernel all --gemm-size 512 --iterations 100 --warmup 5'\n" >> /tmp/performance.env ;;
ml-gemm|ml-conv|ml-depthwise|ml-reduction|ml-softmax|ml-attention)
    timing_barrier=''
    [ "$barrier" != 1 ] || timing_barrier=--start-barrier
    printf "GPU_SMOKE_TEST=ml\nGPU_SMOKE_ARGS='--kernel %s --gemm-size 512 --iterations 100 --warmup 5 %s'\n" "${profile#ml-}" "$timing_barrier" >> /tmp/performance.env ;;
attention-320)
    timing_barrier=''
    [ "$barrier" != 1 ] || timing_barrier=--start-barrier
    printf "GPU_SMOKE_TEST=ml\nGPU_SMOKE_ARGS='--kernel attention --attention-size 320 --iterations 10 --warmup 2 %s'\n" "$timing_barrier" >> /tmp/performance.env ;;
ncnn-mobilenet_v2|ncnn-mobilenet_v3|ncnn-resnet50)
    printf 'GPU_SMOKE_TEST=ncnn\nGPU_SMOKE_NCNN_MODELS=%s\nGPU_SMOKE_NCNN_LOOP_COUNT=100\nGPU_SMOKE_NCNN_THREADS=2\nGPU_SMOKE_NCNN_TIMEOUT_S=900\n' "${profile#ncnn-}" >> /tmp/performance.env ;;
glmark-720|glmark-720-barrier|glmark-1080|glmark-1080-barrier)
    size=1280x720
    case "$profile" in glmark-1080*) size=1920x1080 ;; esac
    if [ "${profile%-barrier}" != "$profile" ]; then
        printf 'GPU_SMOKE_GLMARK_START_BARRIER=1\n' >> /tmp/performance.env
    fi
    printf 'GPU_SMOKE_TEST=glmark\nGPU_SMOKE_GLMARK_SIZE=%s\n' "$size" >> /tmp/performance.env ;;
*) echo PERFORMANCE_CASE_RESULT=FAIL; exit 2 ;;
esac
if [ "$barrier" = 1 ]; then
    echo ML_BENCHMARK_READY
    read -r release
    [ "$release" = ML_BENCHMARK_GO ] || exit 2
    echo ML_BENCHMARK_START
fi
rc=0
GPU_SMOKE_ENV_FILE=/tmp/performance.env /bin/sh /root/gpu-smoke.sh || rc=$?
if [ "$barrier" = 1 ]; then echo ML_BENCHMARK_END; fi
if [ "$rc" = 0 ]; then echo PERFORMANCE_CASE_RESULT=PASS; else echo PERFORMANCE_CASE_RESULT=FAIL; fi
exit "$rc"
