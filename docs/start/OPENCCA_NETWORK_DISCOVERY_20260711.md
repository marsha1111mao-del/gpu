# OpenCCA Network Discovery 2026-07-11

> 本页是 2026-07-11 的历史现场记录，以下 sandbox 限制不代表当前环境。当前操作请使用[Agent 手册](AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)第 4 节；Pi 首选有线 `.189`，`.52` 为同一 Pi 无线备用。

## Historical status

The current Codex command sandbox cannot open network sockets. Direct SSH to the
previously documented hosts fails before reaching the LAN:

```text
ssh mzh@192.168.31.52 ... -> socket: Operation not permitted
ssh root@192.168.31.18 ... -> socket: Operation not permitted
```

Because of that sandbox restriction, the current Raspberry Pi and RK3588 IPs
were not verified from this session. Do not treat the lack of scan results here
as evidence that either board is offline.

## Discovery Entry Point

Run the LAN discovery script from a shell with normal network permissions:

```bash
cd /home/mzh/RK3588/gpu
scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24
```

Expected identification rules:

- Raspberry Pi: SSH user `mzh`, password `root`, and executable
  `/home/mzh/opencca-flash/flash.sh`.
- RK3588: SSH user `root`, password `root`, and one of `/dev/pmthor`,
  `fb000000.gpu`, or an `opencca-pmthor` kernel string.

After confirming the detected hosts are correct, update the documented/default
IPs:

```bash
cd /home/mzh/RK3588/gpu
scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24 --update-docs
```

The update path replaces the old defaults:

```text
Raspberry Pi: 192.168.31.52
RK3588:       192.168.31.18
```

in the runbooks, skill snapshots, OpenCCA path defaults, and GPU run scripts.
