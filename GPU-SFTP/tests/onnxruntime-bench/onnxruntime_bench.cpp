#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>

namespace {

using Clock = std::chrono::steady_clock;

double elapsed_us(Clock::time_point begin, Clock::time_point end)
{
    return std::chrono::duration<double, std::micro>(end - begin).count();
}

std::string shape_string(const std::vector<std::int64_t>& shape)
{
    std::string out = "[";
    for (size_t i = 0; i < shape.size(); ++i) {
        if (i != 0) out += ",";
        out += std::to_string(shape[i]);
    }
    out += "]";
    return out;
}

std::vector<std::int64_t> parse_shape(const std::string& text)
{
    if (text.empty()) return {};
    if (text.front() != '[' || text.back() != ']')
        throw std::runtime_error("input shape must look like [1,3,224,224]: " + text);
    std::vector<std::int64_t> shape;
    size_t begin = 1;
    while (begin < text.size()) {
        const size_t comma = text.find(',', begin);
        const size_t end = comma == std::string::npos ? text.size() - 1 : comma;
        if (begin >= end) throw std::runtime_error("empty input dimension in " + text);
        const std::string field = text.substr(begin, end - begin);
        size_t used = 0;
        const long long value = std::stoll(field, &used);
        if (used != field.size()) throw std::runtime_error("invalid input dimension '" + field + "'");
        shape.push_back(value);
        begin = comma == std::string::npos ? text.size() : comma + 1;
    }
    if (shape.empty()) throw std::runtime_error("empty input shape");
    return shape;
}

std::vector<std::int64_t> input_shape(const Ort::Session& session, size_t index, const std::string& model,
                                      const std::vector<std::int64_t>& override_shape)
{
    auto type_info = session.GetInputTypeInfo(index);
    auto tensor_info = type_info.GetTensorTypeAndShapeInfo();
    if (tensor_info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
        throw std::runtime_error("input " + std::to_string(index) + " is not float32");
    }
    auto shape = tensor_info.GetShape();
    const auto raw_shape = shape;
    if (!override_shape.empty()) {
        shape = override_shape;
    } else if (shape.size() == 4 &&
        std::any_of(shape.begin(), shape.end(), [](std::int64_t d) { return d <= 0; }) &&
        model.find("mobilenet") != std::string::npos) {
        shape = {1, 3, 224, 224};
    }
    size_t count = 1;
    for (auto d : shape) {
        if (d <= 0) throw std::runtime_error("dynamic or invalid input dimension " + std::to_string(d));
        if (static_cast<uint64_t>(d) > std::numeric_limits<size_t>::max() / count) throw std::runtime_error("input shape overflow");
        count *= static_cast<size_t>(d);
    }
    if (count == 0 || count > (256U << 20)) throw std::runtime_error("input element count out of range");
    std::fprintf(stderr, "INPUT[%zu] raw_shape=%s used_shape=%s\n", index,
                 shape_string(raw_shape).c_str(), shape_string(shape).c_str());
    return shape;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc < 2 || argc > 6) {
        std::fprintf(stderr, "usage: %s model.onnx [measured_loops=30] [warmup_loops=5] [threads=2] [input_shape=auto]\n", argv[0]);
        return 2;
    }

    const std::string model = argv[1];
    const int measured = argc > 2 ? std::atoi(argv[2]) : 30;
    const int warmup = argc > 3 ? std::atoi(argv[3]) : 5;
    const int threads = argc > 4 ? std::atoi(argv[4]) : 2;
    const auto override_shape = parse_shape(argc > 5 ? argv[5] : "");
    if (measured <= 0 || warmup < 0 || threads <= 0) {
        std::fprintf(stderr, "invalid loop or thread count\n");
        return 2;
    }

    try {
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "onnxruntime-native-bench");
        std::printf("ONNXRUNTIME_VERSION=%s\n", OrtGetApiBase()->GetVersionString());
        std::printf("MODEL_PATH=%s\n", model.c_str());
        std::printf("MODEL_BYTES=%lld\n", static_cast<long long>(std::ifstream(model, std::ios::binary | std::ios::ate).tellg()));
        std::printf("MEASURED_LOOPS=%d WARMUP_LOOPS=%d THREADS=%d\n", measured, warmup, threads);
        std::printf("INPUT_SHAPE_OVERRIDE=%s\n", override_shape.empty() ? "auto" : shape_string(override_shape).c_str());
        std::printf("REQUESTED_BACKEND=CPU_DEFAULT NO_GPU_EXECUTION_PROVIDER_FOR_PANTHOR\n");

        std::vector<std::string> available;
        try {
            available = Ort::GetAvailableProviders();
        } catch (const Ort::Exception& e) {
            std::printf("AVAILABLE_PROVIDERS_QUERY_ERROR=%s\n", e.what());
        }
        std::string provider_list;
        for (size_t i = 0; i < available.size(); ++i) {
            if (i != 0) provider_list += ",";
            provider_list += available[i];
        }
        std::printf("AVAILABLE_PROVIDERS=%s\n", provider_list.c_str());

        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(threads);
        options.SetInterOpNumThreads(1);
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        const auto load_begin = Clock::now();
        Ort::Session session(env, model.c_str(), options);
        const auto load_end = Clock::now();

