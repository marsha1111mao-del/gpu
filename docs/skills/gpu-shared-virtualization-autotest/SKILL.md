---
name: gpu-shared-virtualization-autotest
description: 在 RK3588/OpenCCA 上部署、运行、诊断及汇总 Proxy/Client vmshm 共享 GPU 测试，包括单/双 Client、IOCTL、计算和图形性能。
---

# Proxy/Client 共享 GPU 测试

## 执行入口与实验室默认值

先读 [环境与测试主手册](../../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md) 和
[开发与产物管理](../../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)，再读将执行的脚本。
命令从仓库根目录执行（`git rev-parse --show-toplevel`）；不依赖旧的绝对工作区路径。

实验室地址：RK `root@192.168.31.18`，Pi `mzh@192.168.31.189`；
`.52` 是同一 Pi 的无线备用地址。仓库副本不保存密码，先按主手册交互读取凭据并导出环境变量。
本机私有 skill 可保留用户指定的实验室配置，不将凭据同步到 Git：

```bash
export REMOTE_HOST="${REMOTE_HOST:-192.168.31.18}"
export REMOTE_USER="${REMOTE_USER:-root}"
export REMOTE_PASS="${REMOTE_PASS:?先按主手册设置凭据环境变量}"
export OPENCCA_RPI_HOST="${OPENCCA_RPI_HOST:-mzh@192.168.31.189}"
export OPENCCA_RPI_PASSWORD="${OPENCCA_RPI_PASSWORD:?先按主手册设置凭据环境变量}"
export OPENCCA_RPI_SUDO_PASSWORD="${OPENCCA_RPI_SUDO_PASSWORD:?先按主手册设置凭据环境变量}"
export OPENCCA_RK_HOST="${OPENCCA_RK_HOST:-root@192.168.31.18}"
export OPENCCA_RK_PASSWORD="${OPENCCA_RK_PASSWORD:?先按主手册设置凭据环境变量}"
```

所有测试通过 `python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- <测试命令>`
执行；不要嵌套 wrapper。首次部署前运行 `lab-resources.py --check` 检查 Pi 与 RK。
资源门槛、独占锁边界、选择性同步、snapshot 保留/清理和逐项证据要求统一见开发与产物管理文档。

## 共享路径与命令

Client 的 DRM/Panthor 前端经 vmshm RPC 请求 Proxy 后端，Proxy 驱动实际 GPU。
不要把“API 能运行”写成硬件机密隔离；当前 OpenCCA 保护能力按实现与探针判定。
先按主手册确认 `pmthor`、`/dev/kvm`、匹配的 Client/Proxy 和必要的 ARM64 用户态。

当前唯一共享入口是RMM Realm路径；旧memfd broker、普通VM共享runner和32项矩阵入口已删除。先核对冻结包、Host/RMM和只读rootfs，wrapper只上传变化的冻结输入，不自动准备固件或rootfs。

```bash
python3 scripts/maintenance/lab-run.py --run-id "realm-720-$(date +%Y%m%d-%H%M%S)" -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

优化每轮先以完整720p超过1000分为门槛；达到后再扩展测试。双Client功能和越权/IRQ负例用`--workload compute`；大BO/ResNet50/1080p参数见[Realm说明](../../../GPU-SFTP/tests/realm-xshm/README.md)。未选择的项目是NOT_RUN，不能称32/32。重大代码改动记录旧/新分数及对应输入；未测量时明确写未测，不能继承旧PASS。

IOCTL 需相应语义 marker；提交成功后必须验证 fence 完成。GLES 需 `COMPUTE_CHECK=PASS`、
`GPU_SMOKE_RESULT=PASS`、Mali/Panfrost renderer 及最终结果；双 Client 两边都要通过。
raw Vulkan 需 suite 与 compute correctness；NCNN backend qualification 不等于模型通过，
含 `vkWaitForFences failed` 的时间不能当性能通过。glmark 必须检查场景和 validation，不能只看 score。

当前设计与冻结版本见 [当前基线](../../shared/CURRENT_BASELINE.md)，
最新性能见 [Native / ProxyClient 汇总](../../shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)。
普通 VM 对照的旧参数与逐轮结果查 [归档索引](../../archive/20261018/README.md)，不能冒充当前 Realm 结果。
2026-10-15 后曾有 Group submit fence 超时记录，保留其证据；新运行独立判定。
