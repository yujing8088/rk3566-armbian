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
# 因此镜像内固化这些内容（全部在构建期完成，首次开机即是成品状态）：
#   /etc/udev/rules.d/99-touch-cal.rules      触摸基础标定（设备层，永久）
#   /etc/default/touch-rotate                 方向配置（可用 set-rotation 修改）
#   /usr/local/bin/touch-follow-rotate +
#   /etc/systemd/system/touch-follow.service  守护：固定方向 + 触摸跟随
#   armbianEnv.txt: bootlogo + quiet splash   开机动画，不刷文字
#   预置用户 admin/123 + 跳过 firstlogin 向导  首启直进桌面，不停在字符界面
#   中文环境: zh_CN.UTF-8 + Noto CJK + ibus-libpinyin
# GNOME 额外强制 X11 会话（Wayland 下 xrandr/xinput 不可用）。
#
# 可用环境变量覆盖：ARMBIAN_PRESET_USER / ARMBIAN_PRESET_PASS
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

# ------------------------------------------- 6. 纯图形启动（plymouth + 静默）
# 目标：从内核启动开始就是开机动画，不刷文字；首启直接进桌面，不落字符向导。
if [ -f /boot/armbianEnv.txt ]; then
	if grep -q '^bootlogo=' /boot/armbianEnv.txt; then
		sed -i 's/^bootlogo=.*/bootlogo=true/' /boot/armbianEnv.txt
	else
		echo 'bootlogo=true' >> /boot/armbianEnv.txt
	fi

	# quiet/splash：内核与 systemd 不再向控制台刷日志（串口调试仍可用
	# 通过 loglevel 控制；先保留 console=both 便于排查）
	QUIET_ARGS="quiet splash plymouth.ignore-serial-consoles loglevel=3 consoleblank=0 vt.global_cursor_default=0"
	if grep -q '^extraargs=' /boot/armbianEnv.txt; then
		grep -q 'plymouth.ignore-serial-consoles' /boot/armbianEnv.txt || \
			sed -i -E "s|^extraargs=(.*)$|extraargs=\1 ${QUIET_ARGS}|" /boot/armbianEnv.txt
	else
		echo "extraargs=${QUIET_ARGS}" >> /boot/armbianEnv.txt
	fi
	echo "==> armbianEnv.txt 已启用 bootlogo + quiet/splash"
	sed -n '1,20p' /boot/armbianEnv.txt || true
fi

# plymouth 主题：desktop 构建已装 armbian-plymouth-theme，这里确保它是默认主题
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
	if [ -d /usr/share/plymouth/themes/armbian ]; then
		plymouth-set-default-theme armbian >/dev/null 2>&1 || true
	else
		plymouth-set-default-theme -l 2>/dev/null | head -5 || true
		plymouth-set-default-theme bgrt >/dev/null 2>&1 || plymouth-set-default-theme spinner >/dev/null 2>&1 || true
	fi
	# 主题变化需要重建 initramfs 才会在开机早期生效
	update-initramfs -u >/dev/null 2>&1 || true
	echo "==> plymouth 主题: $(plymouth-set-default-theme 2>/dev/null || cat /etc/plymouth/plymouthd.conf 2>/dev/null | grep -i theme)"
fi

# ------------------------------------ 7. 预置用户 + 跳过字符界面首启向导
# Armbian 桌面版首启落在 tty1 跑 armbian-firstlogin（改密/建用户/选 shell），
# 这就是「装了图形版却是命令行」的根源。这里预置用户并删除触发标记，
# 首启直接由 display-manager 接管，全程图形。
NEW_USER="${ARMBIAN_PRESET_USER:-admin}"
NEW_PASS="${ARMBIAN_PRESET_PASS:-123}"
if ! id "$NEW_USER" >/dev/null 2>&1; then
	useradd -m -s /bin/bash -c "Armbian user" "$NEW_USER" || useradd -m -s /bin/bash "$NEW_USER"
	echo "${NEW_USER}:${NEW_PASS}" | chpasswd
	echo "==> 预置用户 ${NEW_USER}（密码同 /etc/default 提示，可在桌面里改）"
fi
# 补齐常用权限组（不存在的组自动跳过）
for g in sudo audio video plugdev input netdev bluetooth render; do
	getent group "$g" >/dev/null 2>&1 && usermod -aG "$g" "$NEW_USER" 2>/dev/null || true
done
rm -f /root/.not_logged_in_yet
rm -f /etc/profile.d/armbian-check-first-login.sh 2>/dev/null || true
echo "==> 已跳过 armbian-firstlogin 字符向导"

# 时区（避免首启向导里那一步，也避免桌面时间偏差）
ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime 2>/dev/null || true
[ -f /etc/timezone ] && echo "Asia/Shanghai" > /etc/timezone || true

