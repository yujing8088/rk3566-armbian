#!/usr/bin/env python3
"""Print USB controller DT properties from /proc/device-tree."""
import os

NODES = ["usb@fd000000", "usb@fcc00000", "usb@fd800000", "usb@fd880000"]
PROPS = ["phy-names", "dr_mode", "maximum-speed", "phy_type", "status",
         "snps,dis_u2_susphy_quirk"]

for node in NODES:
    base = os.path.join("/proc/device-tree", node)
    print("=====", node, "(exists)" if os.path.isdir(base) else "(MISSING)")
    if not os.path.isdir(base):
        continue
    for prop in PROPS:
        path = os.path.join(base, prop)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                raw = fh.read()
            if prop == "status" or prop == "dr_mode" or prop == "phy_type":
                print("  %-26s = %s" % (prop, raw.rstrip(b"\0").decode("utf-8", "replace")))
            else:
                print("  %-26s = %r" % (prop, raw))
        else:
            print("  %-26s = <none>" % prop)
    ppath = os.path.join(base, "phys")
    if os.path.exists(ppath):
        with open(ppath, "rb") as fh:
            raw = fh.read()
        cells = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw), 4)]
        print("  %-26s = %s" % ("phys cells(phandle,arg)", cells))