        Ort::AllocatorWithDefaultOptions allocator;
        std::vector<std::string> input_names;
        std::vector<std::string> output_names;
        std::vector<std::vector<std::int64_t>> input_shapes;
        std::vector<std::vector<float>> input_storage;
        std::vector<Ort::Value> inputs;

        for (size_t i = 0; i < session.GetInputCount(); ++i) {
            input_names.emplace_back(session.GetInputNameAllocated(i, allocator).get());
            auto shape = input_shape(session, i, model, override_shape);
            size_t count = 1;
            for (auto d : shape) count *= static_cast<size_t>(d);
            std::vector<float> values(count);
            for (size_t j = 0; j < count; ++j) {
                values[j] = ((static_cast<int>(j % 251) - 125) / 128.0f);
            }
            input_shapes.push_back(shape);
            input_storage.push_back(std::move(values));
        }
        for (size_t i = 0; i < session.GetOutputCount(); ++i) {
            output_names.emplace_back(session.GetOutputNameAllocated(i, allocator).get());
            auto type_info = session.GetOutputTypeInfo(i);
            auto tensor_info = type_info.GetTensorTypeAndShapeInfo();
            std::printf("OUTPUT[%zu] name=%s type=%d shape=%s\n", i, output_names.back().c_str(),
                        static_cast<int>(tensor_info.GetElementType()),
                        shape_string(tensor_info.GetShape()).c_str());
        }

        auto memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        for (size_t i = 0; i < input_names.size(); ++i) {
            std::printf("INPUT[%zu] name=%s shape=%s bytes=%zu\n", i, input_names[i].c_str(),
                        shape_string(input_shapes[i]).c_str(), input_storage[i].size() * sizeof(float));
            inputs.push_back(Ort::Value::CreateTensor<float>(
                memory_info, input_storage[i].data(), input_storage[i].size(),
                input_shapes[i].data(), input_shapes[i].size()));
        }
        std::vector<const char*> input_c_names;
        std::vector<const char*> output_c_names;
        for (const auto& name : input_names) input_c_names.push_back(name.c_str());
        for (const auto& name : output_names) output_c_names.push_back(name.c_str());

        Ort::RunOptions run_options;
        for (int i = 0; i < warmup; ++i) {
            auto outputs = session.Run(run_options, input_c_names.data(), inputs.data(), inputs.size(),
                                       output_c_names.data(), output_c_names.size());
        }

        std::vector<double> samples;
        samples.reserve(static_cast<size_t>(measured));
        std::vector<Ort::Value> final_outputs;
        for (int i = 0; i < measured; ++i) {
            const auto begin = Clock::now();
            auto outputs = session.Run(run_options, input_c_names.data(), inputs.data(), inputs.size(),
                                       output_c_names.data(), output_c_names.size());
            const auto end = Clock::now();
            samples.push_back(elapsed_us(begin, end));
            if (i + 1 == measured) final_outputs = std::move(outputs);
        }

        bool finite = true;
        long double checksum = 0.0L;
        size_t output_elements = 0;
        for (const auto& output : final_outputs) {
            auto info = output.GetTensorTypeAndShapeInfo();
            const size_t count = info.GetElementCount();
            const float* first = output.GetTensorData<float>();
            for (size_t i = 0; i < count; ++i) {
                if (!std::isfinite(first[i])) finite = false;
                checksum += static_cast<long double>(first[i]);
                ++output_elements;
            }
        }
        const auto [min_it, max_it] = std::minmax_element(samples.begin(), samples.end());
        const double mean = std::accumulate(samples.begin(), samples.end(), 0.0) / samples.size();
        std::printf("LOAD_MS=%.3f\n", elapsed_us(load_begin, load_end) / 1000.0);
        std::printf("ITER_COUNT=%zu ITER_US_MIN=%.2f ITER_US_MAX=%.2f ITER_US_MEAN=%.2f\n",
                    samples.size(), *min_it, *max_it, mean);
        std::printf("OUTPUT_ELEMENTS=%zu OUTPUT_ALL_FINITE=%s OUTPUT_SUM=%.9Lf\n",
                    output_elements, finite ? "yes" : "no", checksum);
        std::printf("ACTUAL_BACKEND=CPU EXECUTION_FALLBACK_FROM_GPU=YES\n");
        std::printf("ONNXRUNTIME_RESULT=%s\n", finite && output_elements > 0 ? "PASS" : "FAIL");
        return finite && output_elements > 0 ? 0 : 1;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "ONNXRUNTIME_EXCEPTION=%s\n", e.what());
        std::printf("ONNXRUNTIME_RESULT=FAIL\n");
        return 1;
    }
}
