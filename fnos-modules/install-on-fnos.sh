#!/usr/bin/env bash
# fnOS 板端安装脚本：把云端编好的两个 .ko 装进 6.18.18-trim
# 用法：scp -r 产物目录 到 fnOS 后，root 执行 bash install-on-fnos.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REL="$(uname -r)"

[ "$REL" = "6.18.18-trim" ] || { echo "!! 内核版本不符: $REL (需要 6.18.18-trim)"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "!! 请用 root 执行"; exit 1; }

echo "== 安装模块"
install -Dm644 "$HERE/panel-simple-dsi.ko" "/lib/modules/$REL/kernel/drivers/gpu/drm/panel/panel-simple-dsi.ko"
install -Dm644 "$HERE/silead.ko"           "/lib/modules/$REL/kernel/drivers/input/touchscreen/silead.ko"

echo "== 安装触摸固件"
install -Dm644 "$HERE/gsl1680-evb2.fw" "/lib/firmware/silead/gsl1680-evb2.fw"

echo "== depmod + 开机自动加载"
depmod -a
mkdir -p /etc/modules-load.d
printf 'panel-simple-dsi\nsilead\n' > /etc/modules-load.d/evb2.conf

echo "== 校验"
modinfo -F vermagic panel-simple-dsi | head -1
modinfo -F vermagic silead | head -1

echo "完成。重启后：屏幕应点亮（fbcon 控制台），触摸可用。"
echo "验证命令：dmesg | grep -Ei 'panel|dsi|silead|gslx'"
