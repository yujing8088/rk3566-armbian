import mmap, os, struct, sys

CRU = 0xFDD20000
GRF = 0xFDC60000
PAGE = 4096
_cache = {}


def _map(base):
    if base not in _cache:
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        _cache[base] = (fd, mmap.mmap(fd, PAGE, mmap.MAP_SHARED,
                                      mmap.PROT_READ | mmap.PROT_WRITE, offset=base))
    return _cache[base][1]


def rd(base, off):
    m = _map(base)
    o = off % PAGE
    return struct.unpack("<I", m[o:o + 4])[0]


def wr(base, off, val):
    m = _map(base)
    o = off % PAGE
    m[o:o + 4] = struct.pack("<I", val & 0xFFFFFFFF)
    m.flush()


def wmasked(base, off, bit, on):
    v = rd(base, off)
    mask = 1 << bit
    cur = (v & mask) != 0
    nv = (v | mask) if on else (v & ~mask)
    # 高 16 位写使能
    wr(base, off, (nv & 0xFFFF) | ((mask & 0xFFFF) << 16))
    print("  [%s+0x%03x] bit%d: %d -> %d  (0x%08x -> 0x%08x)"
          % ("CRU" if base == CRU else "GRF", off, bit, cur, on, v, rd(base, off)))


def scan(name, base, off):
    print("%s+0x%03x = 0x%08x" % (name, off, rd(base, off)))


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        if a.startswith("rd"):
            base, off = a[2:].split("@")
            b = CRU if base.upper() == "CRU" else GRF
            scan(base.upper(), b, int(off, 16))
