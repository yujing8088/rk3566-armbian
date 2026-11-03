#!/usr/bin/env python3
"""差分扫描 CRU：对比"空闲"与"播放中"两组读值，找出真正在动的寄存器。

用法: crudiff.py [卡号]
"""
import mmap
import os
import struct
import subprocess
import sys
import time

CRU = 0xFDD20000
PAGE = 4096
_fd = None


def _m(base, size=PAGE):
    global _fd
    if _fd is None:
        _fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    return mmap.mmap(_fd, size, mmap.MAP_SHARED,
                     mmap.PROT_READ | mmap.PROT_WRITE, offset=base)


M = _m(CRU, 0x1000)


def rd(off):
    return struct.unpack("<I", M[off:off + 4])[0]


def scan():
    d = {}
    for off in range(0x000, 0x1000, 4):
        d[off] = rd(off)
    return d


def main():
    card = sys.argv[1] if len(sys.argv) > 1 else "0"
    a = scan()
    p = subprocess.Popen(["aplay", "-D", "hw:%s,0" % card, "/tmp/t2.wav"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    b = scan()
    p.kill()
    p.wait()
    time.sleep(0.3)
    c = scan()

    print("== 播放中相对空闲发生变化的 CRU 寄存器 ==")
    for off in sorted(a):
        if a[off] != b[off]:
            print("  0x%03x: idle=0x%08x  play=0x%08x" % (off, a[off], b[off]))
    print("== 播放结束后仍未恢复的 ==")
    for off in sorted(a):
        if a[off] != c[off] and b[off] == c[off]:
            print("  0x%03x: idle=0x%08x  after=0x%08x" % (off, a[off], c[off]))


if __name__ == "__main__":
    main()