# ----------------------------------------- 8. 图形登录 + 自动登录（无需密码）
# 会话名按实际安装的 xsessions 选择，避免指向不存在的会话导致登录失败
pick_session() {
	for s in gnome-xorg ubuntu-xorg xfce mate cinnamon; do
		[ -f "/usr/share/xsessions/${s}.desktop" ] && { echo "$s"; return; }
	done
	for f in /usr/share/xsessions/*.desktop; do
		[ -f "$f" ] && { basename "$f" .desktop; return; }
	done
}
SESSION_NAME="$(pick_session)"
echo "==> 选用 X11 会话: ${SESSION_NAME:-<none>}"

if [ -d /etc/gdm3 ]; then
	conf=/etc/gdm3/custom.conf
	add_gdm() { # $1 key=value
		if grep -q "^$1" "$conf" 2>/dev/null; then
			sed -i -E "s|^${1%%=*}=.*|$1|" "$conf"
		elif grep -q '^\[daemon\]' "$conf"; then
			sed -i "0,/^\[daemon\]/s||[daemon]\n$1|" "$conf"
		else
			printf '\n[daemon]\n%s\n' "$1" >> "$conf"
		fi
	}
	add_gdm "AutomaticLoginEnable=true"
	add_gdm "AutomaticLogin=${NEW_USER}"
	echo "==> gdm3 自动登录: ${NEW_USER}"
fi

if [ -d /etc/lightdm ]; then
	mkdir -p /etc/lightdm/lightdm.conf.d
	cat > /etc/lightdm/lightdm.conf.d/22-armbian-autologin.conf <<EOF
[Seat:*]
autologin-user=${NEW_USER}
autologin-user-timeout=0
user-session=${SESSION_NAME:-xfce}
EOF
	echo "==> lightdm 自动登录: ${NEW_USER}"
fi

# AccountsService：把用户默认会话钉到 X11 那个，避免 gdm 选了 Wayland
if [ -n "$SESSION_NAME" ]; then
	mkdir -p /var/lib/AccountsService/users
	cat > "/var/lib/AccountsService/users/${NEW_USER}" <<EOF
[User]
Language=
XSession=${SESSION_NAME}
SystemAccount=false
EOF
fi

# 显式启用显示管理器（跳过字符向导后，没人替我们 enable 它）
if [ -e /lib/systemd/system/gdm3.service ]; then
	ln -sf /lib/systemd/system/gdm3.service /etc/systemd/system/display-manager.service
	echo "==> display-manager -> gdm3"
elif [ -e /lib/systemd/system/lightdm.service ]; then
	ln -sf /lib/systemd/system/lightdm.service /etc/systemd/system/display-manager.service
	echo "==> display-manager -> lightdm"
fi

# GNOME 首次登录的「欢迎向导」也跳过（否则进桌面弹设置页）
HOME_DIR="/home/${NEW_USER}"
mkdir -p "${HOME_DIR}/.config"
touch "${HOME_DIR}/.config/gnome-initial-setup-done"
chown -R "${NEW_USER}:${NEW_USER}" "${HOME_DIR}" 2>/dev/null || true

# 默认启动目标 = 图形
ln -sf /lib/systemd/system/graphical.target /etc/systemd/system/default.target
echo "==> default.target -> graphical.target"

# --------------------------------------- 9. 中文环境（界面语言 + 中文字体 + 输入法）
ZH_PKGS="language-pack-zh-hans language-pack-zh-hans-base language-pack-gnome-zh-hans \
fonts-noto-cjk fonts-wqy-zenhei ibus ibus-libpinyin ibus-gtk3 ibus-gtk im-config locales"
echo "==> 安装中文语言包/字体/输入法"
apt-get install -y --no-install-recommends $ZH_PKGS || \
	apt-get install -y $ZH_PKGS || echo "WARN: 部分中文包安装失败（继续）"

# 生成并启用 zh_CN.UTF-8（en_US 保留，避免部分工具 fallback 报错）
sed -i -E 's/^#\s*(zh_CN\.UTF-8 UTF-8)/\1/' /etc/locale.gen 2>/dev/null || true
grep -q '^zh_CN.UTF-8 UTF-8' /etc/locale.gen 2>/dev/null || echo 'zh_CN.UTF-8 UTF-8' >> /etc/locale.gen
locale-gen 2>/dev/null || true

cat > /etc/default/locale <<'EOF'
LANG=zh_CN.UTF-8
LANGUAGE=zh_CN:zh
LC_MESSAGES=zh_CN.UTF-8
EOF
# 系统级 LANG（GNOME/gdm 会话从 PAM 环境继承）
if grep -q '^LANG=' /etc/environment; then
	sed -i 's|^LANG=.*|LANG=zh_CN.UTF-8|' /etc/environment
else
	echo 'LANG=zh_CN.UTF-8' >> /etc/environment
fi

# 输入法框架：ibus + libpinyin（中文拼音）
if [ -d /etc/X11 ]; then
	mkdir -p /etc/X11/xinit
	printf 'XIM=ibus\nXIM_PROGRAM=/usr/bin/ibus-daemon\nXIM_ARGS="--xim -d"\n' \
		> /etc/X11/xinit/xinputrc
	chmod 644 /etc/X11/xinit/xinputrc
fi
cat >> /etc/environment <<'EOF'
GTK_IM_MODULE=ibus
QT_IM_MODULE=ibus
XMODIFIERS=@im=ibus
EOF

# GNOME 默认输入源：英文键盘 + 拼音（系统级 dconf 默认值，用户可自行改）
mkdir -p /etc/dconf/profile /etc/dconf/db/local.d
printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user
cat > /etc/dconf/db/local.d/00-cn-ime <<'EOF'
[org/gnome/desktop/input-sources]
sources=[('xkb','us'),('ibus','libpinyin')]
current=1

[org/gnome/desktop/interface]
# 时间显示中文格式
clock-format='24h'
EOF
command -v dconf >/dev/null 2>&1 && dconf update >/dev/null 2>&1 || true
echo "==> 中文环境完成（LANG=zh_CN.UTF-8，ibus-libpinyin）"

echo "==> customize-image 完成"
