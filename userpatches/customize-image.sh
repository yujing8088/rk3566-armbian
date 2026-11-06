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

# plymouth 主题：自研「固定横屏」启动画面
# 面板原生 800x1280（竖屏）但横装，X 会话用 rotate left。plymouth 0.9.5 不支持
# 旋转，console=ttyS2 还会强制 details 文字模式（extraargs 已带
# plymouth.ignore-serial-consoles 规避）。这里用 script 插件 + 预旋转位图，
# 方向与 X left 严格一致：buffer[bx][by] = logical[dx][dy], bx=dy, by=W-1-dx
# （逆时针 90°）。已在实机经 DRM 扫描缓冲逐像素验证。
if ls /usr/lib/*/plymouth/script.so >/dev/null 2>&1; then
	TH=/usr/share/plymouth/themes/evb2-landscape
	mkdir -p "$TH"
	base64 -d > "$TH/splash_bg.png" <<'B64_SPLASH'
iVBORw0KGgoAAAANSUhEUgAAAyAAAAUACAIAAAAwbqEzAADN/ElEQVR4nOzdB3iU55no/Xeqeu+9
IKECqoBEbwIbDAZ7Y2xsx47tbLYkm88nJ1uS3c3ZPfk2GzuON5t8J5uN49ixs44d90psDJjeESCh
igCh3jWjNqOp34We+D2zEmCBpmn0/12+dM2M3nnfR69k6eZ+7ud+JAkAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
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
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAUKnx/wFrPf8kYIcXfwAAAABJ
RU5ErkJggg==
B64_SPLASH
	cat > "$TH/evb2-landscape.plymouth" <<'EOF'
[Plymouth Theme]
Name=evb2-landscape
Description=Fixed landscape boot splash for RK3566 EVB2 (DPI panel mounted sideways)
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/evb2-landscape
ScriptFile=/usr/share/plymouth/themes/evb2-landscape/evb2-landscape.script
EOF
	cat > "$TH/evb2-landscape.script" <<'EOF'
# Fixed-landscape splash for RK3566 EVB2 (artwork pre-rotated to match X left)
Window.SetBackgroundTopColor(0, 0, 0);
Window.SetBackgroundBottomColor(0, 0, 0);

bg.image = Image("splash_bg.png");
bg.sprite = Sprite(bg.image);
bg.sprite.SetX(Window.GetX() + (Window.GetWidth()  - bg.image.GetWidth())  / 2);
bg.sprite.SetY(Window.GetY() + (Window.GetHeight() - bg.image.GetHeight()) / 2);
bg.sprite.SetOpacity(1);

fun quit_callback ()
  {
    bg.sprite.SetOpacity(0);
  }
Plymouth.SetQuitFunction(quit_callback);
EOF
	update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
		default.plymouth "$TH/evb2-landscape.plymouth" 200 >/dev/null 2>&1 || true
	update-alternatives --set default.plymouth "$TH/evb2-landscape.plymouth" >/dev/null 2>&1 || true
	echo "==> plymouth 主题: evb2-landscape（固定横屏）"
else
	[ -d /usr/share/plymouth/themes/armbian ] && plymouth-set-default-theme armbian >/dev/null 2>&1 || true
	echo "==> WARN: script 插件缺失，回退默认主题"
fi
# 主题变化需要重建 initramfs 才会在开机早期生效
update-initramfs -u >/dev/null 2>&1 || true

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

# --------------------------------------- 9b. 终端应用（用户要求自带）
if ! dpkg -s gnome-terminal >/dev/null 2>&1; then
	echo "==> 安装 gnome-terminal"
	apt-get install -y --no-install-recommends gnome-terminal || \
		apt-get install -y gnome-terminal || echo "WARN: gnome-terminal 安装失败（继续）"
fi

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
