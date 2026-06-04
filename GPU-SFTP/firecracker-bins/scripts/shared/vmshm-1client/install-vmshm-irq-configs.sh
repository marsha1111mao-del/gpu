#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BINS_DIR=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)
CONFIG_DIR="${BINS_DIR}/configs/shared/vmshm-1client"

mkdir -p "${CONFIG_DIR}"

cat >"${CONFIG_DIR}/broker-config.toml" <<'EOF'
[broker]
socket_dir = "/run/vmshm"

# object/data shared window
[[domains]]
id = "vmshm-object"
socket_path = "/run/vmshm/vmshm-object.sock"
memfd_name = "vmshm-object"
window_size = 134217728
seal = true

# control/rpc shared window
[[domains]]
id = "vmshm-comm"
socket_path = "/run/vmshm/vmshm-comm.sock"
memfd_name = "vmshm-comm"
window_size = 33554432
seal = true
EOF

cat >"${CONFIG_DIR}/client-vm-config.json" <<'EOF'
{
  "boot-source": {
    "kernel_image_path": "/root/GPU-SFTP/firecracker-bins/kernels/shared/client/Image",
    "boot_args": "console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/bin/sh"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "/root/GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2",
      "is_root_device": false,
      "is_read_only": false
    }
  ],
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "cpu_template": null,
    "gpu_passthrough": false,
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/vmshm-1client-client.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client",
      "role": "client",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": 134217728,
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm.sock",
      "name": "vmshm-comm-client",
      "role": "client",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "client_comm_vmshm",
      "fdt_compatible": "client_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f000000",
        "doorbell_size": "0x1000",
        "irq": 80
      }
    }
  ]
}
EOF

cat >"${CONFIG_DIR}/proxy-vm-config.json" <<'EOF'
{
  "boot-source": {
    "kernel_image_path": "/root/GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image",
    "boot_args": "console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/bin/sh"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "/root/GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2",
      "is_root_device": false,
      "is_read_only": false
    }
  ],
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "cpu_template": null,
    "gpu_passthrough": true,
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/vmshm-1client-proxy.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": 134217728,
      "fdt_node_name": "proxy-vmshm-manager",
      "fdt_compatible": "proxy-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm.sock",
      "name": "vmshm-comm-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f100000",
        "doorbell_size": "0x1000",
        "irq": 81
      }
    }
  ]
}
EOF

echo "Installed vmshm irq notify configs to ${CONFIG_DIR}"
