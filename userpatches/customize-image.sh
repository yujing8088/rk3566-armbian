#!/usr/bin/env bash
# Armbian 镜像定制钩子（在桌面安装完成、镜像打包之前执行）
#
# 调用方式（框架 lib/functions/rootfs/customize.sh）：
#   customize-image.sh <RELEASE> <LINUXFAMILY> <BOARD> <BUILD_DESKTOP> <ARCH>
#
# 本板（RK3566 EVB2 LP4X V10 + GSL1680 触摸 + DSI 面板）的实机结论：
#   1) 面板物理横装，显示必须旋转为 left（1280x800）才是正的；
#   2) 触摸芯片与面板装向差 90°，且有效区域只有 X 10..1017 / Y 9..632
#      （内核标称 0..1279 / 0..799），需要 udev 基础标定（轴交换+缩放+偏移）；
#   3) X11 下 libinput 不跟随显示旋转，需要运行时用 xinput 覆盖矩阵。
#
# 因此镜像内固化三件事：
#   /etc/udev/rules.d/99-touch-cal.rules      触摸基础标定（设备层，永久）
#   /etc/default/touch-rotate                 方向配置（可用 set-rotation 修改）
#   /usr/local/bin/touch-follow-rotate +
#   /etc/systemd/system/touch-follow.service  守护：固定方向 + 触摸跟随
# GNOME 额外强制 X11 会话（Wayland 下 xrandr/xinput 不可用）。
set -e

RELEASE="${1:-}"
LINUXFAMILY="${2:-}"
BOARD="${3:-}"
BUILD_DESKTOP="${4:-no}"
ARCH="${5:-}"

echo "==> customize-image: release=${RELEASE} board=${BOARD} desktop=${BUILD_DESKTOP} arch=${ARCH}"

# 只在桌面镜像上做（命令行版不需要 X 相关的守护）
if [ "${BUILD_DESKTOP}" != "yes" ]; then
	echo "==> 非桌面构建，跳过旋转/触摸固化"
	exit 0
fi

# ---------------------------------------------------------------- 1. X 工具
# xrandr / xinput 用于运行时固定方向与触摸映射
export DEBIAN_FRONTEND=noninteractive
if ! command -v xrandr >/dev/null 2>&1 || ! command -v xinput >/dev/null 2>&1; then
	echo "==> 安装 x11-xserver-utils / xinput"
	apt-get update -qq || true
	apt-get install -y --no-install-recommends x11-xserver-utils xinput || {
		echo "WARN: x11 工具安装失败（可稍后手动补装）"
	}
fi

# ------------------------------------------------------- 2. 触摸基础标定
# 数值来自板上实测：四角触摸取极值法（与点击顺序无关）
#   sx = 1.282504 * y - 0.014446
#   sy = 1.270109 * x - 0.009930
cat > /etc/udev/rules.d/99-touch-cal.rules <<'EOF'
# GSL1680 (silead_ts) 触摸基础标定：90° 装向差 + 实测有效区域缩放/偏移
ACTION=="add", SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="silead_ts", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 1.282504 -0.014446 1.270109 0 -0.009930"
EOF
echo "==> 写入 /etc/udev/rules.d/99-touch-cal.rules"

# ------------------------------------------------------------ 3. 方向配置
mkdir -p /etc/default
cat > /etc/default/touch-rotate <<'EOF'
# 屏幕方向与触摸配置（由 /usr/local/bin/set-rotation 修改）
# TOUCH_ROTATE: normal | left | right | inverted
TOUCH_OUTPUT=DSI-1
TOUCH_ROTATE=left
TOUCH_DEVICE=silead_ts
EOF
echo "==> 写入 /etc/default/touch-rotate（rotate=left, output=DSI-1）"

# ------------------------------------------------- 4. 守护：定向 + 触摸跟随
cat > /usr/local/bin/touch-follow-rotate <<'EOF'
#!/bin/bash
# 固定屏幕方向（TOUCH_ROTATE）并让触摸跟随实际方向。
# X11 下 libinput 不跟随 xrandr 旋转，必须用 xinput 覆盖变换矩阵。
[ -r /etc/default/touch-rotate ] && . /etc/default/touch-rotate
OUTPUT="${TOUCH_OUTPUT:-DSI-1}"
ROTATE="${TOUCH_ROTATE:-left}"
DEV="${TOUCH_DEVICE:-silead_ts}"

matrix_for() {
	case "$1" in
		# 注意：udev 基础标定里已含 90° 轴交换，故 left/right 与
		# 教科书矩阵表对调（板上实测校准，勿按直觉改）
		left)     echo "0 -1 1 1 0 0 0 0 1" ;;
		right)    echo "0 1 0 -1 0 1 0 0 1" ;;
		inverted) echo "-1 0 1 0 -1 1 0 0 1" ;;
		*)        echo "1 0 0 0 1 0 0 0 1" ;;
	esac
}

