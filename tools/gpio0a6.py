#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在线改写 GPIO0_A6(GPIO0 pin6, vcc5v0_host 使能脚) 输出电平，用于判断开关极性。
用法: gpio0a6.py read | low | high
RK3566 GPIO0 base = 0xFDD60000
  SWPORT_DR_L  0x0000 (pin0..15)
  SWPORT_DDR_L 0x0008
  EXT_PORT     0x0070 (只读实际电平)
"""
import mmap, os, struct, sys

PAGE = 4096
GPIO0 = 0xFDD60000
BIT = 6

def map_page():
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, PAGE, mmap.MAP_SHARED,
                  mmap.PROT_READ | mmap.PROT_WRITE, offset=GPIO0)
    return fd, m

def rd32(m, off):
    return struct.unpack("<I", m[off:off + 4])[0]

def wr32(m, off, v):
    m[off:off + 4] = struct.pack("<I", v)

def wrmask(m, off, val, mask):
    """Rockchip GPIO: 高 16 位为写掩码，低 16 位为数据。"""
    wr32(m, off, ((val & 0xffff) | ((mask & 0xffff) << 16)))

def main():
    act = sys.argv[1] if len(sys.argv) > 1 else "read"
    fd, m = map_page()
    try:
        dr = rd32(m, 0x0000)
        ddr = rd32(m, 0x0008)
        ext = rd32(m, 0x0070)
        print("DR_L  = 0x%08x  (A6 out=%d)" % (dr, (dr >> BIT) & 1))
        print("DDR_L = 0x%08x  (A6 dir=%s)" % (ddr, "out" if (ddr >> BIT) & 1 else "in"))
        print("EXT_L = 0x%08x  (A6 pad=%d)" % (ext, (ext >> BIT) & 1))
        if act == "low":
            wrmask(m, 0x0008, ddr | (1 << BIT), 1 << BIT)   # 确保输出
            wrmask(m, 0x0000, dr & ~(1 << BIT), 1 << BIT)   # 输出 0
            print("--> 已把 GPIO0_A6 拉低")
        elif act == "high":
            wrmask(m, 0x0008, ddr | (1 << BIT), 1 << BIT)
            wrmask(m, 0x0000, dr | (1 << BIT), 1 << BIT)
            print("--> 已把 GPIO0_A6 拉高")
        if act in ("low", "high"):
            dr2 = rd32(m, 0x0000)
            ext2 = rd32(m, 0x0070)
            print("after: DR_L=0x%08x out=%d  EXT pad=%d"
                  % (dr2, (dr2 >> BIT) & 1, (ext2 >> BIT) & 1))
    finally:
        m.close()
        os.close(fd)

main()
