#!/bin/sh
# RK960 BT bringup: retry loop of B7(GPIO2_B7=79) reset pulse + hciattach @1.5M
# BT firmware download needs a fw-less die, so WiFi driver loads only after BT is up.
if [ ! -d /sys/class/gpio/gpio79 ]; then echo 79 > /sys/class/gpio/export; fi
echo out > /sys/class/gpio/gpio79/direction

ok=0
for i in 1 2 3 4 5 6; do
    echo 0 > /sys/class/gpio/gpio79/value
    sleep 0.5
    /usr/local/bin/rk_hciattach -n -s 1500000 /dev/ttyS1 rockchip 3000000 flow nosleep 11:22:33:44:55:66 >/tmp/rk960-bt.log 2>&1 &
    HPID=$!
    sleep 1.2
    echo 1 > /sys/class/gpio/gpio79/value
    # wait up to 12s for hci0
    n=0
    while [ $n -lt 12 ]; do
        if [ -d /sys/class/bluetooth/hci0 ]; then ok=1; break; fi
        sleep 1
        n=$((n+1))
    done
    if [ $ok -eq 1 ]; then
        echo "rk960-bt: hci0 up on attempt $i"
        break
    fi
    kill $HPID 2>/dev/null
    sleep 1
done

if [ $ok -eq 0 ]; then
    echo "rk960-bt: hciattach failed after retries"
fi

# WiFi driver last (works fine once BT fw is running)
modprobe rk960 2>/dev/null
exit 0
