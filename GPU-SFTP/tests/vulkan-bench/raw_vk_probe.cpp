#include <dlfcn.h>
#include <vulkan/vulkan.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

PFN_vkGetInstanceProcAddr load_instance_proc(const char* driver_path, void** library)
{
    const char* path = driver_path && driver_path[0] ? driver_path : "libvulkan.so.1";
    void* handle = dlopen(path, RTLD_LOCAL | RTLD_NOW);
    if (!handle)
    {
        std::fprintf(stderr, "RAW_VK_DLOPEN_ERROR=%s\n", dlerror());
        return nullptr;
    }

    auto icd_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
        dlsym(handle, "vk_icdGetInstanceProcAddr"));
    if (!icd_proc)
    {
        icd_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
            dlsym(handle, "vkGetInstanceProcAddr"));
    }
    if (!icd_proc)
    {
        std::fprintf(stderr, "RAW_VK_DLSYM_ERROR=%s\n", dlerror());
        dlclose(handle);
        return nullptr;
    }

    *library = handle;
    return icd_proc;
}

const char* result_name(VkResult result)
{
    switch (result)
    {
#define RAW_VK_RESULT(name) \
    case name: return #name;
        RAW_VK_RESULT(VK_SUCCESS)
        RAW_VK_RESULT(VK_NOT_READY)
        RAW_VK_RESULT(VK_TIMEOUT)
        RAW_VK_RESULT(VK_EVENT_SET)
        RAW_VK_RESULT(VK_EVENT_RESET)
        RAW_VK_RESULT(VK_INCOMPLETE)
        RAW_VK_RESULT(VK_ERROR_OUT_OF_HOST_MEMORY)
        RAW_VK_RESULT(VK_ERROR_OUT_OF_DEVICE_MEMORY)
        RAW_VK_RESULT(VK_ERROR_INITIALIZATION_FAILED)
        RAW_VK_RESULT(VK_ERROR_DEVICE_LOST)
        RAW_VK_RESULT(VK_ERROR_MEMORY_MAP_FAILED)
        RAW_VK_RESULT(VK_ERROR_LAYER_NOT_PRESENT)
        RAW_VK_RESULT(VK_ERROR_EXTENSION_NOT_PRESENT)
        RAW_VK_RESULT(VK_ERROR_FEATURE_NOT_PRESENT)
        RAW_VK_RESULT(VK_ERROR_INCOMPATIBLE_DRIVER)
        RAW_VK_RESULT(VK_ERROR_TOO_MANY_OBJECTS)
        RAW_VK_RESULT(VK_ERROR_FORMAT_NOT_SUPPORTED)
        RAW_VK_RESULT(VK_ERROR_FRAGMENTED_POOL)
        RAW_VK_RESULT(VK_ERROR_OUT_OF_POOL_MEMORY)
        RAW_VK_RESULT(VK_ERROR_INVALID_EXTERNAL_HANDLE)
        RAW_VK_RESULT(VK_ERROR_SURFACE_LOST_KHR)
        RAW_VK_RESULT(VK_ERROR_NATIVE_WINDOW_IN_USE_KHR)
        RAW_VK_RESULT(VK_SUBOPTIMAL_KHR)
        RAW_VK_RESULT(VK_ERROR_OUT_OF_DATE_KHR)
        RAW_VK_RESULT(VK_ERROR_INCOMPATIBLE_DISPLAY_KHR)
        RAW_VK_RESULT(VK_ERROR_VALIDATION_FAILED_EXT)
        RAW_VK_RESULT(VK_ERROR_FRAGMENTATION_EXT)
        RAW_VK_RESULT(VK_ERROR_NOT_PERMITTED_EXT)
#undef RAW_VK_RESULT
        default: return "VK_UNKNOWN";
    }
}

