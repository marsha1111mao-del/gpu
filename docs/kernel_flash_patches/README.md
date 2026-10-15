# 当前内核刷写实现

旧 raw-FIT 补丁已退出当前流程，历史版本可从 Git 历史查看。当前使用 SD 卡
storage ID 2、p3 ext4/extlinux kernel 分区、p4 rootfs。

唯一维护的上游修改位于 `opencca/patches/manifest.json` 及其列出的补丁文件：

```bash
./scripts/setup/bootstrap.sh --firmware
python3 opencca/scripts/setup/apply-local-patches.py --check
```

刷写步骤参见 `docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md`；初始化脚本只准备源码
和载荷，不会自动刷写设备。
