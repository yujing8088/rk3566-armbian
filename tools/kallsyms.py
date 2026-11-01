#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""解析 ARM64 内核 Image 中的 kallsyms 表（BASE_RELATIVE 布局，4.x/5.x/6.x 通用）

用法: python kallsyms.py <image> [keyword过滤]
image: 未压缩的 arm64 Image（或 boot.img 中偏移 0x800 处开始的内核数据）
"""
import struct
import sys


def find_token_table(data):
    """扫描所有 'gslX6801' 命中点，验证其位于 token_table（256 个连续短字符串）"""
    hits = []
    p = data.find(b"gslX6801")
    while p != -1:
        hits.append(p)
        p = data.find(b"gslX6801", p + 1)
    for h in hits:
        ts = find_token_table_start(data, h)
        if ts is not None:
            return ts
    return None


def find_token_table_start(data, hit):
    """从 hit 向前回退，尝试 256 个 token 的起点"""
    for back in range(0, 8000):
        ts = hit - back
        # 从 ts 开始向后收集 256 个 \0 结尾短串
        p = ts
        toks = []
        ok = True
        for i in range(256):
            e = data.find(b"\x00", p, p + 24)
            if e == -1 or e == p:
                ok = False
                break
            if not all(32 <= c < 127 for c in data[p:e]):
                ok = False
                break
            toks.append(data[p:e])
            p = e + 1
        if ok:
            te = p
            # 紧随其后应是 token_index: 512 字节 u16 单调递增，首项 0
            idx = struct.unpack("<256H", data[te:te + 512])
            if idx[0] == 0 and all(idx[i] <= idx[i + 1] for i in range(255)):
                # token_index 应与 toks 的偏移一致
                off = 0
                match = True
                for i, t in enumerate(toks):
                    if idx[i] != off:
                        match = False
                        break
                    off += len(t) + 1
                if match:
                    return ts, te, toks
    return None


def parse(data, ts, te, toks):
    # markers 结束 = te 向下 8 对齐
    mend = te & ~7
    # 向前找 markers 起点递增 u32 且 markers[0]==0
    p = mend - 4
    mstart = None
    prev = None
    cnt = 0
    while p > mend - 0x40000:
        v = struct.unpack("<I", data[p:p + 4])[0]
        if v == 0 and prev is not None and cnt > 1:
            mstart = p
            break
        if prev is not None and v >= prev:
            cnt += 1
        elif prev is not None and v < prev:
            # 非递增，可能还没进 markers
            pass
        prev = v if prev is None or v >= prev else prev
        p -= 4
    if mstart is None:
        raise SystemExit("markers start not found")
    # 重扫确定 marker 数组（从 mstart 到 mend）
    markers = []
    q = mstart
    while q < mend:
        markers.append(struct.unpack("<I", data[q:q + 4])[0])
        q += 4
    names_len = markers[-1]
    names_start = mstart - names_len
    num_syms_est = (len(markers) - 1) * 256
    # num_syms (u64) + relative_base (u64) 在 names_start 之前（8 对齐）
    p8 = names_start & ~7
    num_syms = struct.unpack("<Q", data[p8:p8 + 8])[0]
    rb_off = p8 - 8
    # num_syms 应约等于估计值
    if not (0.5 * num_syms_est <= num_syms <= 2.5 * num_syms_est):
        print("WARN: num_syms mismatch", num_syms, num_syms_est)
    relative_base = struct.unpack("<Q", data[rb_off:rb_off + 8])[0]
    # offsets 数组：结束于 rb_off（8对齐），长 num_syms*4
    offs_end = rb_off
    offs_start = offs_end - num_syms * 4
    offsets = struct.unpack("<%dI" % num_syms, data[offs_start:offs_end])
    return markers, names_start, num_syms, relative_base, offsets, toks


def decode_names(data, names_start, num_syms, toks):
    names = []
    p = names_start
    for i in range(num_syms):
        ln = data[p]
        p += 1
        raw = data[p:p + ln]
        p += ln
        name = b"".join(toks[c] for c in raw).decode(errors="replace")
        names.append(name)
    return names


def main():
    path = sys.argv[1]
    kw = sys.argv[2] if len(sys.argv) > 2 else None
    data = open(path, "rb").read()
    # 支持 boot.img: 自动定位 Image 起点
    p = data.find(b"ARM\x64", 0, 0x10000)
    img_off = 0 if p == -1 else 0  # 我们以整个文件为窗口，地址换算时再处理
    ts, te, toks = find_token_table(data)
    print("token_table: 0x%x-0x%x (%d bytes, sample: %r)" % (ts, te, te - ts, toks[:8]))
    markers, names_start, num_syms, rb, offsets, toks = parse(data, ts, te, toks)
    print("num_syms=%d relative_base=0x%x names@0x%x" % (num_syms, rb, names_start))
    names = decode_names(data, names_start, num_syms, toks)
    print("decoded %d names" % len(names))
    import re
    pat = re.compile(kw) if kw else re.compile(r"gsl|GSL", re.I)
    n = 0
    for i, nm in enumerate(names):
        if pat.search(nm):
            vaddr = rb + offsets[i]
            print("%6d  0x%016x  file 0x%x  %s" % (i, vaddr, vaddr - rb + img_off, nm))
            n += 1
            if n > 200:
                break


if __name__ == "__main__":
    main()
