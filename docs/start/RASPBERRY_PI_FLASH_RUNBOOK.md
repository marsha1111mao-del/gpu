# Raspberry Pi 刷机控制机操作手册

本文只记录硬件层面的连接、上电、串口、Maskrom 和刷机流程。它不依赖容器运行时、上层应用或项目具体能力。

当前 OpenCCA/RK3588 重刷流程固定写入 SD 卡启动，不写 eMMC。`rkdeveloptool --help` 对 Rockchip storage ID 的说明是：`1=EMMC, 2=SD, 9=SPINOR`。因此写 SD 启动固件或完整 rootfs 时必须显式使用 `OPENCCA_FIRMWARE_STORAGE_ID=2` 和 `OPENCCA_ROOTFS_STORAGE_ID=2`；不要把这两个变量设为 `1`，否则会写 eMMC。

## 1. 机器角色

| 设备 | 作用 | 当前环境 |
| --- | --- | --- |
| 控制机 | 发起 SSH、同步固件文件、调用刷机脚本 | `/home/mzh/RK3588/gpu` |
| Raspberry Pi | 刷机/电源/串口控制机 | `mzh@192.168.31.52`，密码通过本地环境变量提供 |
| RK3588/ROCK 5B | 被刷写的目标板 | SSH 常用地址 `root@192.168.31.18` |

树莓派在硬件链路里承担三件事：

1. 通过局域网接受控制机 SSH 连接。
2. 通过 USB OTG/Maskrom 口控制 RK3588 刷机。
3. 通过 USB-TTL 串口读取 RK3588 console 日志。

推荐拓扑：

```text
控制机
  |
局域网 / 路由器
  |
Raspberry Pi  -- USB OTG/Maskrom --> RK3588
              -- USB-TTL UART ----> RK3588 UART
              -- 电源控制 --------> RK3588 电源
```

## 2. 从控制机连接树莓派

建议先设置通用环境变量，后续命令可以复用：

```bash
export PI_HOST=mzh@192.168.31.52
export PI_PASSWORD='<pi-ssh-password>'
export PI_SUDO_PASSWORD='<pi-sudo-password>'
export RK_HOST=root@192.168.31.18
export RK_PASSWORD='<rk-ssh-password>'
export RK_ROOT_PASSWORD='<rk-root-password-for-image>'
```

检查树莓派 SSH：

```bash
sshpass -p "$PI_PASSWORD" ssh \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/tmp/coco_known_hosts \
  "$PI_HOST" 'hostname; uname -a; ip -br addr'
```

当前树莓派刷机目录：

```text
/home/mzh/opencca-flash
```

检查目录和固件快照：

```bash
sshpass -p "$PI_PASSWORD" ssh \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/tmp/coco_known_hosts \
  "$PI_HOST" \
  'cd /home/mzh/opencca-flash && ls -la && ls -lh snapshot'
```

## 3. 树莓派刷机目录

树莓派端核心文件：

| 路径 | 说明 |
| --- | --- |
| `/home/mzh/opencca-flash/flash.sh` | 统一入口，调用电源控制、Maskrom、`rkdeveloptool` 和串口工具。 |
| `/home/mzh/opencca-flash/tools/rkdeveloptool` | arm64 版 Rockchip 刷机工具。 |
| `/home/mzh/opencca-flash/tools/rk3588/rk3588_spl_loader_v1.16.113.bin` | 当前推荐 SPL loader。 |
| `/home/mzh/opencca-flash/snapshot/` | 待刷写的固件和镜像目录。 |
| `/home/mzh/opencca-flash/board/` | 电源和 Maskrom 控制脚本。 |

常用固件文件：

| 文件 | 用途 |
| --- | --- |
| `snapshot/idbloader.img` | SD 启动 loader。 |
| `snapshot/u-boot.itb` | SD 上的 U-Boot 镜像。 |
| `snapshot/u-boot-rockchip-spi.bin` | SPI flash 使用的 U-Boot 镜像。 |
| `snapshot/opencca-image-rockchip-rock5b-rk3588.img` | 完整系统镜像，刷写会覆盖目标存储内容。 |

查看树莓派端入口帮助：

```bash
sshpass -p "$PI_PASSWORD" ssh \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/tmp/coco_known_hosts \
  "$PI_HOST" \
  'cd /home/mzh/opencca-flash && ./flash.sh help'
```

## 4. 硬件连接

### 4.1 网络

树莓派需要接入控制机可达的局域网。当前使用：

```text
Raspberry Pi: 192.168.31.52
SSH:          mzh, password from PI_PASSWORD
```

如果树莓派同时使用 Wi-Fi 和有线网，优先使用稳定的控制入口地址。避免树莓派有线口和 RK3588 静态 IP 冲突。

### 4.2 Maskrom/OTG USB

将 RK3588/ROCK 5B 的 USB OTG/Maskrom 口连接到树莓派 USB 口。进入 Maskrom 后，树莓派上应能看到 Rockchip USB 设备：

