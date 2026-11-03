#!/usr/bin/env python3
"""边播边采：播放测试音的同时采样 CRU 门控/I2S 寄存器，看硬件真实动作。

用法: i2swatch.py [卡号] [次数] [间隔s]
"""
import mmap
import os
import struct
import subprocess
import sys
import time

CRU = 0xFDD20000
I2S = 0xFE410000
GRF = 0xFDC60000
PAGE = 4096
_maps = {}


def _m(base):
    if base not in _maps:
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        _maps[base] = mmap.mmap(fd, PAGE, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
    return _maps[base]


def rd(base, off):
    return struct.unpack("<I", _m(base)[off % PAGE:off % PAGE + 4])[0]


def wr(base, off, val):
    o = off % PAGE
    _m(base)[o:o + 4] = struct.pack("<I", val & 0xFFFFFFFF)
    _m(base).flush()


def bit_on(base, off, bit):
    v = rd(base, off)
    wr(base, off, (v | (1 << bit)) | ((1 << bit) << 16))


def bit_off(base, off, bit):
    v = rd(base, off)
    wr(base, off, (v & ~(1 << bit)) | ((1 << bit) << 16))


def snap(tag):
    g6 = rd(CRU, 0x318)
    s15 = rd(CRU, 0x13C)
    s16 = rd(CRU, 0x140)
    print("%-10s gate6=0x%05x[b11mclkout=%d b10mclk_tx=%d b8tx=%d b9frac=%d] "
          "sel15=0x%08x sel16=0x%08x | TXCR=0x%08x CKR=0x%08x FIFO=0x%02x XFER=0x%x"
          % (tag, g6, (g6 >> 11) & 1, (g6 >> 10) & 1, (g6 >> 8) & 1, (g6 >> 9) & 1,
             s15, s16, rd(I2S, 0x00), rd(I2S, 0x08),
             rd(I2S, 0x0C) & 0xFF, rd(I2S, 0x1C) & 0xF))


def main():
    card = sys.argv[1] if len(sys.argv) > 1 else "0"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    gap = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5

    snap("idle")
    p = subprocess.Popen(["aplay", "-D", "hw:%s,0" % card, "/tmp/spk_tone.wav"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for i in range(n):
        time.sleep(gap)
        snap("play+%.1fs" % ((i + 1) * gap))
    p.wait()
    time.sleep(0.3)
    snap("after")


if __name__ == "__main__":
    main()
