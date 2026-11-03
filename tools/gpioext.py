#!/usr/bin/env python3
"""只读方式采样 RK3568 GPIO 引脚的真实电平（不改任何 pinctrl 配置）

读的是 EXT_PORT 寄存器 —— 它反映引脚上的物理电平，
与 IOMUX 选择的功能无关，因此可以在 I2S 正在工作时安全观测。

GPIO1_A 相关位：
  bit2 = PA2 = I2S1_MCLK
  bit3 = PA3 = I2S1_SCLK
  bit5 = PA5 = I2S1_LRCK
  bit7 = PA7 = I2S1_SDO0
"""
import os
import sys
import time
import mmap
import struct
import subprocess

GPIO1 = 0xFE740000
EXT_PORT_L = 0x0070
DDR_L = 0x0008

PINS = [('MCLK', 2), ('SCLK', 3), ('LRCK', 5), ('SDO0', 7)]


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def main():
    fd, m = openmem(GPIO1)
    print('GPIO1 DDR_L = 0x%08x (bit=1 表示输出)' % rd(m, DDR_L))

    do_play = len(sys.argv) > 1 and sys.argv[1] == 'play'
    p = None
    if do_play:
        print('启动播放…')
        p = subprocess.Popen(['aplay', '-D', 'hw:0,0', '/tmp/long.wav'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)
    else:
        print('空闲状态采样（未播放）')

    N = 400
    samples = {name: [] for name, _ in PINS}
    for _ in range(N):
        v = rd(m, EXT_PORT_L)
        for name, bit in PINS:
            samples[name].append((v >> bit) & 1)
        # 不加延时，靠寄存器读速度尽量提高采样率

    print('\n采样 %d 次：' % N)
    for name, bit in PINS:
        s = samples[name]
        ones = sum(s)
        print('  PA%-2d %-5s 高=%3d/%d (%.0f%%)  %s'
              % (bit, name, ones, N, 100.0 * ones / N,
                 '有跳变 ✔' if 0 < ones < N else '恒定'))

    if p:
        p.terminate()
        p.wait()
    os.close(fd)


if __name__ == '__main__':
    main()