auths() {
	for f in /run/user/*/gdm/Xauthority /var/lib/gdm3/.Xauthority \
	         /run/user/*/.Xauthority /home/*/.Xauthority /root/.Xauthority; do
		[ -f "$f" ] && echo "$f"
	done
}

declare -A LAST
while :; do
	for sock in /tmp/.X11-unix/X*; do
		[ -S "$sock" ] || continue
		d=":${sock##*/X}"
		for a in $(auths); do
			q=$(DISPLAY="$d" XAUTHORITY="$a" xrandr --query 2>/dev/null) || continue
			echo "$q" | grep -q "^${OUTPUT} connected" || continue
			cur=$(echo "$q" | awk -v o="$OUTPUT" '$1==o {print $5}')
			if [ -n "$ROTATE" ] && [ "$cur" != "$ROTATE" ]; then
				DISPLAY="$d" XAUTHORITY="$a" xrandr --output "$OUTPUT" --rotate "$ROTATE" >/dev/null 2>&1 \
					&& cur="$ROTATE"
			fi
			m=$(matrix_for "$cur")
			if [ "${LAST[$d]}" != "$m" ]; then
				if ! DISPLAY="$d" XAUTHORITY="$a" xinput set-prop "$DEV" \
					"Coordinate Transformation Matrix" $m 2>/dev/null; then
					alt=$(DISPLAY="$d" XAUTHORITY="$a" xinput list --id-only silead 2>/dev/null | head -1)
					if [ -n "$alt" ]; then
						DISPLAY="$d" XAUTHORITY="$a" xinput set-prop "$alt" \
							"Coordinate Transformation Matrix" $m 2>/dev/null || true
					fi
				fi
				LAST[$d]="$m"
			fi
			break
		done
	done
	sleep 2
done
EOF
chmod +x /usr/local/bin/touch-follow-rotate
echo "==> 写入 /usr/local/bin/touch-follow-rotate"

# 便捷修改脚本：set-rotation left|right|normal|inverted
cat > /usr/local/bin/set-rotation <<'EOF'
#!/bin/bash
# 用法: set-rotation <normal|left|right|inverted>
case "$1" in
	normal|left|right|inverted) ;;
	*) echo "用法: set-rotation <normal|left|right|inverted>"; exit 1 ;;
esac
sed -i -E "s/^TOUCH_ROTATE=.*/TOUCH_ROTATE=$1/" /etc/default/touch-rotate
systemctl restart touch-follow.service 2>/dev/null || true
echo "已设为 $1（2 秒内生效）"
EOF
chmod +x /usr/local/bin/set-rotation

cat > /etc/systemd/system/touch-follow.service <<'EOF'
[Unit]
Description=Fix display rotation and touch mapping (X11)
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
Environment=HOME=/root
ExecStart=/usr/local/bin/touch-follow-rotate
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
EOF
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sf /etc/systemd/system/touch-follow.service \
       /etc/systemd/system/graphical.target.wants/touch-follow.service
echo "==> 写入并启用 touch-follow.service"

# --------------------------------------------- 5. GNOME: 强制 X11 会话
# GNOME 在 Wayland 下 xrandr / xinput 均不可用，无法固化方向与触摸映射；
# 关掉 Wayland 让 gdm3 走 Xorg 会话，与实机验证过的方案一致。
if [ -f /etc/gdm3/custom.conf ] || [ -d /etc/gdm3 ] || dpkg -s gdm3 >/dev/null 2>&1; then
	mkdir -p /etc/gdm3
	conf=/etc/gdm3/custom.conf
	if [ ! -f "$conf" ]; then
		printf '[daemon]\nWaylandEnable=false\n' > "$conf"
	elif grep -qi '^[[:space:]]*WaylandEnable' "$conf"; then
		sed -i -E 's/^[[:space:]]*#?[[:space:]]*WaylandEnable=.*/WaylandEnable=false/' "$conf"
	elif grep -q '^\[daemon\]' "$conf"; then
		sed -i '0,/^\[daemon\]/s//[daemon]\nWaylandEnable=false/' "$conf"
	else
		printf '\n[daemon]\nWaylandEnable=false\n' >> "$conf"
	fi
	echo "==> gdm3 已关闭 Wayland（走 Xorg 会话）"
fi

# 供 GDM 自动登录使用：确保 X11 会话名存在（gdm3 关 Wayland 后自动选 gnome-xorg）

echo "==> customize-image 完成"
