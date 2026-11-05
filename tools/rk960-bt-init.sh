#!/bin/sh
# RK960 (AIC8800) 蓝牙上电初始化
#
# 关键事实（板上实测 2026-11-05）：
#   1. BT 复位脚 = GPIO2_B7 = gpio79（低有效复位）。芯片未跑 WiFi 固件时，
#      复位 0->1 会让 ROM 起来，并以 **115200** 波特率不停播报 "RKUART"。
#      —— 不是 1500000：1.5M 下读回来只有 0x00/0xf0，协议必然失败。
#   2. ROM 的下载协议在 115200 起跑（固件约 500KB，耗时约 45s），下载完成后
#      hciattach 用 cmd fc84 把链路切到 3000000，再发 HCI Reset，此后
#      hciconfig 才显示 UP RUNNING。
#   3. hciattach 开串口前先把 in-flight 播报流排空一段，否则 ACK 会被埋在
#      几 KB 的 "RKUART" 里。
#   4. BT 固件下载必须早于 WiFi 驱动（rk960.ko）加载：芯片一旦跑起 WiFi
#      固件，BT 核不再进 ROM，脉冲只会把它打进 break 态，只能整板断电恢复。
set -u

RST=79
TTY=/dev/ttyS1
HCIATTACH=/usr/local/bin/rk_hciattach
LOG=/run/rk960-bt.log

log() { echo "[bt-init] $*"; }

# gpio79 导出 + 默认拉低（把 BT 核按在复位里）
if [ ! -d /sys/class/gpio/gpio$RST ]; then
	echo $RST > /sys/class/gpio/export 2>/dev/null
fi
echo out > /sys/class/gpio/gpio$RST/direction
echo 0 > /sys/class/gpio/gpio$RST/value

pkill -9 rk_hciattach 2>/dev/null
sleep 0.3

# 串口先配到 ROM 的 115200，排空 in-flight 播报
stty -F $TTY 115200 raw -echo -crtscts 2>/dev/null
timeout 1 dd if=$TTY of=/dev/null bs=4096 count=8 2>/dev/null

attempt=1
while [ $attempt -le 3 ]; do
	log "attempt $attempt"

	# 复位脉冲：拉低 400ms 再放开 -> ROM 播报 "RKUART"
	echo 0 > /sys/class/gpio/gpio$RST/value
	sleep 0.4
	echo 1 > /sys/class/gpio/gpio$RST/value
	sleep 0.3

	$HCIATTACH -n -s 115200 $TTY rockchip 3000000 flow nosleep 11:22:33:44:55:66 \
		>>$LOG 2>&1 &
	HPID=$!

	# 下载 + 切速约 50s，最多等 90s
	i=0
	ok=0
	while [ $i -lt 90 ]; do
		sleep 1
		if hciconfig hci0 2>/dev/null | grep -q "UP RUNNING"; then
			ok=1
			break
		fi
		if ! kill -0 $HPID 2>/dev/null; then
			log "hciattach exited early"
			break
		fi
		i=$((i + 1))
	done

	if [ $ok -eq 1 ]; then
		log "hci0 UP RUNNING (attempt $attempt)"
		# BT 已就绪，最后再拉 WiFi 驱动，保证 WiFi+BT 共存
		modprobe rk960 2>/dev/null
		log "rk960 WiFi driver loaded; serving"
		wait $HPID
		exit 0
	fi

	log "attempt $attempt failed, retry"
	kill -9 $HPID 2>/dev/null
	wait $HPID 2>/dev/null
	echo 0 > /sys/class/gpio/gpio$RST/value
	attempt=$((attempt + 1))
done

log "BT bringup failed after 3 attempts"
# 兜底：BT 失败也要把 WiFi 拉起来，否则整板失联（BT 需要断电重来，
# 复位脉冲救不回已经进了 break 态的芯片，所以这里不重试，直接退出 0）
modprobe rk960 2>/dev/null
exit 0
