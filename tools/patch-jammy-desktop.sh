#!/usr/bin/env bash
# 修补 Armbian 构建框架：桌面安装前剔除 jammy 上不存在的软件包
#
# 背景
#   Armbian 的桌面软件包列表来自 armbian-config 的
#   /usr/share/armbian-config/desktops/yaml/*.yaml（common.yaml 的 tiers
#   + 各 DE 的 releases 覆盖块）。这份列表按 noble 及更新的发行版编写，
#   在 Ubuntu 22.04 (jammy) arm64 上缺少：
#       pipewire-libcamera / gstreamer1.0-libcamera   （noble 才引入）
#       glmark2-x11 / glmark2-es2-x11                 （jammy arm64 未构建）
#   apt 遇到不存在的包会整体拒绝安装，armbian-config 随即
#   "Error: <de> package install failed; aborting"，构建在根文件系统阶段
#   失败（实测 run 42053843414，跑满 2 小时才暴露）。
#
# 做法
#   在框架 lib/functions/rootfs/rootfs-create.sh 里，调用
#   `armbian-config --api module_desktops install` 的**前一步**插入过滤：
#   module_desktops 是用 parse_desktop_yaml.py 直接读
#   ${SDCARD}/usr/share/armbian-config/desktops/yaml/*.yaml 的，删掉这几行
#   即可，官方桌面流程（DM 注册 / autologin / skel / 首启）完全不变。
#
#   框架有两种布局，两种都支持：
#     v2（新版）：apt 安装 armbian-config 后直接调用 module_desktops
#     v1（旧版）：overlay_armbian_config_from_git 之后调用 module_desktops
#   统一锚定在 module_desktops 调用行之前插入，天然兼容两者。
#
# 用法
#   bash tools/patch-jammy-desktop.sh build      # build = 框架检出目录
#
# 幂等：已打过补丁会直接跳过；锚点找不到会立即失败（不白跑两小时）。
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

# 锚点：module_desktops 调用行（两种框架布局共用）
needle = 'armbian-config --api module_desktops install'
hits = [l for l in src.splitlines() if needle in l]
if len(hits) != 1:
    sys.exit("ERROR: 锚点 %r 命中 %d 次（期望 1 次），"
             "框架可能已改版，需要重新确认插入位置" % (needle, len(hits)))
anchor_line = hits[0]

inject = (
    "\t\t# --- %s: 剔除 jammy 上不存在的桌面包，避免 apt 整体拒绝安装 ---\n" % marker
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

src = src.replace(anchor_line + "\n", inject + anchor_line + "\n", 1)
io.open(path, 'w', encoding='utf-8', newline='').write(src)
print("==> 已插入 jammy 桌面包过滤逻辑（锚点: %s）" % needle)
PY

echo "==> 校验补丁"
grep -n -A6 "${MARKER}" "${TARGET}"
bash -n "${TARGET}"
echo "==> bash -n 通过"
