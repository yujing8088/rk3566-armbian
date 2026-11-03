#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 HI846 提供 xvclk：GPIO4_C0 复用为 cif_clkout + CLK_CIF_OUT 输出 24 MHz

依据：
  厂商 dtb  hi846.clocks = <&cru 214>，clock-names = "xvclk"
  主线      CLK_CIF_OUT = 214
  厂商 pinctrl 组 cif-clk: rockchip,pins = <4 0x10(pin16=C0) 1 ...>

寄存器：
  GRF  GPIO4C_IOMUX_L = 0x70    C0 的 mux 在 bit[3:0]，需 =1
       (GRF 基址 0xFDC60000；bank1 从 0x00 起，每 bank 0x20；
        A_L/A_H/B_L/B_H/C_L/C_H/D_L/D_H = +0x00/+0x04/+0x08/+0x0C/+0x10/+0x14/+0x18/+0x1C)
  CRU  CLKSEL_CON(35) = 0x18C   bit[15:14] mux 父时钟，bit[13:8] 分频
       父表 gpll_usb480m_xin24m_p = {gpll, usb480m, xin24m, xin24m}
       → mux=2 选 xin24m(24 MHz)，div=1 → 24 MHz
  CRU  CLKGATE_CON(19) = 0x34C  bit8  gate：0=开
"""
import os
import mmap
import struct
import sys

GRF = 0xFDC60000
CRU = 0xFDD20000

IOMUX_GPIO4C_L = 0x70
CLKSEL35 = 0x100 + 35 * 4      # 0x18C
CLKGATE19 = 0x300 + 19 * 4     # 0x34C


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def hiword(m, off, mask, value):
    """Rockchip HIWORD_UPDATE：低 16 位数据 + 高 16 位写掩码"""
    m[off:off + 4] = struct.pack('<I', ((value & 0xFFFF) | ((mask & 0xFFFF) << 16)))


def main():
    want = not (len(sys.argv) > 1 and sys.argv[1] == 'off')

    fdg, g = openmem(GRF)
    fdc, c = openmem(CRU)

    print('[before] GRF+0x70 IOMUX = 0x%08x  C0 mux=%d'
          % (rd(g, IOMUX_GPIO4C_L), rd(g, IOMUX_GPIO4C_L) & 0xF))
    print('[before] CLKSEL35 = 0x%08x  mux=%d div=%d | CLKGATE19 = 0x%08x gate=%d'
          % (rd(c, CLKSEL35), (rd(c, CLKSEL35) >> 14) & 3, (rd(c, CLKSEL35) >> 8) & 0x3F,
             rd(c, CLKGATE19), (rd(c, CLKGATE19) >> 8) & 1))

    if want:
        hiword(g, IOMUX_GPIO4C_L, 0xF, 1)              # C0 -> func1 (cif_clkout)
        hiword(c, CLKSEL35, 0xC000, 2 << 14)           # mux = xin24m
        hiword(c, CLKSEL35, 0x3F00, 1 << 8)            # div = 1
        hiword(c, CLKGATE19, 1 << 8, 0)                # gate 打开
        print('-> 已配 GPIO4_C0=cif_clkout, CLK_CIF_OUT=24MHz, gate=开')
    else:
        hiword(c, CLKGATE19, 1 << 8, 1 << 8)
        print('-> 已关闭 CLK_CIF_OUT')
        print('   (引脚复用保持不动，避免影响其他功能)')

    print('[after]  GRF+0x70 IOMUX = 0x%08x  C0 mux=%d'
          % (rd(g, IOMUX_GPIO4C_L), rd(g, IOMUX_GPIO4C_L) & 0xF))
    print('[after]  CLKSEL35 = 0x%08x  mux=%d div=%d | CLKGATE19 = 0x%08x gate=%d'
          % (rd(c, CLKSEL35), (rd(c, CLKSEL35) >> 14) & 3, (rd(c, CLKSEL35) >> 8) & 0x3F,
             rd(c, CLKGATE19), (rd(c, CLKGATE19) >> 8) & 1))

    g.close()
    c.close()
    os.close(fdg)
    os.close(fdc)


if __name__ == '__main__':
    main()
