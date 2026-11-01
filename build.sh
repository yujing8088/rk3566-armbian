#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 一键构建 Armbian for RK3566 EVB2 LP4X V10
#
# 用法（在 Linux 主机 / 虚拟机 / WSL2 Ubuntu 里执行）：
#   ./build.sh                 # 默认：Debian bookworm, 当前内核分支, 最小化镜像
#   ./build.sh bookworm current
#   ./build.sh noble edge
#   USE_DOCKER=yes ./build.sh  # 宿主机不是 Ubuntu 22.04/Debian 12 时用 docker
#
# 依赖：git, 约 30GB 空闲磁盘, 8GB+ 内存（首次会下载 ~10GB 源码/工具链）
# 产物：build/output/images/Armbian-*.img
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="rk3566-evb2-lp4x-v10"
RELEASE="${1:-bookworm}"
BRANCH="${2:-current}"
BUILD_DIR="${BUILD_DIR:-${HERE}/build}"
ARMBIAN_BRANCH="${ARMBIAN_BRANCH:-main}"

echo "==> board=${BOARD} release=${RELEASE} branch=${BRANCH}"

# 1) 取 Armbian 构建框架
if [[ ! -d "${BUILD_DIR}/.git" ]]; then
	echo "==> cloning armbian/build (shallow)"
	git clone --depth 1 -b "${ARMBIAN_BRANCH}" https://github.com/armbian/build.git "${BUILD_DIR}"
else
	echo "==> reusing ${BUILD_DIR}"
fi

# 2) 同步我们的板级支持（userpatches 是 Armbian 官方的外挂目录）
echo "==> syncing userpatches"
mkdir -p "${BUILD_DIR}/userpatches"
cp -rv "${HERE}/userpatches/config" "${BUILD_DIR}/userpatches/"
cp -rv "${HERE}/userpatches/dtb"    "${BUILD_DIR}/userpatches/"
[[ -d "${HERE}/userpatches/patch" ]] && cp -rv "${HERE}/userpatches/patch" "${BUILD_DIR}/userpatches/"

# 3) 校验 dtb 存在
if [[ ! -f "${BUILD_DIR}/userpatches/dtb/${BOARD}.dtb" ]]; then
	echo "!! 缺少 userpatches/dtb/${BOARD}.dtb" >&2
	exit 1
fi

cd "${BUILD_DIR}"

DOCKER_ARG=""
if [[ "${USE_DOCKER:-no}" == "yes" ]]; then
	DOCKER_ARG="docker"
fi

# 4) 编译
# shellcheck disable=SC2086
./compile.sh ${DOCKER_ARG} build \
	BOARD="${BOARD}" \
	BRANCH="${BRANCH}" \
	RELEASE="${RELEASE}" \
	BUILD_MINIMAL=yes \
	BUILD_DESKTOP=no \
	KERNEL_CONFIGURE=no \
	EXPERT=yes \
	SHARE_LOG=yes

echo
echo "==> 完成。镜像在： ${BUILD_DIR}/output/images/"
ls -lh "${BUILD_DIR}/output/images/" | tail -20
