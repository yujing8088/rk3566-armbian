#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 编译板级 DTS -> DTB
#   优先用系统 dtc + cpp（Linux 正常路径）
#   没有 cpp 时退化为 tools/pp.py；没有 dtc 时用 tools/mingw64/bin/dtc.exe（Windows）
#
# 用法： ./tools/build-dtb.sh
# 产物： dts/rk3566-evb2-lp4x-v10.dtb + userpatches/dtb/ + out/
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
REF="${ROOT}/refs"
DTS="${ROOT}/dts/rk3566-evb2-lp4x-v10.dts"
OUT_DTB="${ROOT}/dts/rk3566-evb2-lp4x-v10.dtb"

[[ -f "${DTS}" ]] || { echo "缺少 ${DTS}"; exit 1; }
[[ -d "${REF}/arch/arm64/boot/dts/rockchip" ]] || {
	echo "缺少 refs/ 参考树（内核 dtsi 依赖）。执行：python tools/fetch_includes.py"; exit 1; }

# dtc
DTC="$(command -v dtc || true)"
[[ -z "${DTC}" && -x "${HERE}/mingw64/bin/dtc.exe" ]] && DTC="${HERE}/mingw64/bin/dtc.exe"
[[ -n "${DTC}" ]] || { echo "找不到 dtc（apt install device-tree-compiler）"; exit 1; }
echo "dtc: ${DTC}"

TMP="${TMPDIR:-/tmp}/armbian-dts-$$.dts"

if command -v cpp >/dev/null 2>&1; then
	echo "==> cpp + dtc"
	cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
		-I "${REF}/include" \
		-I "${REF}/arch/arm64/boot/dts/rockchip" \
		"${DTS}" -o "${TMP}"
else
	echo "==> python 预处理器 + dtc（无 cpp）"
	python "${HERE}/pp.py" "${DTS}" "${TMP}" \
		-I "${REF}/include" \
		-I "${REF}/arch/arm64/boot/dts/rockchip"
fi

"${DTC}" -I dts -O dtb -o "${OUT_DTB}" "${TMP}"
echo "==> ${OUT_DTB} ($(stat -c%s "${OUT_DTB}" 2>/dev/null || wc -c < "${OUT_DTB}") bytes)"

mkdir -p "${ROOT}/userpatches/dtb" "${ROOT}/out"
cp -f "${OUT_DTB}" "${ROOT}/userpatches/dtb/rk3566-evb2-lp4x-v10.dtb"
cp -f "${OUT_DTB}" "${ROOT}/out/rk3566-evb2-lp4x-v10.dtb"
echo "==> 已同步到 userpatches/dtb/ 与 out/"
