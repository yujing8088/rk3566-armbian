#!/usr/bin/env python3
"""从 kernel.org 递归抓取 dts 依赖 (#include)，保存到 refs/ 保持相对路径"""
import os, re, subprocess, sys, time

REF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "refs"))
BASE = "https://ghproxy.net/https://raw.githubusercontent.com/torvalds/linux/master/"
DTS_DIR = "arch/arm64/boot/dts/rockchip"

def fetch(path):
    dst = os.path.join(REF, path)
    if os.path.exists(dst) and os.path.getsize(dst) > 100:
        return open(dst, encoding="utf-8", errors="replace").read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "-o", dst, BASE + path], capture_output=True)
        if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 100:
            head = open(dst, "rb").read(80)
            if b"<!DOCTYPE" in head or b"<html" in head:
                print("HTML response for", path); break
            return open(dst, encoding="utf-8", errors="replace").read()
        time.sleep(2)
    print("!! failed:", path)
    return ""

seen = set()
def walk(path):
    if path in seen: return
    seen.add(path)
    txt = fetch(path)
    if not txt: return
    for m in re.finditer(r'^\s*#\s*include\s+[<"]([^">]+)[">]', txt, re.M):
        inc = m.group(1)
        if inc.startswith("dt-bindings/"):
            walk("include/" + inc)
        elif inc.endswith(".dtsi") or inc.endswith(".h"):
            walk(DTS_DIR + "/" + inc)

for seed in sys.argv[1:] or ["rk3566.dtsi", "rk3568.dtsi"]:
    walk(DTS_DIR + "/" + seed)
print("fetched:", len(seen))
for p in sorted(seen): print(" ", p)
