# 三方案GPU扩展实验结果数据

本目录保留独立审计完成后的汇总 CSV、逐样本和逐场景数据及报告引用的 PNG 图。原始运行日志由对应 run-id 索引。

- `native`：常驻Realm协作独占GPU的直通分时，不是Host原生性能基准。`shared`为本项目共享，`virgl`为virtio-gpu。
- `formal-independent-summary.csv`：独立运行均值及范围。批内迭代/多个用户不作为独立重复；完整33场景每条件一批，代表6场景三批分开。
- `formal-measurement-samples.csv`：参数ns为整个批次的阶段耗时；API ms/输出为提交完成及全量读回除以独立逻辑输出数，后续CPU校验另计。模型为完整extract计时，不是裸GPU时间。
- `complete-workflow-*.csv`：含准备、预热、CPU参考/校验、同步和回收的完整验证请求。异构混合组是固定工作组合，不是通用运算量单位。Jain仅在相同工作下描述响应差异，不证明GPU时间片公平性。
- `venus-compatibility-summary.json`：GLES/图形用原匹配Host，三方模型用仅增加UDMABUF内建支持的匹配Host。`prior-model-observations.*`保留旧Host上的72行成功模型观察，按Host条件选择新测量，未按分数筛选或混合。
- `retained-model-extensions.*`保留已完成的双用户匹配模型观察，`model-extension-scope-ledger.csv`记录用户选择核心口径后移出正式模型矩阵的配置及实际测量状态。核心模型只做单用户三轮；图形/GLES多用户数据仍全部保留。
- `formal-config-ledger.csv`和`all-attempts.csv`：正式计划与所有尝试分开；失败/未执行/不适用不填零，不与成功样本合并。
- `resource-observations.csv`：采样覆盖记录区间，不能证明无短暂降频。VM进程RSS不是全部设备/RMM/Host后端预算，缺失字段留空。
- `hint-fallback-observations.csv`：共享可选等待提示错误来自唯一最终内核快照，包含准备/validation/计分的关闭DRM文件。错误仍须原可信FINISH，不可当作任务完成证据。

各文件与原审计SHA在`provenance.json`，原栈恢复摘要在`restoration-summary.json`。正常性能测试不提升MEM05或尚未实体证明的CPU/DMA/GIC/残留隔离范围。完整方法、条件与解释见上层扩展实验报告。
