#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 用 rkdeveloptool 把 Armbian 镜像整盘写到 RK3566 EVB2 的 eMMC
#
# 前置：
#   1) 已装 rkdeveloptool（apt install rkdeveloptool 或自行编译）
#   2) 板子进入 MaskROM：断电 → 按住 MASKROM/RECOVERY 键(或短接 eMMC CLK) → 插 USB-OTG → 上电
#   3) sudo ./flash-linux.sh /path/to/Armbian-....img
#
# 说明：Armbian 镜像自带 GPT + idbloader(sector 64) + u-boot(sector 16384) + boot + rootfs，
#       整盘从 LBA0 写入即可，不需要 partition/parameter 文件。
# ---------------------------------------------------------------------------
set -euo pipefail

IMG="${1:?用法: $0 <armbian.img> [loader.bin]}"
LOADER="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/MiniLoaderAll.bin}"

[[ -f "${IMG}" ]]    || { echo "找不到镜像: ${IMG}"; exit 1; }
[[ -f "${LOADER}" ]] || { echo "找不到 loader: ${LOADER}（可从原厂固件包里取 MiniLoaderAll.bin）"; exit 1; }

echo "==> 检查 MaskROM 设备"
rkdeveloptool ld || { echo "未发现 MaskROM 设备"; exit 1; }

echo "==> 下载 loader 到 DRAM"
rkdeveloptool db "${LOADER}"
sleep 2
rkdeveloptool ld

SECTORS=$(( ($(stat -c%s "${IMG}") + 511) / 512 ))
echo "==> 写 ${IMG} 到 eMMC (${SECTORS} sectors)"
# wl = write by LBA
rkdeveloptool wl 0 "${IMG}"

echo "==> 复位设备"
rkdeveloptool rd
echo
echo "完成。串口(UART2, 1500000 8N1, 3.3V TTL) 可看到 U-Boot / 内核启动日志。"
echo "首次启动后登录 root/1234，若根分区未占满 eMMC，执行： armbian-resize-filesystem"
