# Rockchip RK3566 EVB2 LP4X (V10) - Armbian board config
# 板卡来源：由厂商 Android 11 固件 DTB 反推（model: Rockchip RK3566 EVB2 LP4X V10 Board）
# 关键特征：无 PMIC（PWM 供电）、eMMC + TF、SDIO WiFi(RK960/AIC8800)、RMII 100M PHY、MIPI-DSI 面板
BOARD_NAME="RK3566 EVB2 LP4X V10"
BOARD_VENDOR="rockchip"
BOOT_SOC="rk3566"
BOARDFAMILY="rk35xx"
BOARD_MAINTAINER="local"
INTRODUCED="2026"
BOOTCONFIG="generic-rk3568_defconfig"
KERNEL_TARGET="current,edge"
FULL_DESKTOP="no"
BOOT_LOGO="none"
BOOT_FDT_FILE="rockchip/rk3566-evb2-lp4x-v10.dtb"
BOOT_SCENARIO="spl-blobs"
IMAGE_PARTITION_TABLE="gpt"
SERIALCON="ttyS2"

# ---------------------------------------------------------------------------
# 自研 DTB 安装：镜像构建收尾时把预编译好的 dtb 放进 /boot/dtb-*/rockchip/
# （避免给内核打补丁，后续升级内核也不会把 dtb 弄丢 —— 如果内核升级后 dtb 目录
#   变了，重跑 build.sh 即可，或把 dts/ 里的 dts 提交给上游内核）
# ---------------------------------------------------------------------------
function pre_customize_image__install_evb2_dtb() {
	local dtb="${SRC}/userpatches/dtb/rk3566-evb2-lp4x-v10.dtb"
	[[ -f "${dtb}" ]] || exit_with_error "missing custom dtb: ${dtb}"

	local target found=0
	for target in "${SDCARD}"/boot/dtb*/rockchip; do
		[[ -d "${target}" ]] || continue
		run_host_command_logged cp -v "${dtb}" "${target}/"
		found=1
	done
	# 兼容 /boot/dtb 直接是目录（非符号链接）的情况
	if [[ ${found} -eq 0 && -d "${SDCARD}/boot/dtb/rockchip" ]]; then
		run_host_command_logged cp -v "${dtb}" "${SDCARD}/boot/dtb/rockchip/"
		found=1
	fi
	[[ ${found} -eq 1 ]] || exit_with_error "no /boot/dtb*/rockchip directory found in image"

	# 确保 armbianEnv.txt 指向我们的 dtb
	# 注意：run_host_command_logged 会把参数拼成字符串交给 bash -c 执行，
	# sed 表达式里的 | 和 * 会被二次解析（实测报 "unterminated s command"），
	# 所以这里直接用 python3 原地改写，绕开一切 shell 引号问题。
	local envfile="${SDCARD}/boot/armbianEnv.txt"
	if [[ -f "${envfile}" ]]; then
		python3 - "${envfile}" "${BOOT_FDT_FILE}" <<-'PYEOF'
			import re, sys
			path, val = sys.argv[1], sys.argv[2]
			text = open(path, encoding="utf-8").read()
			line = "fdtfile=%s" % val
			if re.search(r"(?m)^fdtfile=", text):
			    text = re.sub(r"(?m)^fdtfile=.*$", line, text)
			else:
			    text = text.rstrip("\n") + "\n" + line + "\n"
			open(path, "w", encoding="utf-8").write(text)
		PYEOF
		display_alert "fdtfile set" "$(grep '^fdtfile=' "${envfile}" || true)" "info"
	else
		display_alert "armbianEnv.txt missing" "${envfile} - U-Boot 会用默认 dtb" "wrn"
	fi

	display_alert "Custom DTB installed" "rk3566-evb2-lp4x-v10.dtb -> /boot/dtb*/rockchip/" "info"
}

# ---------------------------------------------------------------------------
# 主线 U-Boot（binman 生成的 u-boot-rockchip.bin，自带 DDR init + BL31）
# 与 Armbian 官方 rk3566-box-demo 板级配置同一套做法，参考设计相近，可靠性高
# ---------------------------------------------------------------------------
function post_family_config__evb2_use_mainline_uboot() {
	display_alert "$BOARD" "Using mainline U-Boot for $BOARD / $BRANCH" "info"

	declare -g BOOTSOURCE="https://github.com/u-boot/u-boot.git"
	declare -g BOOTBRANCH="tag:v2025.10"
	declare -g BOOTPATCHDIR="v2025.10"

	declare -g UBOOT_TARGET_MAP="BL31=${RKBIN_DIR}/${BL31_BLOB} ROCKCHIP_TPL=${RKBIN_DIR}/${DDR_BLOB};;u-boot-rockchip.bin"

	unset uboot_custom_postprocess write_uboot_platform write_uboot_platform_mtd

	function write_uboot_platform() {
		dd "if=$1/u-boot-rockchip.bin" "of=$2" bs=32k seek=1 conv=notrunc status=none
	}
}
