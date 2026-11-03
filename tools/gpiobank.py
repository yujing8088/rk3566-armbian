#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 RK3568 GPIO 驱动/观测（任意 bank，直接写 SWPORT 寄存器，绕过 gpio-hog）

用法:
  python3 gpiobank.py <bank> <pin> <level>   # 设为输出并给电平
  python3 gpiobank.py <bank> <pin>           # 只读查看

pin: 0-31（A0-A7=0-7, B0-B7=8-15, C0-C7=16-23, D0-D7=24-31）

寄存器（Rockchip HIWORD_UPDATE 格式：低 16 位数据 + 高 16 位写掩码）:
  0x0000 SWPORT_DR_L   0x0004 SWPORT_DR_H
  0x0008 SWPORT_DDR_L  0x000C SWPORT_DDR_H   (1=输出)
"""
import os
import mmap
import struct
import sys

BASES = {
    0: 0xFDD60000,
    1: 0xFE740000,
    2: 0xFE750000,
    3: 0xFE760000,
    4: 0xFE770000,
}

DR_L, DR_H, DDR_L, DDR_H = 0x0000, 0x0004, 0x0008, 0x000C


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def hiword_write(m, off, bit, value):
    m[off:off + 4] = struct.pack('<I', ((value & 1) << bit) | (1 << (bit + 16)))


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    bank = int(sys.argv[1])
    pin = int(sys.argv[2])
    level = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if bank not in BASES:
        raise SystemExit('bank 只能是 0-4')
    base = BASES[bank]

    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED,
                  mmap.PROT_READ | mmap.PROT_WRITE, offset=base)

    name = 'GPIO%d_%s%d' % (bank, 'ABCD'[pin // 8], pin % 8)
    ddr = rd(m, DDR_L if pin < 16 else DDR_H)
    dr = rd(m, DR_L if pin < 16 else DR_H)
    b = pin % 16
    print('%s (base=0x%08x)  方向=%s  电平=%d'
          % (name, base, '输出' if (ddr >> b) & 1 else '输入', (dr >> b) & 1))

    if level is not None:
        reg_dr = DR_L if pin < 16 else DR_H
        reg_ddr = DDR_L if pin < 16 else DDR_H
        hiword_write(m, reg_ddr, b, 1)      # 设为输出
        hiword_write(m, reg_dr, b, level)   # 给电平
        ddr = rd(m, DDR_L if pin < 16 else DDR_H)
        dr = rd(m, DR_L if pin < 16 else DR_H)
        print('  -> 已设为输出 %d；回读：方向=%s 电平=%d'
              % (level, '输出' if (ddr >> b) & 1 else '输入', (dr >> b) & 1))

    m.close()
    os.close(fd)


if __name__ == '__main__':
    main()
