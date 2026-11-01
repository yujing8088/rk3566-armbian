#!/usr/bin/env python3
"""RK3566 Android 固件硬件指纹提取"""
import struct, sys, os, re, json

D = r"C:/Users/Admin/Desktop/liunx/android"
OUT = r"C:/Users/Admin/Desktop/liunx/armbian/analysis"
os.makedirs(OUT, exist_ok=True)

def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def u64(b, o): return struct.unpack_from("<Q", b, o)[0]

# ---------- 1. Android boot image ----------
def parse_boot(path):
    with open(path, "rb") as f:
        h = f.read(0x700)
    assert h[:8] == b"ANDROID!"
    d = {}
    d["kernel_size"]  = u32(h, 0x08); d["kernel_addr"] = hex(u32(h, 0x0c))
    d["ramdisk_size"] = u32(h, 0x10); d["ramdisk_addr"] = hex(u32(h, 0x14))
    d["second_size"]  = u32(h, 0x18); d["second_addr"] = hex(u32(h, 0x1c))
    d["tags_addr"]    = hex(u32(h, 0x20)); d["page_size"] = u32(h, 0x24)
    d["header_version"] = u32(h, 0x28)
    d["os_version"]   = hex(u32(h, 0x2c))
    d["name"] = h[0x30:0x40].split(b"\0")[0].decode(errors="replace")
    d["cmdline"] = h[0x40:0x240].split(b"\0")[0].decode(errors="replace")
    d["extra_cmdline"] = h[0x260:0x660].split(b"\0")[0].decode(errors="replace")
    if d["header_version"] >= 2:
        d["recovery_dtbo_size"] = u32(h, 0x660)
        d["header_size"] = u32(h, 0x66c)
        d["dtb_size"] = u32(h, 0x670)
        d["dtb_addr"] = hex(u64(h, 0x674))
    d["file"] = os.path.basename(path)
    return d

# ---------- 2. 扫描 FDT (0xd00dfeed) ----------
FDT = b"\xd0\x0d\xfe\xed"
def find_fdt(path, limit_size=None):
    res = []
    size = os.path.getsize(path)
    if limit_size: size = min(size, limit_size)
    with open(path, "rb") as f:
        prev = -8
        chunk = 1 << 22
        base = 0
        while base < size:
            f.seek(base); buf = f.read(chunk)
            if not buf: break
            idx = 0
            while True:
                i = buf.find(FDT, idx)
                if i < 0: break
                off = base + i
                if off - res[-1]["off"] if res else 8: pass
                tot = u32(buf, i + 4) if i + 8 <= len(buf) else 0
                res.append({"off": off, "totalsize": tot})
                idx = i + 4
            base += chunk - 8
    # 过滤合理大小
    res = [r for r in res if 512 <= r["totalsize"] <= 4 << 20 and r["off"] + r["totalsize"] <= size]
    # 去重（同一 blob 内嵌）
    out = []
    for r in res:
        if out and r["off"] < out[-1]["off"] + out[-1]["totalsize"]:
            continue
        out.append(r)
    return out

def dump_fdt(path, off, total, outpath):
    with open(path, "rb") as f:
        f.seek(off); b = f.read(total)
    with open(outpath, "wb") as g: g.write(b)
    return b

def fdt_model(b):
    """从 FDT structure block 直接读 model / compatible 字符串"""
    try:
        off_struct = u32(b, 8); off_strings = u32(b, 12)
        p = off_struct; cur = None; info = {}
        while p < len(b) - 4:
            tag = struct.unpack_from(">I", b, p)[0]
            if tag == 1:  # BEGIN_NODE
                p += 4; e = b.index(b"\0", p); cur = b[p:e].decode(errors="replace"); p = (e + 4) & ~3
            elif tag == 2:
                p = (p + 4 + 3) & ~3
            elif tag == 3:  # PROP
                ln = struct.unpack_from(">I", b, p + 4)[0]
                no = struct.unpack_from(">I", b, p + 8)[0]
                e = b.index(b"\0", off_strings + no)
                nm = b[off_strings + no:e].decode(errors="replace")
                val = b[p + 12:p + 12 + ln]
                if nm in ("model", "compatible"):
                    info.setdefault(nm, []).append(val.replace(b"\0", b" ").decode(errors="replace").strip())
                p = (p + 12 + ln + 3) & ~3
            elif tag == 4:
                p += 4; cur = None
            elif tag == 9:
                break
            else:
                break
        return info
    except Exception as e:
        return {"err": str(e)}

report = {}

# boot / recovery
for fn in ("boot_backup.img", "recovery_backup.img"):
    p = os.path.join(D, fn)
    if os.path.exists(p):
        report[fn] = parse_boot(p)

# FDT 扫描
scan_targets = ["boot_backup.img", "recovery_backup.img", "baseparameter_backup.img",
                "uboot_backup.img", "trust_backup.img", "MiniLoaderAll.bin", "security_backup.img"]
report["fdt"] = {}
for fn in scan_targets:
    p = os.path.join(D, fn)
    if not os.path.exists(p): continue
    hits = find_fdt(p, limit_size=60 << 20 if "super" in fn else None)
    report["fdt"][fn] = []
    for i, h in enumerate(hits[:8]):
        name = f"{fn.split('_')[0]}_dtb{i+1}.dtb"
        blob = dump_fdt(p, h["off"], h["totalsize"], os.path.join(OUT, name))
        m = fdt_model(blob)
        m["off"] = hex(h["off"]); m["size"] = h["totalsize"]; m["saved"] = name
        report["fdt"][fn].append(m)

print(json.dumps(report, indent=2, ensure_ascii=False))
