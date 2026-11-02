# 新设计 baseline：FU RMM＋FT Client＋原DX

Client分配并写入私有数据页，Proxy提供驱动服务及共享控制页；RMM认证身份、管理真实GPU映射、执行授权、完成与撤销。当前保留完整720p **971／971**，最近原版对照 **972**。最后FX候选980，较972增加8分／0.82%，未过预设982保留线及1000目标，已撤回。按用户要求停止继续优化实验。

`manifest.json`固定已经上板验证的运行包和实际SD2固件；`validation.json`保存本次测试／恢复结论；`source-sha256.json`固定对应运行源文件。组件提交见components.json。FX代码和计时诊断不在此baseline中。

```bash
python3 scripts/artifacts/restore-runtime.py --manifest baselines/rmm-private-fu-ft-20261102/manifest.json --dest build/baselines/fu-ft
python3 scripts/artifacts/restore-runtime.py --manifest baselines/rmm-private-fu-ft-20261102/manifest.json --dest build/baselines/fu-ft --check
```

健康Host为`6.12.0-opencca-pmthor-opp3`，复用其匹配模块，无需刷写Host系统。固件只允许经独占部署入口写SD2，固件位于上述目标的firmware目录；按docs/start的环境／产物规范执行，不能将Image文件名当作release核验。源树TF-A本地修改由OpenCCA补丁manifest恢复并校验，未推送至上游。

匹配运行树和固件已准备后，完整720p入口为：

```bash
python3 scripts/maintenance/lab-run.py --run-id fu-ft-720-repeat-UNIQUE -- python3 scripts/run/run-realm-xshm.py --images build/baselines/fu-ft/runtime --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

CPU自动schedutil、GPU实际594MHz、默认池、单Client、完整33场景。validation为26成功／1既有Failure／6Unknown，不能称全部正确；GPU和VM退出0、内核健康与资源恢复通过。外层rc1仅因不足1000。未扩展ML／完整API／多Client，不继承旧设计完整矩阵PASS。

现存默认GPU-SFTP/runtime-manifest.json仍用于旧公共运行树；新baseline应使用这里的独立manifest，避免恢复为旧镜像。已有构建缓存可能是已撤回FV，复现以本清单镜像为准。源码重建RMM的固定参数在rmm-build-commands.json，用当前仓库路径及独立构建目录替换@WORKSPACE@／@BUILD@；不要更新上游latest。

归档仅整理源码、镜像、哈希和文档，未新增性能测量。与旧设计1158分的差异涉及安全架构、CPU频率及内存条件，不能据此计算单一优化或安全机制的开销。
