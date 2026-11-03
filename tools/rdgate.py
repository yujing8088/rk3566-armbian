#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读查看 i2s1_mclkout_tx 的门控/父时钟状态（不改任何寄存器）"""
import os
import mmap
import struct

CRU = 0xFDD20000
CLKSEL15 = 0x13C
CLKGATE6 = 0x318


def main():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=CRU)
    s = struct.unpack('<I', m[0x13C:0x140])[0]
    g = struct.unpack('<I', m[0x318:0x31C])[0]
    print('mux(bit15)=%d %s | gate(bit11)=%d %s'
          % ((s >> 15) & 1,
             'xin_osc0_half 12M' if (s >> 15) & 1 else 'clk_i2s1_8ch_tx 12.288M',
             (g >> 11) & 1,
             '关' if (g >> 11) & 1 else '开'))
    m.close()
    os.close(fd)


if __name__ == '__main__':
    main()
