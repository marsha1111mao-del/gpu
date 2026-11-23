# GPU 1200 冻结版

完整单 Client 720p glmark2 实测为 1205／1203，均值 1204，较 1170 高 34 分（2.91%）。两轮均为 33 场景和实测 594 MHz。双 Client 功能和 GLES 计算已通过。

1200 包含 Proxy/RMM 四笔提示查询批处理和 RMM 输出失效批处理。Client 镜像与 1170 相同。组件、固件哈希及原测试 run-id 见 [provenance.json](provenance.json)。

```bash
git submodule update --init Linux-Guest-GPU opencca
git -C opencca submodule update --init --recursive tf-rmm
manifest=baselines/gpu-1200-20261122/manifest.json
dest=build/baselines/gpu-1200-20261122/payload
python3 scripts/artifacts/restore-runtime.py --manifest "$manifest" --dest "$dest"
python3 scripts/artifacts/restore-runtime.py --manifest "$manifest" --dest "$dest" --check
```

载荷包括图形和计算各自的 initrd、runner、内核和配套固件。板端复验按独占流程核对 Host、只读 rootfs 及实际固件，参见[两版维护入口](../README.md)。
