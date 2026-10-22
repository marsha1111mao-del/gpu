# 完整1080p glmark测试与原生驱动对照（2026-10-20）

Notion：[完整1080p glmark测试｜原生对照与内存边界（2026-10-20）](https://app.notion.com/p/3ff659a3b8cc816aab11c72ce915f014)。页面及三个数据附件已回读核验；本次仅同步报告，未改运行代码，无新增性能测量。

## 结论

完整1920×1080、33个计分场景、null-noop/finish，两轮512 MiB池单Client成绩为904 / 901，均值902.50，轮间样本标准差2.12。两轮外层rc0、validation与clean通过、Host/Guest健康、Realm正常退出及资源恢复通过。

Native原生Panthor历史参考997分；本轮均值保留90.52%，相差-94.50分/-9.48%。Native为Host #7，本轮为Host #31，属于历史参考比较，差值不能精确归因于虚拟化。

紧凑128/160/192/256 MiB池本轮均未通过完整1080p：连续BO碎片化使实际分配失败。192/256 MiB得到的927/929均为无效成绩。多Client本轮未执行：已通过的512 MiB配置在当前Host内存预算下无法扩展至2/3/4 Client。没有缩短场景或关闭validation来得到PASS。

## 条件与版本

| 项目 | 条件 |
| --- | --- |
| 平台 | RK3588 / Mali-G610；Host 6.12.0-opencca-pmthor-opp3 #31，protected hVHE、RMM timer v6 |
| 输入 | 复用前轮720p candidate-e的Client/Proxy内核、静态工具和只读Panfrost rootfs；更新runner及dispatcher入口，不重编内核/固件 |
| 正式两轮 | 现有--large-pool路径：1 Client + 1 Proxy，各1 vCPU / 1024 MiB RAM / 576 MiB CMA，共享池512 MiB |
| CPU | CPU0–3在线；Proxy进程/线程CPU1，Client进程/线程CPU2；schedutil 1.008–1.8 GHz，未锁恒频 |
| GPU | 请求600 MHz、实际594 MHz；结束恢复原GPU governor/频率和CPU0–1 |
| 负载 | 完整1920×1080、33场景、null-noop、frame-end=finish，shader cache关闭；26 Success / 1既有medium-function差异 / 6 Unknown |
| 校验 | BO/export/VM_BIND/提交错误0、clean PASS；131072页共享池逐页检查、IRQ活动、解绑/detach/revoke及退出检查 |
| 小池试跑差异 | compact路径：Client vCPU共享CPU2–3，VMM非vCPU线程CPU0；池/RAM/CMA与正式大池不同，失败数据仅诊断容量/碎片化 |

## 正式结果与原生对照

| 运行方式 | 1080p score | 对Native997分差 | 对Native变化 | Native评分保留 |
| --- | --- | --- | --- | --- |
| Native Panthor / 历史单进程 | 997.00 | 0 | 0% | 100% |
| glmark1080-512m-a-20261020 | 904 | -93.00 | -9.33% | 90.67% |
| glmark1080-512m-b-20261020 | 901 | -96.00 | -9.63% | 90.37% |
| Proxy/Client两轮均值 | 902.50 | -94.50 | -9.48% | 90.52% |

同为完整1080p，历史512 MiB Proxy/Client为901分，本轮均值902.50，相差+1.50分/+0.17%；Host #7→#31、GPUVM/安全实现及运行版本不同，只记录组合观测，不宣称某一代码改动提分或回退。两轮只能给出描述性均值与标准差，不代表长期稳定性。

## 与前轮720p的范围区别

前轮完整720p单Client为1160/1155，均值1157.5；本轮1080p均值902.50，相差-255.00分/-22.03%。两者分辨率、池/RAM/CMA、CPU/线程放置不同，只是应用成绩的组合对照。

改动目的｜扩展1080p测试及核验内存配置｜改动前720p1160/1155、均值1157.5 → 本版720p未测｜720p分差/百分比未测；已验证720p解析、dispatcher及8轮历史统计兼容｜本轮新增测量仅为1080p，不能当作同分辨率性能优化验证｜各run-id、命令、rc与日志见后文｜保留测试入口，大池两轮通过，小池失败保留。

## 多Client内存边界：未执行

| Client数 | Proxy RAM MiB | 每Client RAM MiB | Realm合计MiB | 加256MiB Host预留 | 初始可用MiB | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 1344 | 768 | 2880 | 3136 | 3083.23 | NOT_RUN：超过现有准入预算 |
| 3 | 1888 | 768 | 4192 | 4448 | 3083.23 | NOT_RUN：超过现有准入预算 |
| 4 | 2432 | 768 | 5504 | 5760 | 3083.23 | NOT_RUN：超过现有准入预算 |

公式来自现有runner的多Client配置：每Client RAM=P+256；Proxy RAM=N×P+256+32×N。单Client正式大池仍使用原1024 MiB/Realm路径。小池失败并不证明所有中间池容量或未来分配策略都不可行；本轮没有修改分配器、压缩普通内存或绕过准入门槛。后续若需1080p并发，应单独处理连续BO碎片化与内存预算。

## 本轮小池失败（必须保留）

| run-id | 池MiB | 原始分数（无效） | BO错误 | 负载/外层rc | 结果 |
| --- | --- | --- | --- | --- | --- |
| mc1080-1c-128m-a-20261020 | 128 | none | 2 | 139/1 | FAIL / clean FAIL |
| mc1080-1c-160m-a-20261020 | 160 | none | 4 | 139/1 | FAIL / clean FAIL |
| mc1080-1c-192m-a-20261020 | 192 | 927 | 10 | 125/1 | FAIL / clean FAIL |
| mc1080-1c-256m-a-20261020 | 256 | 929 | 4 | 125/1 | FAIL / clean FAIL |

128 MiB：申请8359936字节，空闲2704页，最大连续块1075页；160 MiB：申请13201408字节，空闲4659页，最大连续块2975页；192 MiB：申请33947648/47149056字节时空闲约98 MiB，最大连续块31.03 MiB；256 MiB：申请47149056字节时空闲约118–130 MiB，最大连续块30.28 MiB。均有总空闲空间，但没有足够大的连续块；本轮证据指向池内碎片化，并非Host OOM。

四轮外层rc1、Host内核健康PASS、Realm均退出0/0；128/160/192 MiB失败回收还记录pool-unbind响应不明确，256 MiB无此记录。全部失败日志已回收并逐文件校验SHA；失败不能被512 MiB的PASS覆盖。详见 `build/multiclient-glmark1080-20261020/failed-capacity-trials.json`。

## 33场景FPS精确对照

Native来自历史原生日志；两轮与均值为本轮单Client完整成绩。glmark总分不是屏幕FPS，不把不同场景FPS相加解释为吞吐。

| 场景 | Native1080p | 本轮A | 本轮B | 两轮均值 |
| --- | --- | --- | --- | --- |
| [build] use-vbo=false | 748 | 995 | 992 | 993.50 |
| [build] use-vbo=true | 1785 | 1477 | 1476 | 1476.50 |
| [texture] texture-filter=nearest | 1571 | 1352 | 1351 | 1351.50 |
| [texture] texture-filter=linear | 1580 | 1356 | 1354 | 1355.00 |
| [texture] texture-filter=mipmap | 1585 | 1349 | 1352 | 1350.50 |
| [shading] shading=gouraud | 1531 | 1318 | 1315 | 1316.50 |
| [shading] shading=blinn-phong-inf | 1449 | 1284 | 1284 | 1284.00 |
| [shading] shading=phong | 1267 | 1166 | 1166 | 1166.00 |
| [shading] shading=cel | 1240 | 1151 | 1147 | 1149.00 |
| [bump] bump-render=high-poly | 944 | 953 | 947 | 950.00 |
| [bump] bump-render=normals | 1826 | 1480 | 1484 | 1482.00 |
| [bump] bump-render=height | 1651 | 1393 | 1393 | 1393.00 |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0; | 937 | 929 | 928 | 928.50 |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1; | 447 | 434 | 434 | 434.00 |
| [pulsar] light=false:quads=5:texture=false | 1179 | 1099 | 1096 | 1097.50 |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4 | 233 | 173 | 173 | 173.00 |
| [desktop] effect=shadow:windows=4 | 579 | 570 | 567 | 568.50 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map | 47 | 46 | 46 | 46.00 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata | 47 | 46 | 46 | 46.00 |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map | 65 | 65 | 65 | 65.00 |
| [ideas] speed=duration | 426 | 404 | 403 | 403.50 |
| [jellyfish] <default> | 763 | 758 | 752 | 755.00 |
| [terrain] <default> | 57 | 37 | 37 | 37.00 |
| [shadow] <default> | 687 | 605 | 607 | 606.00 |
| [refract] <default> | 144 | 116 | 116 | 116.00 |
| [conditionals] fragment-steps=0:vertex-steps=0 | 1358 | 1205 | 1196 | 1200.50 |
| [conditionals] fragment-steps=5:vertex-steps=0 | 1259 | 1153 | 1143 | 1148.00 |
| [conditionals] fragment-steps=0:vertex-steps=5 | 1337 | 1208 | 1203 | 1205.50 |
| [function] fragment-complexity=low:fragment-steps=5 | 1362 | 1206 | 1199 | 1202.50 |
| [function] fragment-complexity=medium:fragment-steps=5 | 1093 | 1072 | 1066 | 1069.00 |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5 | 1328 | 1205 | 1200 | 1202.50 |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5 | 1331 | 1204 | 1199 | 1201.50 |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5 | 1082 | 1066 | 1061 | 1063.50 |

## 验收证据与复现

### glmark1080-512m-a-20261020

```bash
python3 scripts/maintenance/lab-run.py --run-id glmark1080-512m-a-20261020 -- python3 scripts/run/run-realm-xshm.py --images build/multiclient-glmark1080-20261020/candidate-b --workload glmark --performance --benchmark-only --suite --profiles glmark-1080 --large-pool
```

成绩904；外层rc0、负载rc0、Host健康PASS、Realm退出0/0、131072页共享检查PASS、授权/绑定与CPU/GPU恢复通过；1秒采样最低Host MemAvailable 1344.30 MiB。日志：`build/multiclient-glmark1080-20261020/runs/glmark1080-512m-a-20261020`，含逐文件SHA回收清单、完整33场景、配置、Host dmesg及资源快照。

### glmark1080-512m-b-20261020

```bash
python3 scripts/maintenance/lab-run.py --run-id glmark1080-512m-b-20261020 -- python3 scripts/run/run-realm-xshm.py --images /home/mzh/gpu/build/multiclient-glmark1080-20261020/candidate-b --workload glmark --performance --benchmark-only --suite --profiles glmark-1080 --large-pool
```

成绩901；外层rc0、负载rc0、Host健康PASS、Realm退出0/0、131072页共享检查PASS、授权/绑定与CPU/GPU恢复通过；1秒采样最低Host MemAvailable 1338.68 MiB。日志：`build/multiclient-glmark1080-20261020/runs/glmark1080-512m-b-20261020`，含逐文件SHA回收清单、完整33场景、配置、Host dmesg及资源快照。

| 冻结输入 | SHA-256 |
| --- | --- |
| client-Image | `a7e56e417a5dec024a977f2df2cb9f45f439491d3ce61b236f958e8fc074c511` |
| proxy-Image | `4265f1c22b199108ac42bf1c04a7856b0adc86eab5aa0fc6338350e125990e3c` |
| initrd.cpio | `d8b6e898fb5437e97cb77aa4bca9b11896f2ee2f146b8d29914424131a509604` |
| runner.py | `9c080e62940eb47dbcb8a554ef637ab84231f0c03add8f6e74e1fc50f6c40b1b` |

冻结执行包为 `build/multiclient-glmark1080-20261020/candidate-b/`；属于本地开发测试组合，不替换原runtime-manifest或1171/1170冻结基线。未刷写Host、SD或固件；Pi仅提供独占租约。

Native证据：`GPU-SFTP/log/native-current/native-p42-comparison-20261018/`中的glmark-1080.log、exit-code、clock及SHA清单；外层native-p42-comparison-20261018退出0。本轮重新核对原生33场景、validation及SHA，没有重跑Native。

## 已实现 / 未实现与未执行

已实现并本轮实测：完整1080p大池单Client两轮、33场景与validation/clean、共享池逐页验证、Host健康与资源恢复、SHA证据回收、Native分数及逐场景对照。紧凑入口新增1080p评分屏障与实际尺寸检查，但所测小池未通过，不能称多Client1080p已验收。

未完成：紧凑小池完整1080p的连续BO碎片化问题。未执行：1080p多Client、同期Native复测及原生多进程并发、锁CPU恒频/公平调度对照、API/compute/故障负例全回归。既有Group submit fence间歇超时本轮未修复；本轮无此错误不取消旧未解决记录。
