#!/usr/bin/env python3
"""FDT 解析/反编译 (纯 python，无需 dtc)"""
import struct, sys, os

def be32(b, o): return struct.unpack_from(">I", b, o)[0]

class Fdt:
    def __init__(self, blob):
        self.b = blob
        self.magic = be32(blob, 0)
        self.totalsize = be32(blob, 4)
        self.off_struct = be32(blob, 8)
        self.off_strings = be32(blob, 12)
        self.size_strings = be32(blob, 32)
        self.version = be32(blob, 20)
        self.root = self._parse()

    def _str(self, off):
        s = self.off_strings + off
        e = self.b.index(b"\0", s)
        return self.b[s:e].decode(errors="replace")

    def _parse(self):
        b = self.b; p = self.off_struct
        root = {"name": "/", "props": [], "children": [], "_wrapper": True}
        stack = [root]
        while p < len(b) - 4:
            tag = be32(b, p)
            if tag == 1:
                p += 4; e = b.index(b"\0", p)
                nm = b[p:e].decode(errors="replace"); p = (e + 4) & ~3
                node = {"name": nm, "props": [], "children": []}
                stack[-1]["children"].append(node); stack.append(node)
            elif tag == 2:
                p = (p + 4 + 3) & ~3; stack.pop()
            elif tag == 3:
                ln = be32(b, p + 4); no = be32(b, p + 8)
                nm = self._str(no)
                val = b[p + 12:p + 12 + ln]
                stack[-1]["props"].append((nm, val))
                p = (p + 12 + ln + 3) & ~3
            elif tag == 4:
                p += 4
            elif tag == 9:
                break
            else:
                break
        return root

def fmt_val(v):
    if len(v) == 0: return ""
    if len(v) % 4 == 0 and len(v) <= 16:
        nums = struct.unpack(">%dI" % (len(v)//4), v)
        if all(n < 0x10000 for n in nums) and not all(32 <= c < 127 for c in v):
            return "<" + " ".join("0x%x" % n for n in nums) + ">"
    if all(32 <= c < 127 or c == 0 for c in v) and v[-1:] == b"\0":
        parts = v.rstrip(b"\0").split(b"\0")
        if len(parts) == 1:
            return '"%s"' % parts[0].decode(errors="replace")
        return ", ".join('"%s"' % x.decode(errors="replace") for x in parts)
    if len(v) % 4 == 0:
        return "<" + " ".join("0x%02x" % c for c in v) + ">"
    return "<" + " ".join("0x%02x" % c for c in v) + ">"

def dump(node, depth=0, out=None):
    ind = "\t" * depth
    out.append("%s%s {" % (ind, "" if node is root_name(node) else node["name"] + " "))
    for nm, v in node["props"]:
        out.append("%s\t%s = %s;" % (ind, nm, fmt_val(v)))
    for c in node["children"]:
        dump(c, depth + 1, out)
    out.append("%s};" % ind)

def root_name(n): return n

def walk(node, path=""):
    yield path or "/", node
    for c in node["children"]:
        yield from walk(c, path + "/" + c["name"])

def get(node, name):
    for nm, v in node["props"]:
        if nm == name: return v
    return None

if __name__ == "__main__":
    path = sys.argv[1]
    blob = open(path, "rb").read()
    f = Fdt(blob)
    mode = sys.argv[2] if len(sys.argv) > 2 else "info"
    if mode == "dts":
        out = ["/dts-v1/;", ""]
        def d2(n, depth=0):
            ind = "\t" * depth
            out.append("%s%s{" % (ind, "" if n is f.root else n["name"] + " "))
            for nm, v in n["props"]:
                out.append("%s\t%s = %s;" % (ind, nm, fmt_val(v)))
            for c in n["children"]:
                d2(c, depth + 1)
            out.append("%s};" % ind)
        d2(f.root)
        print("\n".join(out))
    else:
        model = get(f.root, "model"); comp = get(f.root, "compatible")
        print("model     :", model.decode(errors="replace").rstrip("\0") if model else None)
        print("compatible:", fmt_val(comp) if comp else None)
        print("version   :", f.version, " totalsize:", f.totalsize)
        print("--- nodes:", sum(1 for _ in walk(f.root)))
        for p, n in walk(f.root):
            if p.startswith(("/chosen", "/memory", "/reserved", "/external", "/vcc", "/sdhci", "/ethernet", "/phy", "/usb", "/i2c", "/spi", "/gpio", "/leds", "/backlight", "/panel", "/hdmi", "/dsi", "/vop", "/wifi", "/wireless", "/bluetooth", "/mmc", "/pinctrl")):
                st = get(n, "status"); cp = get(n, "compatible")
                print("%-46s %-24s %s" % (p, (cp.decode(errors='replace').rstrip('\0')[:46] if cp else ""), (st.decode(errors='replace').rstrip('\0') if st else "")))