uint32_t choose_compute_family(
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_props,
    VkPhysicalDevice physical,
    uint32_t* available_count)
{
    uint32_t count = 0;
    get_queue_props(physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    get_queue_props(physical, &count, families.data());

    uint32_t fallback = UINT32_MAX;
    for (uint32_t i = 0; i < count; ++i)
    {
        std::printf(
            "RAW_VK_QUEUE_FAMILY=%u flags=0x%x count=%u timestamp_valid=%u image_granularity=%u\n",
            i, families[i].queueFlags, families[i].queueCount,
            families[i].timestampValidBits, families[i].minImageTransferGranularity.width);
        if ((families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) == 0)
            continue;
        if ((families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) == 0)
        {
            *available_count = families[i].queueCount;
            return i;
        }
        if (fallback == UINT32_MAX)
        {
            fallback = i;
            *available_count = families[i].queueCount;
        }
    }
    return fallback;
}

struct VulkanFunctions
{
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices;
    PFN_vkGetPhysicalDeviceProperties get_physical_device_properties;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_family_properties;
    PFN_vkCreateDevice create_device;
    PFN_vkDestroyDevice destroy_device;
    PFN_vkGetDeviceQueue get_device_queue;
    PFN_vkCreateCommandPool create_command_pool;
    PFN_vkDestroyCommandPool destroy_command_pool;
    PFN_vkAllocateCommandBuffers allocate_command_buffers;
    PFN_vkFreeCommandBuffers free_command_buffers;
    PFN_vkBeginCommandBuffer begin_command_buffer;
    PFN_vkEndCommandBuffer end_command_buffer;
    PFN_vkCmdPipelineBarrier cmd_pipeline_barrier;
    PFN_vkCreateFence create_fence;
    PFN_vkDestroyFence destroy_fence;
    PFN_vkResetFences reset_fences;
    PFN_vkGetFenceStatus get_fence_status;
    PFN_vkWaitForFences wait_for_fences;
    PFN_vkCreateSemaphore create_semaphore;
    PFN_vkDestroySemaphore destroy_semaphore;
    PFN_vkQueueSubmit queue_submit;
    PFN_vkQueueWaitIdle queue_wait_idle;
    PFN_vkDeviceWaitIdle device_wait_idle;
    PFN_vkCreateBuffer create_buffer;
    PFN_vkDestroyBuffer destroy_buffer;
    PFN_vkGetBufferMemoryRequirements get_buffer_memory_requirements;
    PFN_vkCreateImage create_image;
    PFN_vkDestroyImage destroy_image;
    PFN_vkGetImageMemoryRequirements get_image_memory_requirements;
    PFN_vkGetPhysicalDeviceMemoryProperties get_physical_device_memory_properties;
    PFN_vkAllocateMemory allocate_memory;
    PFN_vkFreeMemory free_memory;
    PFN_vkBindBufferMemory bind_buffer_memory;
    PFN_vkBindImageMemory bind_image_memory;
    PFN_vkMapMemory map_memory;
    PFN_vkUnmapMemory unmap_memory;
    PFN_vkCreateShaderModule create_shader_module;
    PFN_vkDestroyShaderModule destroy_shader_module;
    PFN_vkCreateDescriptorSetLayout create_descriptor_set_layout;
    PFN_vkDestroyDescriptorSetLayout destroy_descriptor_set_layout;
    PFN_vkCreatePipelineLayout create_pipeline_layout;
    PFN_vkDestroyPipelineLayout destroy_pipeline_layout;
    PFN_vkCreatePipelineCache create_pipeline_cache;
    PFN_vkDestroyPipelineCache destroy_pipeline_cache;
    PFN_vkCreateComputePipelines create_compute_pipelines;
    PFN_vkDestroyPipeline destroy_pipeline;
    PFN_vkCreateDescriptorPool create_descriptor_pool;
    PFN_vkDestroyDescriptorPool destroy_descriptor_pool;
    PFN_vkAllocateDescriptorSets allocate_descriptor_sets;
    PFN_vkUpdateDescriptorSets update_descriptor_sets;
    PFN_vkCmdBindPipeline cmd_bind_pipeline;
    PFN_vkCmdBindDescriptorSets cmd_bind_descriptor_sets;
    PFN_vkCmdDispatch cmd_dispatch;
};

#define LOAD_VK_FN(member, name) \
    functions.member = reinterpret_cast<decltype(functions.member)>( \
        instance_proc(instance, name)); \
    if (!functions.member) \
    { \
        std::fprintf(stderr, "RAW_VK_MISSING_PROC=%s\n", name); \
        return false; \
    }

bool load_functions(
    PFN_vkGetInstanceProcAddr instance_proc,
    VkInstance instance,
    VulkanFunctions& functions)
{
    LOAD_VK_FN(enumerate_physical_devices, "vkEnumeratePhysicalDevices")
    LOAD_VK_FN(get_physical_device_properties, "vkGetPhysicalDeviceProperties")
    LOAD_VK_FN(get_queue_family_properties, "vkGetPhysicalDeviceQueueFamilyProperties")
    LOAD_VK_FN(create_device, "vkCreateDevice")
    LOAD_VK_FN(destroy_device, "vkDestroyDevice")
    LOAD_VK_FN(get_device_queue, "vkGetDeviceQueue")
    LOAD_VK_FN(create_command_pool, "vkCreateCommandPool")
    LOAD_VK_FN(destroy_command_pool, "vkDestroyCommandPool")
    LOAD_VK_FN(allocate_command_buffers, "vkAllocateCommandBuffers")
    LOAD_VK_FN(free_command_buffers, "vkFreeCommandBuffers")
    LOAD_VK_FN(begin_command_buffer, "vkBeginCommandBuffer")
    LOAD_VK_FN(end_command_buffer, "vkEndCommandBuffer")
    LOAD_VK_FN(cmd_pipeline_barrier, "vkCmdPipelineBarrier")
    LOAD_VK_FN(create_fence, "vkCreateFence")
    LOAD_VK_FN(destroy_fence, "vkDestroyFence")
    LOAD_VK_FN(reset_fences, "vkResetFences")
    LOAD_VK_FN(get_fence_status, "vkGetFenceStatus")
    LOAD_VK_FN(wait_for_fences, "vkWaitForFences")
    LOAD_VK_FN(create_semaphore, "vkCreateSemaphore")
    LOAD_VK_FN(destroy_semaphore, "vkDestroySemaphore")
    LOAD_VK_FN(queue_submit, "vkQueueSubmit")
    LOAD_VK_FN(queue_wait_idle, "vkQueueWaitIdle")
    LOAD_VK_FN(device_wait_idle, "vkDeviceWaitIdle")
    LOAD_VK_FN(create_buffer, "vkCreateBuffer")
    LOAD_VK_FN(destroy_buffer, "vkDestroyBuffer")
    LOAD_VK_FN(get_buffer_memory_requirements, "vkGetBufferMemoryRequirements")
    LOAD_VK_FN(create_image, "vkCreateImage")
    LOAD_VK_FN(destroy_image, "vkDestroyImage")
    LOAD_VK_FN(get_image_memory_requirements, "vkGetImageMemoryRequirements")
    LOAD_VK_FN(get_physical_device_memory_properties, "vkGetPhysicalDeviceMemoryProperties")
    LOAD_VK_FN(allocate_memory, "vkAllocateMemory")
    LOAD_VK_FN(free_memory, "vkFreeMemory")
    LOAD_VK_FN(bind_buffer_memory, "vkBindBufferMemory")
    LOAD_VK_FN(bind_image_memory, "vkBindImageMemory")
    LOAD_VK_FN(map_memory, "vkMapMemory")
    LOAD_VK_FN(unmap_memory, "vkUnmapMemory")
    LOAD_VK_FN(create_shader_module, "vkCreateShaderModule")
    LOAD_VK_FN(destroy_shader_module, "vkDestroyShaderModule")
    LOAD_VK_FN(create_descriptor_set_layout, "vkCreateDescriptorSetLayout")
    LOAD_VK_FN(destroy_descriptor_set_layout, "vkDestroyDescriptorSetLayout")
    LOAD_VK_FN(create_pipeline_layout, "vkCreatePipelineLayout")
    LOAD_VK_FN(destroy_pipeline_layout, "vkDestroyPipelineLayout")
    LOAD_VK_FN(create_pipeline_cache, "vkCreatePipelineCache")
    LOAD_VK_FN(destroy_pipeline_cache, "vkDestroyPipelineCache")
    LOAD_VK_FN(create_compute_pipelines, "vkCreateComputePipelines")
    LOAD_VK_FN(destroy_pipeline, "vkDestroyPipeline")
    LOAD_VK_FN(create_descriptor_pool, "vkCreateDescriptorPool")
    LOAD_VK_FN(destroy_descriptor_pool, "vkDestroyDescriptorPool")
    LOAD_VK_FN(allocate_descriptor_sets, "vkAllocateDescriptorSets")
    LOAD_VK_FN(update_descriptor_sets, "vkUpdateDescriptorSets")
    LOAD_VK_FN(cmd_bind_pipeline, "vkCmdBindPipeline")
    LOAD_VK_FN(cmd_bind_descriptor_sets, "vkCmdBindDescriptorSets")
    LOAD_VK_FN(cmd_dispatch, "vkCmdDispatch")
    return true;
}

#undef LOAD_VK_FN

int32_t find_memory_type(
    const VkPhysicalDeviceMemoryProperties& memory,
    uint32_t type_bits,
    VkMemoryPropertyFlags required)
{
    for (uint32_t i = 0; i < memory.memoryTypeCount; ++i)
    {
        if ((type_bits & (1u << i)) &&
            (memory.memoryTypes[i].propertyFlags & required) == required)
        {
            return static_cast<int32_t>(i);
        }
    }
    return -1;
}

const char k_raw_vk_compute_spirv_hex[] =
    "03022307000001000a000800280000000000000011000200010000000b00060001000000474c534c2e7374642e343530000000000e00030000000000010000000f00060005000000040000006d61696e000000000b0000001000060004000000110000004000000001000000010000000300030002000000c201000005000400040000006d61696e000000000500040008000000696e646578000000050008000b000000676c5f476c6f62616c496e766f636174696f6e49440000000500040012000000446174610000000006000500120000000000000076616c7565730000050003001400000000000000470004000b0000000b0000001c000000470004001100000006000000040000004800050012000000000000002300000000000000470003001200000003000000470004001400000022000000000000004700040014000000210000000000000047000400270000000b000000190000001300020002000000210003000300000002000000150004000600000020000000000000002000040007000000070000000600000017000400090000000600000003000000200004000a00000001000000090000003b0004000a0000000b000000010000002b000400060000000c00000000000000200004000d00000001000000060000001d00030011000000060000001e0003001200000011000000200004001300000002000000120000003b0004001300000014000000020000001500040016000000200000000100000014000200190000002b000400160000001d00000000000000200004002000000002000000060000002b0004000600000023000000010000002b0004000600000026000000400000002c00060009000000270000002600000023000000230000003600050002000000040000000000000003000000f8000200050000003b000400070000000800000007000000410005000d0000000e0000000b0000000c0000003d000400060000000f0000000e0000003e000300080000000f0000003d00040006000000100000000800000044000500060000001500000014000000000000007c0004001600000017000000150000007c000400060000001800000017000000b0000500190000001a0000001000000018000000f70003001c00000000000000fa0004001a0000001b0000001c000000f80002001b0000003d000400060000001e000000080000003d000400060000001f00000008000000410006002000000021000000140000001d0000001f0000003d0004000600000022000000210000008000050006000000240000002200000023000000410006002000000025000000140000001d0000001e0000003e0003002500000024000000f90002001c000000f80002001c000000fd00010038000100";

const char k_raw_vk_minimal_storage_spirv_hex[] =
    "03022307000301000a0008001c0000000000000011000200010000000b00060001000000474c534c2e7374642e343530000000000e00030000000000010000000f00060005000000040000006d61696e000000000f0000001000060004000000110000004000000001000000010000000300030002000000c201000005000400040000006d61696e000000000500040008000000446174610000000006000500080000000000000076616c7565730000050003000a00000000000000050008000f000000676c5f476c6f62616c496e766f636174696f6e4944000000470004000700000006000000040000004800050008000000000000002300000000000000470003000800000002000000470004000a0000002200000000000000470004000a0000002100000000000000470004000f0000000b0000001c000000470004001b0000000b000000190000001300020002000000210003000300000002000000150004000600000020000000000000001d00030007000000060000001e000300080000000700000020000400090000000c000000080000003b000400090000000a0000000c000000150004000b00000020000000010000002b0004000b0000000c00000000000000170004000d0000000600000003000000200004000e000000010000000d0000003b0004000e0000000f000000010000002b000400060000001000000000000000200004001100000001000000060000002b00040006000000140000000100000020000400150000000c000000060000002b000400060000001a000000400000002c0006000d0000001b0000001a00000014000000140000003600050002000000040000000000000003000000f8000200050000004100050011000000120000000f000000100000003d0004000600000013000000120000004100050011000000140000000f000000100000003d00040006000000150000001400000080000500060000001700000015000000160000004100060015000000190000000a0000000c000000130000003e0003001900000018000000fd00010038000100";

std::vector<uint32_t> decode_spirv_words(const char* hex)
{
    std::vector<uint32_t> words;
    if (!hex || !hex[0])
        return words;
    const size_t hex_length = std::strlen(hex);
    if ((hex_length & 7u) != 0)
        return words;

    words.reserve(hex_length / 8);
    for (size_t i = 0; i < hex_length; i += 8)
    {
        uint32_t word = 0;
        for (size_t j = 0; j < 8; j += 2)
        {
            uint32_t byte = 0;
            for (size_t k = 0; k < 2; ++k)
            {
                const char c = hex[i + j + k];
                uint32_t nibble;
                if (c >= '0' && c <= '9')
                    nibble = static_cast<uint32_t>(c - '0');
                else if (c >= 'a' && c <= 'f')
                    nibble = static_cast<uint32_t>(c - 'a' + 10);
                else if (c >= 'A' && c <= 'F')
                    nibble = static_cast<uint32_t>(c - 'A' + 10);
                else
                    return {};
                byte = (byte << 4) | nibble;
            }
            word |= byte << (8u * (j / 2u));
        }
        words.push_back(word);
    }
    if (!words.empty() && words[0] != UINT32_C(0x07230203))
        return {};
    return words;
}

bool run_queue_case(
    const VulkanFunctions& vk,
    VkPhysicalDevice physical,
    uint32_t family,
    uint32_t requested_count,
    bool concurrent_submit,
    uint32_t case_index)
{
    std::printf(
        "RAW_VK_CASE=%u family=%u requested_queues=%u submit=%s\n",
        case_index, family, requested_count,
        concurrent_submit ? "concurrent" : "sequential");

    std::vector<float> priorities(requested_count, 1.0f);
    VkDeviceQueueCreateInfo queue_info{};
    queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = requested_count;
    queue_info.pQueuePriorities = priorities.data();

    VkDeviceCreateInfo device_info{};
    device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;

    VkDevice device = VK_NULL_HANDLE;
    VkResult result = vk.create_device(physical, &device_info, nullptr, &device);
    std::printf("RAW_VK_CREATE_DEVICE=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=create-device result=%d\n", static_cast<int>(result));
        return false;
    }

    VkPhysicalDeviceMemoryProperties memory{};
    vk.get_physical_device_memory_properties(physical, &memory);

    VkBufferCreateInfo buffer_info{};
    buffer_info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    buffer_info.size = 4096;
    buffer_info.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
                        VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    VkBuffer buffer = VK_NULL_HANDLE;
    result = vk.create_buffer(device, &buffer_info, nullptr, &buffer);
    std::printf("RAW_VK_CREATE_BUFFER=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=create-buffer result=%d\n", static_cast<int>(result));
        return false;
    }

    VkMemoryRequirements buffer_requirements{};
    vk.get_buffer_memory_requirements(device, buffer, &buffer_requirements);
    int32_t buffer_type = find_memory_type(
        memory, buffer_requirements.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (buffer_type < 0)
        buffer_type = find_memory_type(memory, buffer_requirements.memoryTypeBits, 0);
    std::printf("RAW_VK_BUFFER_TYPE=%d size=%llu alignment=%llu type_bits=0x%x\n",
                buffer_type,
                static_cast<unsigned long long>(buffer_requirements.size),
                static_cast<unsigned long long>(buffer_requirements.alignment),
                buffer_requirements.memoryTypeBits);
    if (buffer_type < 0)
    {
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=find-buffer-memory\n");
        return false;
    }

    VkMemoryAllocateInfo buffer_alloc{};
    buffer_alloc.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    buffer_alloc.allocationSize = buffer_requirements.size;
    buffer_alloc.memoryTypeIndex = static_cast<uint32_t>(buffer_type);
    VkDeviceMemory buffer_memory = VK_NULL_HANDLE;
    result = vk.allocate_memory(device, &buffer_alloc, nullptr, &buffer_memory);
    std::printf("RAW_VK_ALLOC_BUFFER_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=alloc-buffer-memory result=%d\n", static_cast<int>(result));
        return false;
    }
    result = vk.bind_buffer_memory(device, buffer, buffer_memory, 0);
    std::printf("RAW_VK_BIND_BUFFER_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=bind-buffer result=%d\n", static_cast<int>(result));
        return false;
    }

    void* mapped = nullptr;
    result = vk.map_memory(device, buffer_memory, 0, VK_WHOLE_SIZE, 0, &mapped);
    std::printf("RAW_VK_MAP_BUFFER_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=map-buffer result=%d\n", static_cast<int>(result));
        return false;
    }
    std::memset(mapped, 0xa5, 4096);
    vk.unmap_memory(device, buffer_memory);

    VkImageCreateInfo image_info{};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = VK_FORMAT_R8G8B8A8_UNORM;
    image_info.extent = {1, 1, 1};
    image_info.mipLevels = 1;
    image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkImage image = VK_NULL_HANDLE;
    result = vk.create_image(device, &image_info, nullptr, &image);
    std::printf("RAW_VK_CREATE_IMAGE=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=create-image result=%d\n", static_cast<int>(result));
        return false;
    }

    VkMemoryRequirements image_requirements{};
    vk.get_image_memory_requirements(device, image, &image_requirements);
    int32_t image_type = find_memory_type(
        memory, image_requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (image_type < 0)
        image_type = find_memory_type(memory, image_requirements.memoryTypeBits, 0);
    VkMemoryAllocateInfo image_alloc{};
    image_alloc.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    image_alloc.allocationSize = image_requirements.size;
    image_alloc.memoryTypeIndex = static_cast<uint32_t>(image_type);
    VkDeviceMemory image_memory = VK_NULL_HANDLE;
    result = vk.allocate_memory(device, &image_alloc, nullptr, &image_memory);
    if (result != VK_SUCCESS || image_type < 0)
    {
        if (image_memory != VK_NULL_HANDLE)
            vk.free_memory(device, image_memory, nullptr);
        vk.destroy_image(device, image, nullptr);
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=alloc-image-memory result=%d\n", static_cast<int>(result));
        return false;
    }
    result = vk.bind_image_memory(device, image, image_memory, 0);
    std::printf("RAW_VK_BIND_IMAGE_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.free_memory(device, image_memory, nullptr);
        vk.destroy_image(device, image, nullptr);
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=bind-image result=%d\n", static_cast<int>(result));
        return false;
    }

    VkCommandPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pool_info.queueFamilyIndex = family;
    VkCommandPool pool = VK_NULL_HANDLE;
    result = vk.create_command_pool(device, &pool_info, nullptr, &pool);
    std::printf("RAW_VK_CREATE_COMMAND_POOL=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.free_memory(device, image_memory, nullptr);
        vk.destroy_image(device, image, nullptr);
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=create-command-pool result=%d\n", static_cast<int>(result));
        return false;
    }

    VkCommandBufferAllocateInfo command_info{};
    command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    command_info.commandPool = pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = requested_count;
    std::vector<VkCommandBuffer> commands(requested_count, VK_NULL_HANDLE);
    result = vk.allocate_command_buffers(device, &command_info, commands.data());
    std::printf("RAW_VK_ALLOCATE_COMMAND_BUFFERS=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.destroy_command_pool(device, pool, nullptr);
        vk.free_memory(device, image_memory, nullptr);
        vk.destroy_image(device, image, nullptr);
        vk.free_memory(device, buffer_memory, nullptr);
        vk.destroy_buffer(device, buffer, nullptr);
        vk.destroy_device(device, nullptr);
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=allocate-command-buffers result=%d\n", static_cast<int>(result));
        return false;
    }

    std::vector<VkQueue> queues(requested_count, VK_NULL_HANDLE);
    std::vector<VkFence> fences(requested_count, VK_NULL_HANDLE);
    for (uint32_t i = 0; i < requested_count; ++i)
    {
        vk.get_device_queue(device, family, i, &queues[i]);
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        result = vk.create_fence(device, &fence_info, nullptr, &fences[i]);
        if (result != VK_SUCCESS)
        {
            std::printf("RAW_VK_CREATE_FENCE=%u %d(%s)\n", i, static_cast<int>(result), result_name(result));
            for (uint32_t j = 0; j < fences.size(); ++j)
            {
                if (fences[j] != VK_NULL_HANDLE)
                    vk.destroy_fence(device, fences[j], nullptr);
            }
            vk.destroy_command_pool(device, pool, nullptr);
            vk.free_memory(device, image_memory, nullptr);
            vk.destroy_image(device, image, nullptr);
            vk.free_memory(device, buffer_memory, nullptr);
            vk.destroy_buffer(device, buffer, nullptr);
            vk.destroy_device(device, nullptr);
            std::printf("RAW_VK_CASE_RESULT=FAIL stage=create-fence result=%d\n", static_cast<int>(result));
            return false;
        }
    }

    for (uint32_t i = 0; i < requested_count; ++i)
    {
        VkCommandBufferBeginInfo begin_info{};
        begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        result = vk.begin_command_buffer(commands[i], &begin_info);
        std::printf("RAW_VK_BEGIN_COMMAND_BUFFER=%u %d(%s)\n", i, static_cast<int>(result), result_name(result));
        if (result == VK_SUCCESS)
        {
            result = vk.end_command_buffer(commands[i]);
            std::printf("RAW_VK_END_COMMAND_BUFFER=%u %d(%s)\n", i, static_cast<int>(result), result_name(result));
        }
        if (result != VK_SUCCESS)
        {
            for (VkFence fence : fences)
                vk.destroy_fence(device, fence, nullptr);
            vk.destroy_command_pool(device, pool, nullptr);
            vk.free_memory(device, image_memory, nullptr);
            vk.destroy_image(device, image, nullptr);
            vk.free_memory(device, buffer_memory, nullptr);
            vk.destroy_buffer(device, buffer, nullptr);
            vk.destroy_device(device, nullptr);
            std::printf("RAW_VK_CASE_RESULT=FAIL stage=record result=%d\n", static_cast<int>(result));
            return false;
        }
    }

    if (concurrent_submit)
    {
        for (uint32_t i = 0; i < requested_count; ++i)
        {
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &commands[i];
            result = vk.queue_submit(queues[i], 1, &submit, fences[i]);
            std::printf("RAW_VK_QUEUE_SUBMIT=%u %d(%s)\n", i, static_cast<int>(result), result_name(result));
            if (result != VK_SUCCESS)
                break;
        }
        if (result == VK_SUCCESS)
        {
            result = vk.wait_for_fences(device, requested_count, fences.data(), VK_TRUE, 60000000000ULL);
            std::printf("RAW_VK_WAIT_ALL_FENCES=%d(%s)\n", static_cast<int>(result), result_name(result));
        }
    }
    else
    {
        for (uint32_t i = 0; i < requested_count; ++i)
        {
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &commands[i];
            result = vk.queue_submit(queues[i], 1, &submit, fences[i]);
            std::printf("RAW_VK_QUEUE_SUBMIT=%u %d(%s)\n", i, static_cast<int>(result), result_name(result));
            if (result != VK_SUCCESS)
                break;
            VkResult wait_result = vk.wait_for_fences(device, 1, &fences[i], VK_TRUE, 60000000000ULL);
            std::printf("RAW_VK_WAIT_FENCE=%u %d(%s)\n", i, static_cast<int>(wait_result), result_name(wait_result));
            VkResult status = vk.get_fence_status(device, fences[i]);
            std::printf("RAW_VK_FENCE_STATUS=%u %d(%s)\n", i, static_cast<int>(status), result_name(status));
            if (result == VK_SUCCESS && wait_result == VK_SUCCESS && status == VK_SUCCESS)
                result = wait_result;
            else
            {
                result = result == VK_SUCCESS ? (wait_result != VK_SUCCESS ? wait_result : status) : result;
                break;
            }
        }
    }

    if (result == VK_SUCCESS)
    {
        result = vk.device_wait_idle(device);
        std::printf("RAW_VK_DEVICE_WAIT_IDLE=%d(%s)\n", static_cast<int>(result), result_name(result));
    }

    for (VkFence fence : fences)
        vk.destroy_fence(device, fence, nullptr);
    vk.destroy_command_pool(device, pool, nullptr);
    vk.free_memory(device, image_memory, nullptr);
    vk.destroy_image(device, image, nullptr);
    vk.free_memory(device, buffer_memory, nullptr);
    vk.destroy_buffer(device, buffer, nullptr);
    vk.destroy_device(device, nullptr);

    bool passed = result == VK_SUCCESS;
    std::printf(
        "RAW_VK_CASE_RESULT=%s stage=final result=%d(%s)\n",
        passed ? "PASS" : "FAIL", static_cast<int>(result), result_name(result));
    return passed;
}

