# 旧设计 baseline：Proxy 分配 Client GPU 内存

对应 1280×720 单 Client **1158／1158，均值1158.00**；用户指定 Native 参考1431.50，参考保留率80.89%。这里保存的是 Proxy 分配数据页、Client 共享使用、Proxy 原生驱动提交 GPU 的设计。

源码沿用已发布正式设计9127c47（Guest39d95dd）；`manifest.json`保存两轮1158分的实际冻结Client／Proxy／initrd／runner及RMM固件，逐项SHA已经与原实验核验。`measured-inputs.json`与`measured-guest-source.diff`保留当时A/B源码依据。**当时两份默认关闭的内存计量辅助源码已删除，仅存哈希；因此本分支不宣称可从现存源码逐字节重建1158分镜像。** 清理后的正式源码仍是同一内存分配设计，完整可构建；复现实测优先使用封存镜像。

```bash
python3 scripts/artifacts/restore-runtime.py --manifest baselines/legacy-proxy-allocated-1158-20261102/manifest.json --dest build/baselines/legacy-1158
python3 scripts/artifacts/restore-runtime.py --manifest baselines/legacy-proxy-allocated-1158-20261102/manifest.json --dest build/baselines/legacy-1158 --check
```

实际测试条件：单Client、完整33场景、CPU固定1.8GHz、GPU594MHz、128MiB紧凑池、固定落核，PLAN缓存开启；RPC／计量关闭。两轮run-id见validation.json，未在归档时重跑。旧固件应与旧Host和既有健康运行树配套，不向当前私有页板端部署旧载荷。

旧运行树已准备且固件／Host匹配后，复测入口为：

```bash
python3 scripts/maintenance/lab-run.py --run-id legacy-1158-repeat-UNIQUE -- python3 scripts/run/run-realm-xshm.py --images build/baselines/legacy-1158/runtime --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1 --compact-memory --pool-mib 128 --cpu-frequency-khz 1800000
```

此命令是复现入口说明，本次未新增硬件测量；必须先按环境与资源手册核对，不将历史PASS扩大到新运行。旧Native参考与新FU自动CPU频率／默认池不是同期单变量对照。
