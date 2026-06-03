#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BINS_DIR=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)
CONFIG_DIR="${BINS_DIR}/configs/shared/vmshm-2client"

mkdir -p "${CONFIG_DIR}"

cat >"${CONFIG_DIR}/broker-config.toml" <<'EOF'
[broker]
socket_dir = "/run/vmshm"

[[domains]]
id = "vmshm-object"
socket_path = "/run/vmshm/vmshm-object.sock"
memfd_name = "vmshm-object-2client"
window_size = 67108864
seal = true

[[domains]]
id = "vmshm-comm-client0"
socket_path = "/run/vmshm/vmshm-comm-client0.sock"
memfd_name = "vmshm-comm-client0"
window_size = 33554432
seal = true

[[domains]]
id = "vmshm-comm-client1"
socket_path = "/run/vmshm/vmshm-comm-client1.sock"
memfd_name = "vmshm-comm-client1"
window_size = 33554432
seal = true
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
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/vmshm-2client-proxy.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x20000000",
      "slot": 1,
      "expected_size": 67108864,
      "fdt_node_name": "proxy-vmshm-manager",
      "fdt_compatible": "proxy-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client0.sock",
      "name": "vmshm-comm-client0-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm_client0",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f100000",
        "doorbell_size": "0x1000",
        "irq": 81
      }
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client1.sock",
      "name": "vmshm-comm-client1-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x26000000",
      "slot": 3,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm_client1",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f110000",
        "doorbell_size": "0x1000",
        "irq": 82
      }
    }
  ]
}
EOF

cat >"${CONFIG_DIR}/client0-vm-config.json" <<'EOF'
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
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/vmshm-2client-client0.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client0",
      "role": "client",
      "guest_phys_addr": "0x20000000",
      "slot": 1,
      "expected_size": 67108864,
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client0.sock",
      "name": "vmshm-comm-client0-client",
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

cat >"${CONFIG_DIR}/client1-vm-config.json" <<'EOF'
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
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/vmshm-2client-client1.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client1",
      "role": "client",
      "guest_phys_addr": "0x20000000",
      "slot": 1,
      "expected_size": 67108864,
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client1.sock",
      "name": "vmshm-comm-client1-client",
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

echo "Installed 2-client vmshm irq notify configs to ${CONFIG_DIR}"
