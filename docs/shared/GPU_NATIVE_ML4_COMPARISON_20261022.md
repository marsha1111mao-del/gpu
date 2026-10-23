# ML / NCNN：Native 四进程与四 Client 对照

已完成10项Native四进程并发尝试，7项有效、3项GPU执行失败；失败项不取耗时、不计算保留比例。Clientproxy复用已通过的四Client结果，未重复运行。原40条历史单进程Native对照表保留，本页新增相同任务数的对照，不把未测的1–3进程改称同期对照。

已追加至[Notion多Client并行测试结果合集](https://www.notion.so/3ff659a3b8cc813bbab7c109be10ad21)，回读确认新增对照仅一处、原有glmark/内存/40条ML结果原文保留；发布核验在`build/native-ml4-20261022/notion-ml4-publication.json`。

## 结果

单位ms，为四个进程/Client各自迭代均值的算术平均；性能保留比例=Native四进程均值÷Clientproxy四Client均值×100%。它描述本轮有限任务的完成表现，不是纯GPU服务时间、精确稳态吞吐或同配置虚拟化开销。

| 测试 | Native 四进程耗时 ms（均值；各进程） | Clientproxy 四 Client 耗时 ms（均值；各 Client） | 性能保留比例 |
| --- | --- | --- | --- |
| ml-reduction | 30.894（25.390 / 37.915 / 34.731 / 25.541） | 34.803（30.463 / 37.150 / 43.071 / 28.531） | 88.77% |
| ml-conv | 101.741（132.961 / 126.894 / 73.364 / 73.743） | 130.491（136.224 / 131.478 / 127.953 / 126.311） | 77.97% |
| ml-depthwise | 65.235（43.473 / 44.234 / 85.951 / 87.281） | 84.710（82.815 / 85.500 / 86.130 / 84.396） | 77.01% |
| ml-gemm | 失败，GPU 超时/提交错误，耗时不采信 | 111.144（103.571 / 106.616 / 121.229 / 113.158） | — |
| ncnn-mobilenet_v2 | 91.065（86.690 / 103.640 / 91.990 / 81.940） | 79.870（104.570 / 103.100 / 33.650 / 78.160） | 114.02% |
| ncnn-mobilenet_v3 | 91.377（80.450 / 98.210 / 90.680 / 96.170） | 74.760（82.110 / 96.040 / 30.660 / 90.230） | 122.23% |
| ncnn-resnet50 | 2267.457（2263.210 / 2265.840 / 2271.090 / 2269.690） | 5660.180（5555.430 / 5631.060 / 5686.080 / 5768.150） | 40.06% |
| ml-softmax | 64.068（70.421 / 76.434 / 48.980 / 60.438） | 66.589（50.959 / 91.825 / 77.112 / 46.460） | 96.21% |
| ml-attention | 失败，GPU 超时/提交错误，耗时不采信 | 2866.044（3165.234 / 2906.081 / 3006.397 / 2386.464） | — |
| attention-320 | 失败，GPU 超时/提交错误，耗时不采信 | 4394.888（4689.747 / 3493.069 / 4418.124 / 4978.611） | — |

原生也会随并发下降：卷积从历史单进程34.135ms变为四进程101.741ms，Reduction从10.695ms变为30.894ms。先前表中Native不变，是反复引用单进程基准，并不代表四进程并发没有竞争。新对照中Reduction/Softmax保留约89%/96%，卷积/深度卷积约78%/77%；ResNet50仍只有40.06%，提示其共享路径有值得单独排查的额外成本，但本实验不能区分Proxy CPU、准入策略、GPU调度和内存/cache维护各自的贡献。

## 条件与可比性

- 同RK3588、Host `6.12.0-opencca-pmthor-opp3 #31`；Native临时nVHE，四个进程均允许在CPU2–3运行，CPU policy0为schedutil、1008–1800MHz，GPU请求600MHz/实际594MHz。Clientproxy是历史protected Realm结果，Proxy CPU1、各Client vCPU可在CPU2–3运行，VMM I/O CPU0；未固定CPU频率，旧MobileNet批次缺少连续CPU频率采样，不能称各阶段实际频率严格相同。
- rootfs/Mesa/模型、算子二进制和工作负载脚本固定并核对SHA。rootfs为`5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60`；Native只读挂载四次，沿用同一脚本/二进制，不改算法或输入规模。NCNN为随机输入/空权重基准，100循环、2线程、GPU0、224×224、panvk-direct，不验证模型准确率。
- 七个算子在warmup之后同步释放测量循环：一般100次/预热5次，Attention-320为10次/预热2次。NCNN只在完整工作负载入口同步，含资格检查和模型加载，不保证推理循环精确同步。
- Clientproxy的七算子和ResNet50采用最多三个真实fence未完成任务的准入限制；Native未添加本项目限流，直接使用原生四进程路径。两者是实际系统策略对比，不能将全部耗时差归因于RPC。旧MobileNet为之前的共享配置，不能假定它也采用本轮七算子的限流。
- 每项只测一轮、每轮四个任务。原生发生GPU错误后保留该项失败；后续先重新绑定驱动，逐项检查新dmesg区间。此前失败的时间、恢复过程和各项顺序不隐藏，不声称整次启动期间内核从未报错。

## 并发窗口

以下为Host接收程序标记所见的四方公共窗口÷四方总窗口。算子使用warmup后的测量窗口；NCNN使用完整工作负载窗口，含加载/资格检查。窗口比例不同意味着较快进程可能在后半段退出竞争，不能把有限任务的均值直接解释为始终四路饱和时的吞吐。

| 测试 | Native 公共窗口 / 总窗口 | Clientproxy 公共窗口 / 总窗口 |
| --- | --- | --- |
| ml-reduction | 66.96% | 55.48% |
| ml-conv | 55.18% | 90.98% |
| ml-depthwise | 49.80% | 94.32% |
| ncnn-mobilenet_v2 | 78.86% | 36.49% |
| ncnn-mobilenet_v3 | 83.94% | 29.48% |
| ncnn-resnet50 | 99.79% | 96.95% |
| ml-softmax | 64.08% | 16.47% |

## 证据与失败

外层命令、退出码、恢复证据在`build/lab-runs/native-ml4-20261022-{a,b,c}/`，本地原始输出与文件SHA在`build/native-ml4-20261022/native/<run-id>/`；分析为同目录`analysis.json`、`results.md`及`analyze.py`。逐个重算原40份共享输出和有效Native输出，共核验68份有效输出；另保留失败原始日志，不以程序rc0或ML_CHECK=PASS掩盖Mesa错误。

| run-id | 状态与用途 | 外层退出码 |
| --- | --- | --- |
| native-ml4-20261022-a | 上传载荷缺少可执行权限，未取得有效成绩；修正后只继续实际测试 | 1 |
| native-ml4-20261022-b | GEMM四进程出现job timeout及Mesa提交错误，整项不采信；不重跑到PASS | 1 |
| native-ml4-20261022-c | 剩余9项；逐项状态见表，Attention两项错误保留，恢复驱动后继续 | 1 |

有效项均核验四个退出码、Mali/PanVK标记、样本数、真实公共窗口及该项新增内核日志。Native观测窗口GPU实际594MHz，CPU调频配置正确；没有把GPU执行失败写成内存不足。全部Native批次结束后extlinux配置逐字节恢复、重启回protected、CPU0–1和pmthor，loop/本次挂载清理完成。GPU失败仍使相应外层批次保持rc1。

历史共享来源：`build/ml-completion-20261022/runs/ml-fix-7profiles-4c-20261022-d`、`ml-fix-resnet-4c-20261022-f`和`build/multiclient-ml-20261021/runs/ml-4c-128m-20261021-ncnn-k`；各原始文件回收SHA、退出码和有效标记重新核验。

复现Native命令：

```bash
python3 scripts/maintenance/lab-run.py --allow-rk-reboot --run-id <新ID> -- \
  python3 build/native-ml4-20261022/native-mode-controller-v6.py --round a \
  --cases ml-conv ml-depthwise ml-reduction ml-softmax ml-attention attention-320 \
    ncnn-mobilenet_v2 ncnn-mobilenet_v3 ncnn-resnet50
```

GEMM已在b批次尝试；复现全部10项时在`--cases`中加`ml-gemm`。本轮不改变GPU提交实现，无新增glmark测量；不能根据ML对照声称glmark提分。新提交计时内核的构建和720p/1080p验收另见[提交路径分解](GPU_SUBMIT_PHASES_20261022.md)。