```bash
sshpass -p "$PI_PASSWORD" ssh "$PI_HOST" \
  "lsusb | grep -i -E '2207|rockchip' || true"
```

常见设备标识：

```text
ID 2207:350b Fuzhou Rockchip Electronics Company USB-MSC
```

也可以用 `rkdeveloptool` 检查：

```bash
sshpass -p "$PI_PASSWORD" ssh "$PI_HOST" \
  'cd /home/mzh/opencca-flash && sudo ./tools/rkdeveloptool ld'
```

预期输出包含：

```text
Maskrom
```

### 4.3 串口 UART

串口和 Maskrom USB 是两条独立链路。串口只用于 console，不用于刷写。

当前串口参数：

```text
设备:   /dev/ttyUSB0
波特率: 1500000
数据位: 8
校验:   N
停止位: 1
流控:   No
```

USB-TTL 接线：

```text
RK3588 UART TX  -> USB-TTL RX
RK3588 UART RX  -> USB-TTL TX
RK3588 GND      -> USB-TTL GND
```

只接 3.3V TTL 信号，不要把 5V 接到 UART 引脚。

检查树莓派串口设备：

```bash
sshpass -p "$PI_PASSWORD" ssh "$PI_HOST" \
  "ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null || true"
```

连接串口 console：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  'cd /home/mzh/opencca-flash && ./flash.sh minicom'
```

## 5. 同步固件到树莓派

把待刷写文件同步到树莓派 `snapshot/` 目录：

```bash
rsync -av --checksum \
  idbloader.img \
  u-boot.itb \
  u-boot-rockchip-spi.bin \
  "$PI_HOST:/home/mzh/opencca-flash/snapshot/"
```

如果固件位于本仓库 `opencca/snapshot/`，也可以直接指定源路径：

```bash
rsync -av --checksum \
  opencca/snapshot/idbloader.img \
  opencca/snapshot/u-boot.itb \
  opencca/snapshot/u-boot-rockchip-spi.bin \
  "$PI_HOST:/home/mzh/opencca-flash/snapshot/"
```

本仓库还提供了一个可选包装脚本，用于同步固定快照文件到树莓派：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --sync-only
```

包装脚本目标目录：

```text
mzh@192.168.31.52:/home/mzh/opencca-flash/snapshot/
```

## 6. 进入 Maskrom

优先使用树莓派端自动控制：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  "cd /home/mzh/opencca-flash && printf '%s\n' '$PI_SUDO_PASSWORD' | sudo -S ./flash.sh device"
```

`flash.sh` 会执行：

1. 通过 `board/` 脚本按下 Maskrom 控制。
2. 重新上电或重启 RK3588。
3. 等待 `rkdeveloptool ld` 看到 Maskrom 设备。
4. 必要时下载 SPL loader。

如果自动控制不可用，也可以手工进入：

1. 按住 RK3588 开发板 Maskrom 按键。
2. 给 RK3588 上电或重新插入 USB OTG。
3. 树莓派上确认 `lsusb` 出现 `2207:350b`。
4. 松开 Maskrom 按键。

## 7. 刷写 SD 启动固件

SD 固件刷写只更新启动相关位置，不重写完整 rootfs。当前流程不写 eMMC；Rockchip storage ID 必须保持 `2=SD`。

树莓派端命令：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  "cd /home/mzh/opencca-flash && printf '%s\n' '$PI_SUDO_PASSWORD' | sudo -S env OPENCCA_FIRMWARE_STORAGE_ID=2 ./flash.sh mmc"
```

控制机包装命令：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
OPENCCA_RPI_SUDO_PASSWORD="$PI_SUDO_PASSWORD" \
OPENCCA_RK_HOST="$RK_HOST" OPENCCA_RK_PASSWORD="$RK_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --flash-sd-firmware --wait-rk
```

底层写入位置：

```text
idbloader.img -> LBA 0x40
u-boot.itb    -> LBA 0x4000
```

刷写完成后脚本会执行 `rkdeveloptool rd` 重启目标板。加 `--wait-rk` 时，控制机会等待 RK3588 SSH 恢复。

## 8. 刷写 SPI 固件

SPI 刷写用于更新 SPI flash 中的 U-Boot 镜像。

树莓派端命令：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  "cd /home/mzh/opencca-flash && printf '%s\n' '$PI_SUDO_PASSWORD' | sudo -S ./flash.sh spi"
```

控制机包装命令：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
OPENCCA_RPI_SUDO_PASSWORD="$PI_SUDO_PASSWORD" \
OPENCCA_RK_HOST="$RK_HOST" OPENCCA_RK_PASSWORD="$RK_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --flash-spi --wait-rk
```

默认文件：

```text
snapshot/u-boot-rockchip-spi.bin
```

## 9. 刷写完整 rootfs 镜像

完整镜像刷写会覆盖目标存储上的文件系统。只有在需要重装整盘系统时使用。
当前流程刷写 SD 卡启动盘，目标 storage ID 是 `2=SD`，不是 `1=EMMC`。

确认镜像在树莓派：

```bash
sshpass -p "$PI_PASSWORD" ssh "$PI_HOST" \
  'ls -lh /home/mzh/opencca-flash/snapshot/opencca-image-rockchip-rock5b-rk3588.img'
