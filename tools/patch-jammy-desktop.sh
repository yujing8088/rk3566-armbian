#!/usr/bin/env bash
# 修补 Armbian 构建框架：桌面安装前剔除 jammy 上不存在的软件包
#
# 背景
#   Armbian 的桌面软件包列表来自 armbian/configng 的
#   tools/modules/desktops/yaml/*.yaml（common.yaml 的 tiers + 各 DE 的
#   releases 覆盖块）。这份列表是按 noble 及更新的发行版写的，在
#   Ubuntu 22.04 (jammy) arm64 上缺少以下 4 个包：
#       pipewire-libcamera / gstreamer1.0-libcamera   （noble 才引入）
#       glmark2-x11 / glmark2-es2-x11                 （jammy arm64 未构建）
#   apt 遇到不存在的包会整体拒绝安装，armbian-config 随即
#   "Error: xfce package install failed; aborting"，整个构建在根文件系统
#   阶段失败（实测 run 42053843414，跑满 2 小时后才暴露）。
#
# 做法
#   框架在 lib/functions/rootfs/rootfs-create.sh 里完成
#   overlay_armbian_config_from_git 之后，就在 chroot 内调用
#   armbian-config --api module_desktops install，而这个模块是用
#   parse_desktop_yaml.py 直接读取 <SDCARD>/usr/share/armbian-config/
#   desktops/yaml/*.yaml 的。所以只要在 overlay 之后、调用之前把这几行
#   删掉，官方桌面安装流程（DM 注册 / autologin / skel / 首启）完全不变。
#
# 用法
#   bash tools/patch-jammy-desktop.sh build      # build = 框架检出目录
#
# 幂等：已打过补丁会直接跳过。
set -euo pipefail

BUILD_DIR="${1:-build}"
TARGET="${BUILD_DIR}/lib/functions/rootfs/rootfs-create.sh"
MARKER="jammy-pkg-filter"

if [ ! -f "${TARGET}" ]; then
	echo "ERROR: 找不到 ${TARGET}（框架是否已检出？）" >&2
	exit 1
fi

if grep -q "${MARKER}" "${TARGET}"; then
	echo "==> 补丁已存在，跳过"
	exit 0
fi

python3 - "${TARGET}" "${MARKER}" <<'PY'
import io, sys

path, marker = sys.argv[1], sys.argv[2]
src = io.open(path, encoding='utf-8', newline='').read()

anchor = "\t\toverlay_armbian_config_from_git\n"
if src.count(anchor) != 1:
    sys.exit("ERROR: 锚点 overlay_armbian_config_from_git 命中 %d 次（期望 1 次），"
             "框架可能已改版，需要重新确认插入位置" % src.count(anchor))

inject = (
    anchor
    + "\t\t# --- %s: 剔除 jammy 上不存在的桌面包，避免 apt 整体拒绝安装 ---\n" % marker
    + "\t\tif [[ \"${RELEASE}\" == \"jammy\" ]]; then\n"
    + "\t\t\twhile IFS= read -r _yaml; do\n"
    + "\t\t\t\tdisplay_alert \"剔除 jammy 缺失的桌面包\" \"${_yaml}\" \"info\"\n"
    + "\t\t\t\tsed -i -E '/^[[:space:]]*-[[:space:]]*"
      "(pipewire-libcamera|gstreamer1\\.0-libcamera|glmark2-x11|glmark2-es2-x11)"
      "[[:space:]]*(#.*)?$/d' \"${_yaml}\"\n"
    + "\t\t\tdone < <(find \"${SDCARD}/usr/share/armbian-config\" -type f "
      "-name '*.yaml' 2>/dev/null)\n"
    + "\t\tfi\n"
)

src = src.replace(anchor, inject, 1)
io.open(path, 'w', encoding='utf-8', newline='').write(src)
print("==> 已插入 jammy 桌面包过滤逻辑")
PY

echo "==> 校验补丁"
grep -n -A6 "${MARKER}" "${TARGET}"
bash -n "${TARGET}"
echo "==> bash -n 通过"
