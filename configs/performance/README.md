# 性能与构建配置

当前默认开发路径是RMM授权共享的Realm Client/Proxy，设计和冻结版本见[当前基线](../../docs/shared/CURRENT_BASELINE.md)。旧普通VM配置已删除，历史报告仅用于设计和性能对照。

## 当前Realm配置

从仓库根目录运行：

```bash
BUILD_ROOT="$PWD/build/realm-kernels" bash scripts/build/build-verified-kernels.sh realm
```

入口在`configs/verified-20261015/{client,proxy}.config`上合并本目录的`realm-{client,proxy}.config`，启用REALM_XSHM、320 MiB CMA。分别安装至`GPU-SFTP/firecracker-bins/kernels/realm-xshm/Image`和`proxy/Image`，不构建Host/RMM或完整initrd。构建前确认输出未被测试使用；执行测试必须冻结载荷并记录哈希。

两侧配置合并、olddefconfig及Image构建已验证，记录位于`build/realm-performance-20261018/realm-config-entry-retained-build.{log,json}`；这是构建验证，不是新GPU性能测量。

| 档位 | 每Realm内存 | CMA | 共享池 | 入口 |
| --- | --- | --- | --- | --- |
| 默认720p | 768 MiB | 320 MiB | 256 MiB | `--workload glmark --performance --benchmark-only --suite --profiles glmark-720` |
| 大负载 | 1024 MiB | 命令行覆盖为576 MiB | 512 MiB | 上述glmark模式加`--large-pool`并选择负载 |

大配置要求匹配支持512 MiB上限的RMM，不修改默认内核配置。实际GPU请求600MHz/读回594MHz，Proxy CPU1、Client CPU2；关闭shader cache和诊断计时，完整33场景，null-noop / finish。由`lab-run.py`包裹`run-realm-xshm.py --images <冻结包>`运行；未选项目不计PASS。

当前成绩及按项版本来源见[完整性能汇总](../../docs/shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)。不凭相同配置推断未测源码组合通过。

## 历史对照

旧memfd/irqfd runner和配置已移除。历史版本、SHA、命令和结果查[2026-10-16性能报告](../../docs/archive/20261018/history/GPU_GLMARK_PERFORMANCE_REPORT_20261016.md)及[优化记录](../../docs/archive/20261018/history/GPU_GLMARK_OPTIMIZATION_20261016.md)，不再作为当前可执行入口。