bool create_case_device(
    const VulkanFunctions& vk,
    VkPhysicalDevice physical,
    uint32_t family,
    uint32_t requested_count,
    VkDevice* device,
    VkQueue* queue)
{
    std::vector<float> priorities(requested_count, 1.0f);
    VkDeviceQueueCreateInfo queue_info{};
    queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = requested_count;
    queue_info.pQueuePriorities = priorities.data();

    VkDeviceCreateInfo device_info{};
    device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;

    VkResult result = vk.create_device(physical, &device_info, nullptr, device);
    std::printf(
        "RAW_VK_CREATE_DEVICE=%d(%s)\n",
        static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
        return false;

    vk.get_device_queue(*device, family, 0, queue);
    return true;
}

bool record_empty_command(
    const VulkanFunctions& vk,
    VkDevice device,
    uint32_t family,
    VkCommandPool* pool,
    VkCommandBuffer* command,
    bool record_compute_barrier = false)
{
    VkCommandPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pool_info.queueFamilyIndex = family;
    VkResult result = vk.create_command_pool(device, &pool_info, nullptr, pool);
    std::printf(
        "RAW_VK_CREATE_COMMAND_POOL=%d(%s)\n",
        static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
        return false;

    VkCommandBufferAllocateInfo command_info{};
    command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    command_info.commandPool = *pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = 1;
    result = vk.allocate_command_buffers(device, &command_info, command);
    std::printf(
        "RAW_VK_ALLOCATE_COMMAND_BUFFERS=%d(%s)\n",
        static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        vk.destroy_command_pool(device, *pool, nullptr);
        *pool = VK_NULL_HANDLE;
        return false;
    }

    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    result = vk.begin_command_buffer(*command, &begin_info);
    std::printf(
        "RAW_VK_BEGIN_COMMAND_BUFFER=%d(%s)\n",
        static_cast<int>(result), result_name(result));
    if (result == VK_SUCCESS)
    {
        if (record_compute_barrier)
        {
            VkMemoryBarrier barrier{};
            barrier.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER;
            barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
            barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
            vk.cmd_pipeline_barrier(
                *command,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                0,
                1, &barrier,
                0, nullptr,
                0, nullptr);
            std::printf("RAW_VK_CMD_COMPUTE_BARRIER=0(VK_SUCCESS)\n");
        }
        result = vk.end_command_buffer(*command);
        std::printf(
            "RAW_VK_END_COMMAND_BUFFER=%d(%s)\n",
            static_cast<int>(result), result_name(result));
    }
    if (result != VK_SUCCESS)
    {
        vk.destroy_command_pool(device, *pool, nullptr);
        *pool = VK_NULL_HANDLE;
        *command = VK_NULL_HANDLE;
        return false;
    }
    return true;
}

bool run_compute_storage_case(
    const VulkanFunctions& vk,
    VkPhysicalDevice physical,
    uint32_t family,
    uint32_t requested_count,
    uint32_t case_index,
    bool minimal_shader,
    bool explicit_pipeline_cache)
{
    std::printf(
        "RAW_VK_CASE=%u mode=compute-storage-%s cache=%s family=%u requested_queues=%u\n",
        case_index,
        minimal_shader ? (explicit_pipeline_cache ? "minimal-explicit" : "minimal")
                       : "bounds-checked",
        explicit_pipeline_cache ? "explicit" : "null", family,
        requested_count);

    uint32_t element_count = 16384;
    uint32_t iteration_count = 1;
    if (const char* value = std::getenv("RAW_VK_COMPUTE_ELEMENTS"))
    {
        long parsed = std::strtol(value, nullptr, 10);
        if (parsed > 0 && parsed <= 16777216)
            element_count = static_cast<uint32_t>(parsed);
    }
    if (const char* value = std::getenv("RAW_VK_COMPUTE_ITERATIONS"))
    {
        long parsed = std::strtol(value, nullptr, 10);
        if (parsed > 0 && parsed <= 1000)
            iteration_count = static_cast<uint32_t>(parsed);
    }
    std::printf(
        "RAW_VK_COMPUTE_CONFIG elements=%u iterations=%u workgroup=64 bytes=%llu\n",
        element_count, iteration_count,
        static_cast<unsigned long long>(element_count) * sizeof(uint32_t));

    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    if (!create_case_device(vk, physical, family, requested_count, &device, &queue))
    {
        std::printf(
            "RAW_VK_CASE_RESULT=FAIL stage=create-device result=%d\n",
            static_cast<int>(VK_ERROR_INITIALIZATION_FAILED));
        return false;
    }

    VkPhysicalDeviceMemoryProperties memory{};
    vk.get_physical_device_memory_properties(physical, &memory);
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory_object = VK_NULL_HANDLE;
    VkDescriptorSetLayout set_layout = VK_NULL_HANDLE;
    VkShaderModule shader_module = VK_NULL_HANDLE;
    VkPipelineLayout pipeline_layout = VK_NULL_HANDLE;
    VkPipelineCache pipeline_cache = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkDescriptorPool descriptor_pool = VK_NULL_HANDLE;
    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;
    VkCommandPool command_pool = VK_NULL_HANDLE;
    VkCommandBuffer command = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    void* mapped = nullptr;
    const char* fail_stage = "final";
    VkResult result = VK_SUCCESS;

    const auto cleanup = [&]()
    {
        if (fence != VK_NULL_HANDLE)
            vk.destroy_fence(device, fence, nullptr);
        if (command_pool != VK_NULL_HANDLE)
            vk.destroy_command_pool(device, command_pool, nullptr);
        if (descriptor_pool != VK_NULL_HANDLE)
            vk.destroy_descriptor_pool(device, descriptor_pool, nullptr);
        if (pipeline != VK_NULL_HANDLE)
            vk.destroy_pipeline(device, pipeline, nullptr);
        if (pipeline_cache != VK_NULL_HANDLE)
            vk.destroy_pipeline_cache(device, pipeline_cache, nullptr);
        if (pipeline_layout != VK_NULL_HANDLE)
            vk.destroy_pipeline_layout(device, pipeline_layout, nullptr);
        if (shader_module != VK_NULL_HANDLE)
            vk.destroy_shader_module(device, shader_module, nullptr);
        if (set_layout != VK_NULL_HANDLE)
            vk.destroy_descriptor_set_layout(device, set_layout, nullptr);
        if (mapped != nullptr)
            vk.unmap_memory(device, memory_object);
        if (memory_object != VK_NULL_HANDLE)
            vk.free_memory(device, memory_object, nullptr);
        if (buffer != VK_NULL_HANDLE)
            vk.destroy_buffer(device, buffer, nullptr);
        if (device != VK_NULL_HANDLE)
            vk.destroy_device(device, nullptr);
    };

    VkBufferCreateInfo buffer_info{};
    buffer_info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    buffer_info.size = static_cast<VkDeviceSize>(element_count) * sizeof(uint32_t);
    buffer_info.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
    result = vk.create_buffer(device, &buffer_info, nullptr, &buffer);
    std::printf("RAW_VK_CREATE_COMPUTE_BUFFER=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-compute-buffer";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkMemoryRequirements requirements{};
    vk.get_buffer_memory_requirements(device, buffer, &requirements);
    const int32_t memory_type = find_memory_type(
        memory, requirements.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    std::printf(
        "RAW_VK_COMPUTE_MEMORY_TYPE=%d size=%llu alignment=%llu type_bits=0x%x\n",
        memory_type,
        static_cast<unsigned long long>(requirements.size),
        static_cast<unsigned long long>(requirements.alignment),
        requirements.memoryTypeBits);
    if (memory_type < 0)
    {
        fail_stage = "find-compute-memory";
        result = VK_ERROR_INITIALIZATION_FAILED;
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkMemoryAllocateInfo allocation_info{};
    allocation_info.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocation_info.allocationSize = requirements.size;
    allocation_info.memoryTypeIndex = static_cast<uint32_t>(memory_type);
    result = vk.allocate_memory(device, &allocation_info, nullptr, &memory_object);
    std::printf("RAW_VK_ALLOC_COMPUTE_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "alloc-compute-memory";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }
    result = vk.bind_buffer_memory(device, buffer, memory_object, 0);
    std::printf("RAW_VK_BIND_COMPUTE_BUFFER=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "bind-compute-buffer";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }
    result = vk.map_memory(device, memory_object, 0, VK_WHOLE_SIZE, 0, &mapped);
    if (result == VK_SUCCESS)
        std::memset(mapped, 0, static_cast<size_t>(element_count) * sizeof(uint32_t));
    if (mapped != nullptr)
    {
        vk.unmap_memory(device, memory_object);
        mapped = nullptr;
    }
    std::printf("RAW_VK_INIT_COMPUTE_MEMORY=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "init-compute-memory";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkDescriptorSetLayoutBinding layout_binding{};
    layout_binding.binding = 0;
    layout_binding.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    layout_binding.descriptorCount = 1;
    layout_binding.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo set_layout_info{};
    set_layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    set_layout_info.bindingCount = 1;
    set_layout_info.pBindings = &layout_binding;
    result = vk.create_descriptor_set_layout(device, &set_layout_info, nullptr, &set_layout);
    std::printf("RAW_VK_CREATE_DESCRIPTOR_LAYOUT=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-descriptor-layout";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    const std::vector<uint32_t> spirv = decode_spirv_words(
        minimal_shader ? k_raw_vk_minimal_storage_spirv_hex
                       : k_raw_vk_compute_spirv_hex);
    VkShaderModuleCreateInfo shader_info{};
    shader_info.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
    shader_info.codeSize = spirv.size() * sizeof(uint32_t);
    shader_info.pCode = spirv.data();
    result = vk.create_shader_module(device, &shader_info, nullptr, &shader_module);
    std::printf(
        "RAW_VK_CREATE_SHADER_MODULE=%d(%s) words=%zu\n",
        static_cast<int>(result), result_name(result), spirv.size());
    if (result != VK_SUCCESS || spirv.empty())
    {
        fail_stage = "create-shader-module";
        if (result == VK_SUCCESS)
            result = VK_ERROR_INITIALIZATION_FAILED;
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkPipelineLayoutCreateInfo pipeline_layout_info{};
    pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
    pipeline_layout_info.setLayoutCount = 1;
    pipeline_layout_info.pSetLayouts = &set_layout;
    result = vk.create_pipeline_layout(device, &pipeline_layout_info, nullptr, &pipeline_layout);
    std::printf("RAW_VK_CREATE_PIPELINE_LAYOUT=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-pipeline-layout";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    if (explicit_pipeline_cache)
    {
        VkPipelineCacheCreateInfo cache_info{};
        cache_info.sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO;
        result = vk.create_pipeline_cache(device, &cache_info, nullptr, &pipeline_cache);
        std::printf(
            "RAW_VK_CREATE_PIPELINE_CACHE=%d(%s)\n",
            static_cast<int>(result), result_name(result));
        if (result != VK_SUCCESS)
        {
            fail_stage = "create-pipeline-cache";
            cleanup();
            std::printf(
                "RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n",
                fail_stage, static_cast<int>(result));
            return false;
        }
    }

    VkComputePipelineCreateInfo pipeline_info{};
    pipeline_info.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
    pipeline_info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    pipeline_info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    pipeline_info.stage.module = shader_module;
    pipeline_info.stage.pName = "main";
    pipeline_info.layout = pipeline_layout;
    result = vk.create_compute_pipelines(
        device, explicit_pipeline_cache ? pipeline_cache : VK_NULL_HANDLE,
        1, &pipeline_info, nullptr, &pipeline);
    std::printf("RAW_VK_CREATE_COMPUTE_PIPELINE=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-compute-pipeline";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkDescriptorPoolSize pool_size{};
    pool_size.type = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    pool_size.descriptorCount = 1;
    VkDescriptorPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    pool_info.maxSets = 1;
    pool_info.poolSizeCount = 1;
    pool_info.pPoolSizes = &pool_size;
    result = vk.create_descriptor_pool(device, &pool_info, nullptr, &descriptor_pool);
    std::printf("RAW_VK_CREATE_DESCRIPTOR_POOL=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-descriptor-pool";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkDescriptorSetAllocateInfo set_info{};
    set_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    set_info.descriptorPool = descriptor_pool;
    set_info.descriptorSetCount = 1;
    set_info.pSetLayouts = &set_layout;
    result = vk.allocate_descriptor_sets(device, &set_info, &descriptor_set);
    std::printf("RAW_VK_ALLOCATE_DESCRIPTOR_SET=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "allocate-descriptor-set";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkDescriptorBufferInfo buffer_descriptor{};
    buffer_descriptor.buffer = buffer;
    buffer_descriptor.offset = 0;
    buffer_descriptor.range = buffer_info.size;
    VkWriteDescriptorSet descriptor_write{};
    descriptor_write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    descriptor_write.dstSet = descriptor_set;
    descriptor_write.dstBinding = 0;
    descriptor_write.descriptorCount = 1;
    descriptor_write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    descriptor_write.pBufferInfo = &buffer_descriptor;
    vk.update_descriptor_sets(device, 1, &descriptor_write, 0, nullptr);
    std::printf("RAW_VK_UPDATE_DESCRIPTOR_SET=0(VK_SUCCESS)\n");

    VkCommandPoolCreateInfo command_pool_info{};
    command_pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    command_pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    command_pool_info.queueFamilyIndex = family;
    result = vk.create_command_pool(device, &command_pool_info, nullptr, &command_pool);
    std::printf("RAW_VK_CREATE_COMMAND_POOL=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-command-pool";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkCommandBufferAllocateInfo command_info{};
    command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    command_info.commandPool = command_pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = 1;
    result = vk.allocate_command_buffers(device, &command_info, &command);
    std::printf("RAW_VK_ALLOCATE_COMMAND_BUFFERS=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "allocate-command-buffers";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    result = vk.begin_command_buffer(command, &begin_info);
    std::printf("RAW_VK_BEGIN_COMMAND_BUFFER=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result == VK_SUCCESS)
    {
        vk.cmd_bind_pipeline(command, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        vk.cmd_bind_descriptor_sets(
            command, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline_layout,
            0, 1, &descriptor_set, 0, nullptr);
        vk.cmd_dispatch(command, (element_count + 63u) / 64u, 1, 1);
        std::printf("RAW_VK_CMD_COMPUTE_DISPATCH=%u\n", (element_count + 63u) / 64u);
        result = vk.end_command_buffer(command);
        std::printf("RAW_VK_END_COMMAND_BUFFER=%d(%s)\n", static_cast<int>(result), result_name(result));
    }
    if (result != VK_SUCCESS)
    {
        fail_stage = "record-compute-command";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    VkFenceCreateInfo fence_info{};
    fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    result = vk.create_fence(device, &fence_info, nullptr, &fence);
    std::printf("RAW_VK_CREATE_FENCE=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        fail_stage = "create-fence";
        cleanup();
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=%s result=%d\n", fail_stage, static_cast<int>(result));
        return false;
    }

    for (uint32_t iteration = 1; iteration <= iteration_count && result == VK_SUCCESS; ++iteration)
    {
        result = vk.reset_fences(device, 1, &fence);
        if (result == VK_SUCCESS)
        {
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &command;
            result = vk.queue_submit(queue, 1, &submit, fence);
            std::printf(
                "RAW_VK_COMPUTE_SUBMIT=%u %d(%s)\n",
                iteration, static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            const VkResult wait_result = vk.wait_for_fences(
                device, 1, &fence, VK_TRUE, 60000000000ULL);
            std::printf(
                "RAW_VK_COMPUTE_WAIT_FENCE=%u %d(%s)\n",
                iteration, static_cast<int>(wait_result), result_name(wait_result));
            if (wait_result != VK_SUCCESS)
                result = wait_result;
        }
        if (result == VK_SUCCESS)
        {
            const VkResult status = vk.get_fence_status(device, fence);
            std::printf(
                "RAW_VK_COMPUTE_FENCE_STATUS=%u %d(%s)\n",
                iteration, static_cast<int>(status), result_name(status));
            if (status != VK_SUCCESS)
                result = status;
        }
        if (result == VK_SUCCESS)
        {
            result = vk.map_memory(device, memory_object, 0, VK_WHOLE_SIZE, 0, &mapped);
            if (result == VK_SUCCESS)
            {
                const auto* values = static_cast<const uint32_t*>(mapped);
                uint32_t mismatches = 0;
                for (uint32_t i = 0; i < element_count && mismatches < 8; ++i)
                {
                    if (values[i] != iteration)
                        ++mismatches;
                }
                vk.unmap_memory(device, memory_object);
                mapped = nullptr;
                std::printf(
                    "RAW_VK_COMPUTE_CHECK=%u result=%s mismatches_tail=%u expected=%u\n",
                    iteration, mismatches == 0 ? "PASS" : "FAIL", mismatches, iteration);
                if (mismatches != 0)
                    result = VK_ERROR_DEVICE_LOST;
            }
            else
            {
                std::printf(
                    "RAW_VK_COMPUTE_MAP=%u %d(%s)\n",
                    iteration, static_cast<int>(result), result_name(result));
            }
        }
    }

    if (result == VK_SUCCESS)
    {
        result = vk.device_wait_idle(device);
        std::printf("RAW_VK_DEVICE_WAIT_IDLE=%d(%s)\n", static_cast<int>(result), result_name(result));
    }
    if (result != VK_SUCCESS)
        fail_stage = "compute-submit-or-check";

    cleanup();
    const bool passed = result == VK_SUCCESS;
    std::printf(
        "RAW_VK_CASE_RESULT=%s stage=%s result=%d(%s)\n",
        passed ? "PASS" : "FAIL", fail_stage,
        static_cast<int>(result), result_name(result));
    return passed;
}

bool run_reduction_case(
    const VulkanFunctions& vk,
    VkPhysicalDevice physical,
    uint32_t family,
    uint32_t requested_count,
    const char* case_name,
    bool concurrent_submit,
    uint32_t case_index)
{
    (void)concurrent_submit;
    std::printf(
        "RAW_VK_CASE=%u mode=%s family=%u requested_queues=%u\n",
        case_index, case_name, family, requested_count);

    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    if (!create_case_device(vk, physical, family, requested_count, &device, &queue))
    {
        std::printf(
            "RAW_VK_CASE_RESULT=FAIL stage=create-device result=%d\n",
            static_cast<int>(VK_ERROR_INITIALIZATION_FAILED));
        return false;
    }

    VkResult result = VK_SUCCESS;
    VkFence fence = VK_NULL_HANDLE;
    VkSemaphore semaphore = VK_NULL_HANDLE;
    VkCommandPool command_pool = VK_NULL_HANDLE;
    VkCommandBuffer command = VK_NULL_HANDLE;

    if (std::strcmp(case_name, "device-only") == 0)
    {
        std::printf("RAW_VK_DEVICE_ONLY=PASS\n");
    }
    else if (std::strcmp(case_name, "queue-wait-idle") == 0)
    {
        result = vk.queue_wait_idle(queue);
        std::printf(
            "RAW_VK_QUEUE_WAIT_IDLE=%d(%s)\n",
            static_cast<int>(result), result_name(result));
    }
    else if (std::strcmp(case_name, "device-wait-idle") == 0)
    {
        result = vk.device_wait_idle(device);
        std::printf(
            "RAW_VK_DEVICE_WAIT_IDLE=%d(%s)\n",
            static_cast<int>(result), result_name(result));
    }
    else if (std::strcmp(case_name, "fence-signaled") == 0)
    {
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        result = vk.create_fence(device, &fence_info, nullptr, &fence);
        std::printf(
            "RAW_VK_CREATE_SIGNALED_FENCE=%d(%s)\n",
            static_cast<int>(result), result_name(result));
        if (result == VK_SUCCESS)
        {
            result = vk.wait_for_fences(device, 1, &fence, VK_TRUE, 60000000000ULL);
            std::printf(
                "RAW_VK_WAIT_SIGNALED_FENCE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            result = vk.reset_fences(device, 1, &fence);
            std::printf(
                "RAW_VK_RESET_FENCE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            const VkResult reset_status = vk.get_fence_status(device, fence);
            std::printf(
                "RAW_VK_RESET_FENCE_STATUS=%d(%s)\n",
                static_cast<int>(reset_status), result_name(reset_status));
            // A successfully reset fence is unsignaled, so VK_NOT_READY is
            // the expected lifecycle result rather than a probe failure.
            result =
                reset_status == VK_NOT_READY ? VK_SUCCESS : reset_status;
        }
    }
    else if (std::strcmp(case_name, "fence-only-submit") == 0)
    {
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        result = vk.create_fence(device, &fence_info, nullptr, &fence);
        std::printf(
            "RAW_VK_CREATE_FENCE=%d(%s)\n",
            static_cast<int>(result), result_name(result));
        if (result == VK_SUCCESS)
        {
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 0;
            result = vk.queue_submit(queue, 1, &submit, fence);
            std::printf(
                "RAW_VK_QUEUE_SUBMIT_FENCE_ONLY=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            result = vk.wait_for_fences(device, 1, &fence, VK_TRUE, 60000000000ULL);
            std::printf(
                "RAW_VK_WAIT_FENCE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            result = vk.get_fence_status(device, fence);
            std::printf(
                "RAW_VK_FENCE_STATUS=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
    }
    else if (
        std::strcmp(case_name, "empty-cmd-nofence") == 0 ||
        std::strcmp(case_name, "empty-cmd-fence") == 0 ||
        std::strcmp(case_name, "empty-cmd-semaphore") == 0 ||
        std::strcmp(case_name, "barrier-cmd-nofence") == 0 ||
        std::strcmp(case_name, "barrier-cmd-fence") == 0)
    {
        const bool compute_barrier =
            std::strcmp(case_name, "barrier-cmd-nofence") == 0 ||
            std::strcmp(case_name, "barrier-cmd-fence") == 0;
        if (!record_empty_command(
                vk, device, family, &command_pool, &command, compute_barrier))
        {
            std::printf(
                "RAW_VK_CASE_RESULT=FAIL stage=record result=%d\n",
                static_cast<int>(VK_ERROR_INITIALIZATION_FAILED));
            vk.destroy_device(device, nullptr);
            return false;
        }

        if (std::strcmp(case_name, "empty-cmd-fence") == 0 ||
            std::strcmp(case_name, "barrier-cmd-fence") == 0)
        {
            VkFenceCreateInfo fence_info{};
            fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
            result = vk.create_fence(device, &fence_info, nullptr, &fence);
            std::printf(
                "RAW_VK_CREATE_FENCE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS &&
            std::strcmp(case_name, "empty-cmd-semaphore") == 0)
        {
            VkSemaphoreCreateInfo semaphore_info{};
            semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
            result = vk.create_semaphore(device, &semaphore_info, nullptr, &semaphore);
            std::printf(
                "RAW_VK_CREATE_SEMAPHORE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS)
        {
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &command;
            if (semaphore != VK_NULL_HANDLE)
            {
                submit.signalSemaphoreCount = 1;
                submit.pSignalSemaphores = &semaphore;
            }
            result = vk.queue_submit(
                queue, 1, &submit,
                fence != VK_NULL_HANDLE ? fence : VK_NULL_HANDLE);
            std::printf(
                "RAW_VK_QUEUE_SUBMIT=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS && fence != VK_NULL_HANDLE)
        {
            result = vk.wait_for_fences(device, 1, &fence, VK_TRUE, 60000000000ULL);
            std::printf(
                "RAW_VK_WAIT_FENCE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS && fence == VK_NULL_HANDLE)
        {
            result = vk.queue_wait_idle(queue);
            std::printf(
                "RAW_VK_QUEUE_WAIT_IDLE=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
        if (result == VK_SUCCESS && fence != VK_NULL_HANDLE)
        {
            result = vk.get_fence_status(device, fence);
            std::printf(
                "RAW_VK_FENCE_STATUS=%d(%s)\n",
                static_cast<int>(result), result_name(result));
        }
    }
    else
    {
        std::printf("RAW_VK_CASE_RESULT=FAIL stage=unknown-case\n");
        vk.destroy_device(device, nullptr);
        return false;
    }

    if (fence != VK_NULL_HANDLE)
        vk.destroy_fence(device, fence, nullptr);
    if (semaphore != VK_NULL_HANDLE)
        vk.destroy_semaphore(device, semaphore, nullptr);
    if (command_pool != VK_NULL_HANDLE)
        vk.destroy_command_pool(device, command_pool, nullptr);
    vk.destroy_device(device, nullptr);

    bool passed = result == VK_SUCCESS;
    std::printf(
        "RAW_VK_CASE_RESULT=%s stage=final result=%d(%s)\n",
        passed ? "PASS" : "FAIL", static_cast<int>(result), result_name(result));
    return passed;
}

bool is_supported_reduction_case(const char* name)
{
    return std::strcmp(name, "device-only") == 0 ||
           std::strcmp(name, "queue-wait-idle") == 0 ||
           std::strcmp(name, "device-wait-idle") == 0 ||
           std::strcmp(name, "fence-signaled") == 0 ||
           std::strcmp(name, "fence-only-submit") == 0 ||
           std::strcmp(name, "empty-cmd-nofence") == 0 ||
           std::strcmp(name, "empty-cmd-fence") == 0 ||
           std::strcmp(name, "empty-cmd-semaphore") == 0 ||
           std::strcmp(name, "barrier-cmd-nofence") == 0 ||
           std::strcmp(name, "barrier-cmd-fence") == 0 ||
           std::strcmp(name, "compute-storage") == 0 ||
           std::strcmp(name, "compute-storage-min") == 0 ||
           std::strcmp(name, "compute-storage-cache") == 0 ||
           std::strcmp(name, "full") == 0;
}

} // namespace

int main()
{
    // Shared Firecracker runs pipe stdout into the guest wrapper.  Without
    // this, a probe crash can lose the last stage marker needed for triage.
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    const char* driver = std::getenv("NCNN_VULKAN_DRIVER");
    const char* queue_spec = std::getenv("RAW_VK_QUEUE_COUNTS");
    const char* submit_mode = std::getenv("RAW_VK_SUBMIT_MODE");
    const char* case_name = std::getenv("RAW_VK_CASE");
    if (!queue_spec || !queue_spec[0])
        queue_spec = "1,2,3";
    if (!case_name || !case_name[0])
        case_name = "full";
    bool concurrent_submit = submit_mode && std::strcmp(submit_mode, "concurrent") == 0;

    std::printf("RAW_VK_DRIVER=%s\n", driver ? driver : "libvulkan.so.1");
    std::printf("RAW_VK_QUEUE_COUNTS=%s\n", queue_spec);
    std::printf("RAW_VK_SUBMIT_MODE=%s\n", concurrent_submit ? "concurrent" : "sequential");
    std::printf("RAW_VK_CASE=%s\n", case_name);
    if (!is_supported_reduction_case(case_name))
    {
        std::printf("RAW_VK_RESULT=FAIL reason=unknown-case case=%s\n", case_name);
        return 2;
    }

    void* library = nullptr;
    PFN_vkGetInstanceProcAddr instance_proc = load_instance_proc(driver, &library);
    Dl_info driver_info{};
    if (dladdr(reinterpret_cast<void*>(instance_proc), &driver_info) && driver_info.dli_fbase)
        std::printf("RAW_VK_DRIVER_BASE=%p\n", driver_info.dli_fbase);
    if (!instance_proc)
    {
        std::printf("RAW_VK_RESULT=FAIL reason=driver-load\n");
        return 2;
    }

    auto create_instance = reinterpret_cast<PFN_vkCreateInstance>(
        instance_proc(nullptr, "vkCreateInstance"));
    if (!create_instance)
    {
        std::printf("RAW_VK_RESULT=FAIL reason=vkCreateInstance-proc\n");
        dlclose(library);
        return 2;
    }

    VkApplicationInfo app{};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = "raw-vk-probe";
    app.pEngineName = "raw-vk-probe";
    app.apiVersion = VK_API_VERSION_1_0;
    VkInstanceCreateInfo instance_info{};
    instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    instance_info.pApplicationInfo = &app;
    VkInstance instance = VK_NULL_HANDLE;
    VkResult result = create_instance(&instance_info, nullptr, &instance);
    std::printf("RAW_VK_CREATE_INSTANCE=%d(%s)\n", static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS)
    {
        std::printf("RAW_VK_RESULT=FAIL reason=create-instance result=%d\n", static_cast<int>(result));
        dlclose(library);
        return 3;
    }

    VulkanFunctions vk{};
    if (!load_functions(instance_proc, instance, vk))
    {
        vk.destroy_device = reinterpret_cast<PFN_vkDestroyDevice>(instance_proc(instance, "vkDestroyDevice"));
        auto destroy_instance = reinterpret_cast<PFN_vkDestroyInstance>(instance_proc(instance, "vkDestroyInstance"));
        if (destroy_instance)
            destroy_instance(instance, nullptr);
        dlclose(library);
        std::printf("RAW_VK_RESULT=FAIL reason=missing-proc\n");
        return 4;
    }

    uint32_t physical_count = 0;
    result = vk.enumerate_physical_devices(instance, &physical_count, nullptr);
    std::printf("RAW_VK_PHYSICAL_COUNT=%u enum=%d(%s)\n", physical_count, static_cast<int>(result), result_name(result));
    if (result != VK_SUCCESS || physical_count == 0)
    {
        auto destroy_instance = reinterpret_cast<PFN_vkDestroyInstance>(instance_proc(instance, "vkDestroyInstance"));
        if (destroy_instance)
            destroy_instance(instance, nullptr);
        dlclose(library);
        std::printf("RAW_VK_RESULT=FAIL reason=physical-devices result=%d\n", static_cast<int>(result));
        return 5;
    }

    std::vector<VkPhysicalDevice> physicals(physical_count);
    result = vk.enumerate_physical_devices(instance, &physical_count, physicals.data());
    if (result != VK_SUCCESS)
    {
        auto destroy_instance = reinterpret_cast<PFN_vkDestroyInstance>(instance_proc(instance, "vkDestroyInstance"));
        if (destroy_instance)
            destroy_instance(instance, nullptr);
        dlclose(library);
        std::printf("RAW_VK_RESULT=FAIL reason=physical-enumerate result=%d\n", static_cast<int>(result));
        return 6;
    }

    VkPhysicalDevice physical = physicals[0];
    VkPhysicalDeviceProperties properties{};
    vk.get_physical_device_properties(physical, &properties);
    std::printf(
        "RAW_VK_DEVICE_NAME=%s api=%u.%u.%u driver=%u vendor=0x%x device=0x%x type=%u\n",
        properties.deviceName,
        VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion),
        VK_VERSION_PATCH(properties.apiVersion), properties.driverVersion,
        properties.vendorID, properties.deviceID, properties.deviceType);

    uint32_t available_queue_count = 0;
    uint32_t family = choose_compute_family(
        vk.get_queue_family_properties, physical, &available_queue_count);
    std::printf("RAW_VK_COMPUTE_FAMILY=%u available=%u\n", family, available_queue_count);
    if (family == UINT32_MAX || available_queue_count == 0)
    {
        auto destroy_instance = reinterpret_cast<PFN_vkDestroyInstance>(instance_proc(instance, "vkDestroyInstance"));
        if (destroy_instance)
            destroy_instance(instance, nullptr);
        dlclose(library);
        std::printf("RAW_VK_RESULT=FAIL reason=no-compute-queue\n");
        return 7;
    }

    std::vector<uint32_t> requested_counts;
    std::string spec(queue_spec);
    size_t begin = 0;
    while (begin <= spec.size())
    {
        size_t end = spec.find(',', begin);
        if (end == std::string::npos)
            end = spec.size();
        if (end > begin)
        {
            long value = std::strtol(spec.substr(begin, end - begin).c_str(), nullptr, 10);
            if (value > 0 && static_cast<uint32_t>(value) <= available_queue_count)
                requested_counts.push_back(static_cast<uint32_t>(value));
            else
                std::printf("RAW_VK_SKIP_QUEUE_COUNT=%ld available=%u\n", value, available_queue_count);
        }
        if (end == spec.size())
            break;
        begin = end + 1;
    }

    bool all_pass = !requested_counts.empty();
    uint32_t case_index = 0;
    for (uint32_t count : requested_counts)
    {
        const bool case_pass =
            std::strcmp(case_name, "full") == 0
                ? run_queue_case(
                      vk, physical, family, count, concurrent_submit, case_index++)
                : std::strcmp(case_name, "compute-storage") == 0
                    ? run_compute_storage_case(
                      vk, physical, family, count, case_index++, false, false)
                : std::strcmp(case_name, "compute-storage-min") == 0
                    ? run_compute_storage_case(
                          vk, physical, family, count, case_index++, true, false)
                : std::strcmp(case_name, "compute-storage-cache") == 0
                    ? run_compute_storage_case(
                          vk, physical, family, count, case_index++, true, true)
                : run_reduction_case(
                      vk, physical, family, count, case_name, concurrent_submit, case_index++);
        all_pass = case_pass && all_pass;
    }

    auto destroy_instance = reinterpret_cast<PFN_vkDestroyInstance>(instance_proc(instance, "vkDestroyInstance"));
    if (destroy_instance)
        destroy_instance(instance, nullptr);
    dlclose(library);

    std::printf("RAW_VK_RESULT=%s cases=%zu\n", all_pass ? "PASS" : "FAIL", requested_counts.size());
    return all_pass ? 0 : 10;
}
