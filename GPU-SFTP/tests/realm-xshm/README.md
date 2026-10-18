# Realm 共享、可信通知与 GPU 测试

当前版本为P42 + BO容量修复。设计、冻结输入与验收边界统一见[当前基线](../../../docs/shared/CURRENT_BASELINE.md)，不再在工具说明中重复历史实验。

## 入口与构建

从仓库根目录运行。先读[环境主手册](../../../docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)，确认Pi/RK角色、Host/RMM匹配并取得硬件租约：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> --workload compute
```

| 选项 | 实际范围 |
| --- | --- |
| `--workload events` | 三Realm可信事件与拒绝语义 |
| `--workload compute` | 两个Client独立池、各17项API、实际计算、权限与IRQ检查 |
| `--workload glmark --performance --benchmark-only --suite --profiles glmark-720` | 默认256 MiB，完整720p性能 |
| 上述glmark模式加`--large-pool --profiles ncnn-resnet50 glmark-1080 ioctl compute-128` | 512 MiB池、每Realm1 GiB、CMA576 MiB；要求支持512 MiB的RMM |

冻结包包含`client-Image`、`proxy-Image`、`initrd.cpio`、`runner.py`及`hashes.json`。入口逐文件校验，仅上传变化内容；不替换Host/RMM/rootfs。rootfs须已准备并按只读方式使用。清理后已测包是`build/memfd-retirement-20261018/candidate/`（720p1157）；client/proxy/initrd/VMM已进入当前runtime-manifest。旧`build/bo-capacity-20261018/final/`保留为历史性能对照，不等同清理后源码。

构建工具：`bash scripts/build/build-realm-xshm.sh`，输出位于`build/realm-xshm/`；成套内核：`bash scripts/build/build-verified-kernels.sh realm`。配置和完整构建范围见[配置说明](../../../configs/performance/README.md)。`build-realm-xshm-initrd.py --help`列出可选探针与工作负载打包参数；仅编译工具不等于生成完整可验证包。

## 接口语义

`realm-xshm`访问0600权限的`/dev/realm-xshm`，Guest需`CONFIG_REALM_XSHM=y`；调用进入真实RSI，不模拟RMM。管理操作需Guest `CAP_SYS_ADMIN`。关闭fd不注销Realm端点，必须显式unregister或销毁Realm。

REGISTER返回`[ABI, endpoint, capabilities, capacity]`。按实际能力位检查端点、持久事件、映射、身份描述、IRQ和ACK_ARM，不以历史cap31替代当前能力检查。当前成套Guest要求ACK_ARM；不支持的固件不能降级后冒充可信IRQ通过。端点ID不是远程证明。

| 操作 | 含义 |
| --- | --- |
| `register / unregister` | 本Realm端点生命周期 |
| `offer PEER / accept CHANNEL / close CHANNEL` | 通道创建与销毁 |
| `notify CHANNEL` | 通知对端，RMM验证参与者身份 |
| `ack-arm CHANNEL` | 原子确认当前pending并重新armed；排空后仍需acquire重查队列 |
| `irq-bind / irq-stats` | 绑定INTID127、读取真实分发计数 |
| `mem-offer CHANNEL SOURCE_IPA SIZE` | 提供已准备的私有DATA页 |
| `mem-attach GRANT TARGET_IPA` | 挂接到准备好的受保护RAM空闲L3 entries |
| `mem-status / mem-continue GRANT` | 查看或推进分段操作 |
| `mem-detach / mem-revoke GRANT` | 借用方解除、提供方撤销 |
| `mem-describe GRANT` | 经身份校验获得通道、双方端点与本Realm IPA |

内存操作返回`[grant, state, progress, pages]`，状态3表示分段未完成，应CONTINUE，不能重新OFFER/ATTACH。通知/提交不自动重试；EFAULT或传输超时不证明RMM未执行。

## 池与传输

- `pool-source SIZE / pool-target SIZE`建立内核持久池；每Realm最多8个，单池上限512 MiB，实际受CMA限制。默认性能池仍为256 MiB。
- `pool-info/read/write`用于受控诊断；多个池时用`--pool LOCAL_IPA`明确选择，目标访问需ACTIVE grant。不是任意用户缓冲区注册或hot-unload接口。
- `pool-fill-pages SEED [GRANT] / pool-check-pages SEED [GRANT]`检查每页首个64位字，不能表述为验证每个字节。
- `pool-bind GRANT`绑定前1 MiB通信队列，身份取自RMM；`pool-bind-gpu GRANT`还绑定池后部的对象分配区。数据区移除WB线性映射后建立WC映射，队列仍为WB。
- `pool-unbind GRANT`要求活动fd/session/对象引用已释放；未排空pin时保持quiesced，不能提前回收。绑定期间拒绝原始字访问和本地撤销。

RMM授权与IRQ不替代消息边界验证。IRQ只提示队列检查；GPU完成仍由真实原生fence确认。当前固定一Realm一vCPU、INTID127，需匹配Host的LR预留策略。没有新增硬件GPT/GPC或跨Group shadow页表保护声明。

## 判定与证据

工具输出JSON：退出0为RMM成功，1为本地设备/ioctl失败，2为参数错误，3为RMM拒绝；负例必须核对具体返回，不能把任意失败当作拒绝通过。

runner保存实际命令、逐项退出码、输入哈希、串口及summary；wrapper保存前后资源。性能需同时核对Mali后端、正确性、完整场景、BO/提交错误、内核健康与恢复；不能只看score或外层exit0。未选择项目记为NOT_RUN。

最新结果及历史失败：[性能汇总](../../../docs/shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)、[BO修复](../../../docs/shared/GPU_BO_CAPACITY_FIX_20261018.md)、[历史实现记录](../../../docs/archive/20261018/history/PROXY_TASK_SERVICE_IMPLEMENTATION_20261017.md)。
