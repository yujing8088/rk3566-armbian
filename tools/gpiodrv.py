#!/usr/bin/env python3
"""直接操作 RK3568 GPIO 的 SWPORT 寄存器（绕过 gpio-hog 占用）

RK3568 GPIO 控制器寄存器：
  0x0000 SWPORT_DR_L   数据寄存器（低 16 位数据 + 高 16 位写掩码）
  0x0004 SWPORT_DR_H
  0x0008 SWPORT_DDR_L  方向寄存器
  0x000C SWPORT_DDR_H

Rockchip 的写掩码规则：只有高 16 位对应位为 1 的比特才会真正写入。
要拉低 bit N：写 (1 << (N + 16))，低 16 位该位为 0。
"""
import os
import mmap
import struct
import sys

GPIO1 = 0xFE740000   # /pinctrl/gpio@fe740000

DR_L = 0x0000
DR_H = 0x0004
DDR_L = 0x0008
DDR_H = 0x000C


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def set_pin(m, pin, level):
    """pin: 0-31（A0-A7=0-7, B0-B7=8-15, C0-C7=16-23, D0-D7=24-31）"""
    if pin < 16:
        reg, bit = DR_L, pin
    else:
        reg, bit = DR_H, pin - 16
    val = ((1 if level else 0) << bit) | (1 << (bit + 16))
    m[reg:reg + 4] = struct.pack('<I', val)


def main():
    pin = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    level = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    fd, m = openmem(GPIO1)

    print('GPIO1 寄存器 (pin=%d):' % pin)
    for name, off in (('DR_L', DR_L), ('DR_H', DR_H),
                      ('DDR_L', DDR_L), ('DDR_H', DDR_H)):
        print('  %-6s = 0x%08x' % (name, rd(m, off)))
    print('  当前 A%d 电平 = %d' % (pin, (rd(m, DR_L) >> pin) & 1))

    set_pin(m, pin, level)
    print('  -> 已写入 A%d = %d' % (pin, level))
    print('  写入后 DR_L = 0x%08x  A%d = %d'
          % (rd(m, DR_L), pin, (rd(m, DR_L) >> pin) & 1))
    os.close(fd)


if __name__ == '__main__':
    main()
