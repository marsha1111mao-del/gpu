# GPU Passthrough Optimization Log

本文档只记录清零之后的重要 GPU passthrough 优化和测试结论。历史长篇 attempt 记录已经删除；已确认有效的设计、诊断能力和失败方向黑名单见 `GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md`，正式测试规范见 `GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`。

## 记录规则

- 只记录重要优化、重要回退、重要性能复测或能改变后续判断的诊断结论。
- 编号使用自增格式 `OPT-001`、`OPT-002`、`OPT-003`。
- 每个编号只用一个小节，把优化内容、测试结果和结论放在一起，不再拆成“优化内容”和“测试结果”两个部分。
- 正式性能结果优先记录 `Formal Host/VM performance ratio table`，表格格式必须和 `GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md` 保持一致。
- 如果只是 VM-only 诊断，也要写清楚诊断开关，并在结论里说明它不能替代正式 baseline。
- 如果优化最终被回退或不采用，写入本日志后，还应把稳定反例补充进 `GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md` 的黑名单。

## 条目模板

```markdown
## OPT-001 - YYYY-MM-DD - 简短标题

- 变更：一句话说明改了什么。
- 动机：一句话说明要解决哪个阶段或哪类开销。
- 测试：`RUN_ID`，正式/诊断开关，是否 Host/VM sweep。
- 结果：

| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share ref** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | ... | ... | ... | ... | ... | 79.0/6.7/14.4/0.07 |
| 16 MiB | 100 | ... | ... | ... | ... | ... | 81.0/2.0/16.3/0.02 |
| 64 MiB | 20 | ... | ... | ... | ... | ... | 80.0/0.75/19.3/0.01 |

- 结论：采用/不采用/继续观察，以及下一步。
```

## Entries

暂无新条目。
