#!/usr/bin/env python3
"""Dump USB host controller port status registers straight from /dev/mem.

Used to tell "device not plugged" apart from "controller port never sees
connect" on RK356x boards where lsusb only shows empty root hubs.
"""
import mmap
import os
import struct
import sys

PAGE = 4096

CTRLS = [
    ("xhci@fd000000 (USB3 host)", 0xFD000000, "xhci"),
    ("ehci@fd800000 (USB2 host0)", 0xFD800000, "ehci"),
    ("ehci@fd880000 (USB2 host1)", 0xFD880000, "ehci"),
    ("dwc3@fcc00000 (OTG)", 0xFCC00000, "dwc3"),
]


def rd(addr, n=8):
    # arm64 /dev/mem 只允许整页映射（<= PAGE_SIZE），映射两页会 SIGBUS
    base = addr & ~(PAGE - 1)
    off = addr - base
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        m = mmap.mmap(fd, PAGE, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    finally:
        os.close(fd)
    try:
        return bytes(m[off:off + n])
    finally:
        m.close()


def dump_xhci(base):
    cap = rd(base, 0x50)
    caplen = cap[0]
    hcsparams = struct.unpack("<I", cap[4:8])[0]
    nports = hcsparams & 0xF
    print("  CAPLENGTH=0x%x  N_ports=%d" % (caplen, nports))
    for p in range(nports):
        v = struct.unpack("<I", rd(base + caplen + 0x400 + p * 0x10, 4))[0]
        print("  PORTSC%d=0x%08x CCS=%d PED=%d PR=%d PP=%d PLS=%d"
              % (p + 1, v, v & 1, (v >> 1) & 1, (v >> 4) & 1,
                 (v >> 9) & 1, (v >> 5) & 0xF))


def dump_ehci(base):
    cap = rd(base, 0x50)
    caplen = cap[0]
    hcsparams = struct.unpack("<I", cap[4:8])[0]
    nports = hcsparams & 0xF
    print("  CAPLENGTH=0x%x  N_ports=%d" % (caplen, nports))
    for p in range(nports):
        v = struct.unpack("<I", rd(base + caplen + 0x44 + p * 4, 4))[0]
        print("  PORTSC%d=0x%08x CCS=%d PE=%d PR=%d PP=%d LS=%d"
              % (p + 1, v, v & 1, (v >> 2) & 1, (v >> 8) & 1,
                 (v >> 12) & 1, (v >> 10) & 3))


def dump_dwc3(base):
    # GCTL@0xc110, GUSB2PHYCFG0@0xc200, DCTL@0xc704, DSTS@0xc70c
    gctl = struct.unpack("<I", rd(base + 0xC110, 4))[0]
    dctl = struct.unpack("<I", rd(base + 0xC704, 4))[0]
    dsts = struct.unpack("<I", rd(base + 0xC70C, 4))[0]
    print("  GCTL=0x%08x PrtCapDir=%d  DCTL=0x%08x RunStop=%d DevEn=%d"
          % (gctl, (gctl >> 12) & 3, dctl, dctl & 1, (dctl >> 31) & 1))
    print("  DSTS=0x%08x  Connected=%d Speed=%d"
          % (dsts, (dsts >> 0) & 1, (dsts >> 1) & 7))


def main():
    for name, base, kind in CTRLS:
        try:
            print(name)
            if kind == "xhci":
                dump_xhci(base)
            elif kind == "ehci":
                dump_ehci(base)
            else:
                dump_dwc3(base)
        except Exception as exc:  # noqa: BLE001
            print("  ERROR: %s" % exc)
        print()


if __name__ == "__main__":
    sys.exit(main())