```

执行整盘刷写：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  "cd /home/mzh/opencca-flash && printf '%s\n' '$PI_SUDO_PASSWORD' | sudo -S env OPENCCA_ROOTFS_STORAGE_ID=2 ./flash.sh rootfs snapshot/opencca-image-rockchip-rock5b-rk3588.img --yes"
```

控制机包装命令：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
OPENCCA_RPI_SUDO_PASSWORD="$PI_SUDO_PASSWORD" \
OPENCCA_RK_HOST="$RK_HOST" OPENCCA_RK_PASSWORD="$RK_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --flash-rootfs --no-sync --wait-rk
```

底层等价流程：

```bash
sudo ./tools/rkdeveloptool ld
sudo ./tools/rkdeveloptool db tools/rk3588/rk3588_spl_loader_v1.16.113.bin
sudo ./tools/rkdeveloptool cs 2
sudo ./tools/rkdeveloptool wl 0 snapshot/opencca-image-rockchip-rock5b-rk3588.img
sudo ./tools/rkdeveloptool rd
```

## 10. 电源和重启控制

树莓派端 `flash.sh` 暴露了板级控制入口：

```bash
cd /home/mzh/opencca-flash
./flash.sh on
./flash.sh off
./flash.sh reboot
```

从控制机调用：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  "cd /home/mzh/opencca-flash && printf '%s\n' '$PI_SUDO_PASSWORD' | sudo -S ./flash.sh reboot"
```

控制机包装命令：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
OPENCCA_RPI_SUDO_PASSWORD="$PI_SUDO_PASSWORD" \
OPENCCA_RK_HOST="$RK_HOST" OPENCCA_RK_PASSWORD="$RK_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --reboot --wait-rk
```

树莓派端电源控制由 `/home/mzh/opencca-flash/board/` 决定，当前脚本会调用配置中的插座或 USB 供电控制。具体硬件配置在 `/home/mzh/opencca-flash/.env` 中。

## 11. 常见排查

### `rkdeveloptool ld` 看不到设备

先查 USB：

```bash
sshpass -p "$PI_PASSWORD" ssh "$PI_HOST" \
  "lsusb | grep -i -E '2207|rockchip' || true"
```

如果没有 `2207:350b`，通常是：

- RK3588 没有进入 Maskrom。
- USB OTG 口或线缆接错。
- 树莓派没有识别到 USB 设备。
- 电源控制没有真正重启目标板。

### `rkdeveloptool` 权限不足

先使用 `sudo`：

```bash
cd /home/mzh/opencca-flash
sudo ./tools/rkdeveloptool ld
```

后续如需免 sudo，可以单独增加 udev 规则；当前流程默认允许用 sudo。

### 串口没有 `/dev/ttyUSB0`

检查枚举：

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null
dmesg | tail -n 80 | grep -Ei 'ttyUSB|ttyACM|ch34|ch341|cp210|ftdi|pl2303|usb|serial'
```

如果只看到 Maskrom USB 设备，没有 `/dev/ttyUSB0`，说明当前只连了刷机 USB，没有连 USB-TTL 串口。

### 刷写后 RK3588 SSH 不恢复

先确认板子是否已经重启：

```bash
OPENCCA_RPI_HOST="$PI_HOST" OPENCCA_RPI_PASSWORD="$PI_PASSWORD" \
OPENCCA_RPI_SUDO_PASSWORD="$PI_SUDO_PASSWORD" \
OPENCCA_RK_HOST="$RK_HOST" OPENCCA_RK_PASSWORD="$RK_PASSWORD" \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --reboot --wait-rk
```

如果仍不能恢复，打开串口查看启动日志：

```bash
sshpass -p "$PI_PASSWORD" ssh -t "$PI_HOST" \
  'cd /home/mzh/opencca-flash && ./flash.sh minicom'
```

### 误刷风险

- `rkdeveloptool cs` 的 storage ID 是 `1=EMMC, 2=SD, 9=SPINOR`。
- 本流程要求 SD 启动，`flash.sh mmc` 和 `flash.sh rootfs ... --yes` 必须配合 `OPENCCA_FIRMWARE_STORAGE_ID=2` 或 `OPENCCA_ROOTFS_STORAGE_ID=2`。
- `flash.sh mmc` 会写 `idbloader.img` 和 `u-boot.itb`。
- `flash.sh spi` 会写 SPI flash。
- `flash.sh rootfs ... --yes` 会重写完整系统镜像。
- `flash.sh clear` 会清空 flash，确认目标和恢复方案后再执行。
