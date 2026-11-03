#!/usr/bin/env python3
"""Resolve phandles in the live device tree to node paths.

Prints where each USB controller's phys point, so mainline defaults can be
compared against the vendor board wiring.
"""
import os
import struct

ROOT = "/proc/device-tree"
WANT = ["usb@fd000000", "usb@fcc00000", "usb@fd800000", "usb@fd840000",
        "usb@fd880000", "usb@fd8c0000"]

phandles = {}


def walk(path):
    try:
        entries = os.listdir(path)
    except OSError:
        return
    hp = os.path.join(path, "phandle")
    lp = os.path.join(path, "linux,phandle")
    for cand in (hp, lp):
        if os.path.exists(cand):
            with open(cand, "rb") as fh:
                val = struct.unpack(">I", fh.read(4))[0]
            phandles[val] = path[len(ROOT):] or "/"
            break
    for entry in entries:
        full = os.path.join(path, entry)
        if os.path.isdir(full):
            walk(full)


walk(ROOT)

print("--- usb controller phys ---")
for node in WANT:
    base = os.path.join(ROOT, node)
    if not os.path.isdir(base):
        print("%-14s MISSING" % node)
        continue
    names_path = os.path.join(base, "phy-names")
    names = []
    if os.path.exists(names_path):
        with open(names_path, "rb") as fh:
            names = fh.read().decode().split("\0")[:-1]
    cells = []
    phys_path = os.path.join(base, "phys")
    if os.path.exists(phys_path):
        with open(phys_path, "rb") as fh:
            raw = fh.read()
        cells = [struct.unpack(">I", raw[i:i + 4])[0] for i in range(0, len(raw), 4)]
    out = []
    # phy specifier = 1 phandle cell (+ optional arg for combphy, 1 cell)
    i = 0
    idx = 0
    while i < len(cells):
        ph = cells[i]
        target = phandles.get(ph, "?")
        arg = ""
        if "combphy" in target or "naneng" in target:
            arg = " arg=%d" % cells[i + 1] if i + 1 < len(cells) else ""
            i += 2
        else:
            i += 1
        label = names[idx] if idx < len(names) else "?"
        out.append("%s -> %s%s" % (label, target, arg))
        idx += 1
    print("%-14s %s" % (node, "; ".join(out) if out else "no phys"))
