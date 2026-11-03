#!/usr/bin/env python3
"""RK3568 I2S1 MCLK 引脚输出使能开关（GRF 直写）

GRF 寄存器是 Rockchip 的 HIWORD_UPDATE 格式：
  低 16 位 = 数据值，高 16 位 = 写掩码。只有掩码为 1 的位才会被写入。

对应关系（sound/soc/rockchip/rockchip_i2s_tdm.h）：
  GRF+0x504 bit5  I2S1_MCLK_OUT_SRC_FROM_TX  1=TX 2=RX
  GRF+0x508 bit1  I2S1_MCLK_TX_OE            1=输出
  GRF+0x508 bit0  I2S1_MCLK_RX_OE            1=输出

驱动 common_soc_init() 只在 clk_trcm != TRCM_TXRX 时才写这两处，
所以主线默认（不写 trcm 属性）PA2 上的 MCLK 引脚永远没有输出。
"""
import os
import mmap
import struct
import sys

GRF = 0xFDC60000


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def wr(m, off, val):
    m[off:off + 4] = struct.pack('<I', val)


def hiword_update(value, hi, lo):
    """构造 HIWORD_UPDATE：同一位段内的低位掩码 + 高 16 位掩码"""
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return ((value << lo) & mask) | (mask << 16)


def dump(m, tag):
    for off in range(0x500, 0x510, 4):
        print('  [%s] GRF+0x%03x = 0x%08x' % (tag, off, rd(m, off)))


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'on'
    fd, m = openmem(GRF)
    dump(m, 'before')

    if action == 'on':
        # 0x504: MCLK 源选 TX (bit5)
        wr(m, 0x504, hiword_update(1, 5, 5))
        # 0x508: TX MCLK 输出使能 (bit1)，同时关闭 RX OE (bit0)
        wr(m, 0x508, hiword_update(1, 1, 1) | hiword_update(0, 0, 0))
        print('  -> 已写入 MCLK TX 输出使能')
    elif action == 'off':
        wr(m, 0x508, hiword_update(0, 1, 1))
        print('  -> 已关闭 MCLK TX 输出')
    else:
        print('用法: grfmclk.py [on|off|read]')

    dump(m, 'after')

    v504 = rd(m, 0x504)
    v508 = rd(m, 0x508)
    print('\n判定: MCLK_SRC=%s  TX_OE=%d  RX_OE=%d'
          % ('TX' if (v504 >> 5) & 1 else 'RX',
             (v508 >> 1) & 1,
             v508 & 1))
    os.close(fd)


if __name__ == '__main__':
    main()
