#!/usr/bin/env bash
# 针对 fnOS (ophub) 内核 6.18.18-trim 旁路编译 panel-simple-dsi.ko + silead.ko
# 设计要点：
#   - fnOS 内核 CONFIG_MODVERSIONS=n / CONFIG_MODULE_SIG=n → 只要
#     vermagic 一致即可干净加载，无需 CRC 对齐
#   - CONFIG_LOCALVERSION_AUTO=n → 用 LOCALVERSION=-trim 还原 release 字符串
#   - DEBUG_INFO 关闭仅影响 -g，不影响 ABI/vermagic，用来加速 CI
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KVER=6.18.18
CROSS=aarch64-linux-gnu-
WORK="${GITHUB_WORKSPACE:-$(mktemp -d)}"
MODDIR="$KIT_DIR/modules"

cd "$WORK"

echo "== [1/6] 安装工具链"
sudo apt-get update -qq
sudo apt-get install -y -qq gcc-aarch64-linux-gnu bc bison flex libssl-dev libelf-dev >/dev/null

echo "== [2/6] 下载内核源码 linux-$KVER.tar.xz"
if [ ! -f "linux-$KVER.tar.xz" ]; then
    # 优先镜像，失败回退 kernel.org
    curl -fL --retry 3 -o "linux-$KVER.tar.xz" \
        "https://mirrors.tuna.tsinghua.edu.cn/kernel/v6.x/linux-$KVER.tar.xz" \
    || curl -fL --retry 3 -o "linux-$KVER.tar.xz" \
        "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$KVER.tar.xz"
fi
rm -rf "linux-$KVER"
tar xf "linux-$KVER.tar.xz"
cd "linux-$KVER"

echo "== [3/6] 准备内核构建树（还原 -trim 后缀）"
cp "$KIT_DIR/config-6.18.18-trim" .config
scripts/config --disable DEBUG_INFO          # 提速，无 ABI 影响
make ARCH=arm64 CROSS_COMPILE="$CROSS" LOCALVERSION=-trim olddefconfig
make ARCH=arm64 CROSS_COMPILE="$CROSS" LOCALVERSION=-trim modules_prepare -j"$(nproc)"

echo "== [4/6] 应用 silead 触摸补丁并取出源文件"
patch -p1 --fuzz=3 < "$KIT_DIR/patches/1000-input-silead-support-gslx680-download-protocol.patch"
cp drivers/input/touchscreen/silead.c "$MODDIR/silead.c"

echo "== [5/6] 编译模块"
make ARCH=arm64 CROSS_COMPILE="$CROSS" LOCALVERSION=-trim M="$MODDIR" modules -j"$(nproc)"

echo "== [6/6] 校验 vermagic"
for ko in panel-simple-dsi silead; do
    v=$(modinfo -F vermagic "$MODDIR/$ko.ko")
    echo "  $ko.ko vermagic: $v"
    case "$v" in
        *6.18.18-trim*) : ;;
        *) echo "!! vermagic 不含 6.18.18-trim，加载会失败" >&2; exit 1 ;;
    esac
done

# 顺手生成 sha256
( cd "$MODDIR" && sha256sum panel-simple-dsi.ko silead.ko > SHA256SUMS )
cat "$MODDIR/SHA256SUMS"
echo "== 完成，产物在 fnos-modules/modules/"
