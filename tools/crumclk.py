#!/usr/bin/env python3
"""打开 RK3568 I2S1 MCLK 引脚输出的时钟：选对父时钟 + 打开门控

问题：i2s1_mclkout_tx 是一个 "deviceless gate"（clk-rk3568.c 里的
COMPOSITE_NODIV），没有任何设备通过 clocks 属性引用它，所以 clk 框架
永远不会去 enable 它。结果：
  - MCLK 引脚（PA2）上没有时钟输出
  - 它的父时钟选择停在 xin_osc0_half(12MHz) 这个默认值上
需要 MCLK 做内部过采样的外置 DAC（CS4333 这类）因此完全不出声。

寄存器（CRU = 0xFDD20000）：
  CLKSEL_CON(15) = 0x13C  bit15  mux: 0=clk_i2s1_8ch_tx  1=xin_osc0_half
  CLKGATE_CON(6) = 0x318  bit11  gate: 0=开  1=关

两者都是 Rockchip 的 HIWORD_UPDATE 格式：低 16 位数据 + 高 16 位写掩码。
"""
import os
import sys
import mmap
import struct

CRU = 0xFDD20000
CLKSEL15 = 0x13C
CLKGATE6 = 0x318


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def hiword_write(m, off, bit, value):
    """bit 位置 1 位写入（HIWORD_UPDATE）"""
    v = ((value & 1) << bit) | (1 << (bit + 16))
    m[off:off + 4] = struct.pack('<I', v)


def report(m, tag):
    s = rd(m, CLKSEL15)
    g = rd(m, CLKGATE6)
    print('[%s] CLKSEL_CON(15)=0x%08x  mux(bit15)=%d (%s)'
          % (tag, s, (s >> 15) & 1,
             'xin_osc0_half 12M' if (s >> 15) & 1 else 'clk_i2s1_8ch_tx 12.288M'))
    print('[%s] CLKGATE_CON(6)=0x%08x  gate(bit11)=%d (%s)'
          % (tag, g, (g >> 11) & 1, '关' if (g >> 11) & 1 else '开'))


def main():
    on = not (len(sys.argv) > 1 and sys.argv[1] == 'off')
    fd, m = openmem(CRU)
    report(m, 'before')

    if on:
        hiword_write(m, CLKSEL15, 15, 0)   # 父时钟 = clk_i2s1_8ch_tx
        hiword_write(m, CLKGATE6, 11, 0)   # gate 打开
        print('-> 已设 mux=clk_i2s1_8ch_tx, gate=开')
    else:
        hiword_write(m, CLKGATE6, 11, 1)
        print('-> 已关闭 gate')

    report(m, 'after')

    s, g = rd(m, CLKSEL15), rd(m, CLKGATE6)
    ok = ((s >> 15) & 1) == 0 and ((g >> 11) & 1) == 0
    print('\n结果: %s' % ('成功，MCLK 引脚应有 12.288MHz 输出' if ok else '失败'))
    os.close(fd)


if __name__ == '__main__':
    main()
