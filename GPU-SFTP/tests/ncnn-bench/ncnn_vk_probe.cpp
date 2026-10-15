#include <cstdio>
#include "gpu.h"

int main()
{
    const int count = ncnn::get_gpu_count();
    std::printf("NCNN_VK_GPU_COUNT=%d\n", count);
    if (count <= 0)
    {
        std::printf("NCNN_VK_PROBE_RESULT=FAIL reason=no-vulkan-device\n");
        return 1;
    }

    for (int i = 0; i < count; i++)
    {
        ncnn::VulkanDevice device(i);
        const ncnn::GpuInfo& info = device.info;
        std::printf("NCNN_VK_DEVICE_%d_INDEX=%d\n", i, info.device_index());
        std::printf("NCNN_VK_DEVICE_%d_TYPE=%d\n", i, info.type());
        std::printf("NCNN_VK_DEVICE_%d_NAME=%s\n", i, info.device_name());
        std::printf("NCNN_VK_DEVICE_%d_DRIVER_NAME=%s\n", i, info.driver_name());
        std::printf("NCNN_VK_DEVICE_%d_API=%u\n", i, info.api_version());
    }

    const ncnn::VulkanDevice device0(0);
    const ncnn::GpuInfo& info0 = device0.info;
    // Vulkan VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU is 1.
    if (!device0.is_valid() || info0.type() != 1)
    {
        std::printf("NCNN_VK_PROBE_RESULT=FAIL reason=invalid-device\n");
        return 2;
    }
    std::printf("NCNN_VK_PROBE_RESULT=PASS\n");
    return 0;
}
