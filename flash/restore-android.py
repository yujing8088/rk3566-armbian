#!/usr/bin/env python3
"""
从分区备份还原 Android —— 生成 parameter.txt + rkdeveloptool 写回命令

两种模式：
  1) 有 GPT 备份（最准）：
     python restore-android.py --gpt gpt-primary.bin --dir ../../android
     按 GPT 里的分区名匹配 *_backup.img，输出精确 LBA
  2) 只有分区镜像（推算）：
     python restore-android.py --dir ../../android --pack
     按 Rockchip 标准"顺序紧排"规则从 LBA 0x4000 开始排布

输出：parameter.txt（可 rkdeveloptool ppt 写分区表）与 restore.sh（逐分区 wl 写回）
加 --apply 则直接调用 rkdeveloptool 执行（需设备在 MaskROM）
"""
import argparse, os, struct, subprocess, sys

# 分区名 -> 备份文件名（按匹配优先级）
KNOWN = ["uboot", "trust", "misc", "dtbo", "vbmeta", "boot", "recovery", "backup",
         "security", "metadata", "baseparameter", "super", "cache"]
# 标准紧排顺序（dtbo 若无备份则跳过）
PACK_ORDER = ["uboot", "trust", "misc", "vbmeta", "boot", "recovery", "backup",
              "security", "metadata", "baseparameter", "super", "cache"]


def sectors(path):
    return (os.path.getsize(path) + 511) // 512


def find_images(d):
    out = {}
    for f in os.listdir(d):
        if not f.endswith(".img"):
            continue
        base = f[:-4].replace("_backup", "")
        out[base] = os.path.join(d, f)
    return out


def parse_gpt(path):
    """返回 [(name, first_lba, last_lba, size_sectors)]"""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) >= 1024 and data[512:520] == b"EFI PART":
        hdr = 512
    elif data[:8] == b"EFI PART":
        hdr = 0
    else:
        sys.exit("不是有效的 GPT 镜像（缺 EFI PART 签名）")
    part_lba = struct.unpack_from("<Q", data, hdr + 72)[0]
    num = struct.unpack_from("<I", data, hdr + 80)[0]
    esz = struct.unpack_from("<I", data, hdr + 84)[0]
    # 分区表可能不在读到的缓冲里，按 LBA 计算文件内偏移
    base = part_lba * 512 - hdr
    parts = []
    for i in range(num):
        off = base + i * esz
        if off + 128 > len(data):
            break
        e = data[off:off + 128]
        if e[:16] == b"\0" * 16:
            continue
        name = e[56:128].decode("utf-16-le", errors="replace").rstrip("\0")
        first, last = struct.unpack_from("<QQ", e, 32)
        parts.append((name, first, last, last - first + 1))
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="存放 *_backup.img 的目录")
    ap.add_argument("--gpt", help="GPT 备份（含主表 34 扇区）")
    ap.add_argument("--pack", action="store_true", help="无 GPT 时按紧排规则推算")
    ap.add_argument("--start-lba", type=lambda x: int(x, 0), default=0x4000)
    ap.add_argument("--out", default=".", help="输出目录")
    ap.add_argument("--apply", action="store_true", help="直接调用 rkdeveloptool 写回")
    args = ap.parse_args()

    imgs = find_images(args.dir)
    if not imgs:
        sys.exit(f"{args.dir} 里没找到 *_backup.img")
    os.makedirs(args.out, exist_ok=True)

    plan = []  # (name, lba, file)
    if args.gpt:
        for name, first, last, cnt in parse_gpt(args.gpt):
            key = name.split("_")[0]
            if key in imgs:
                plan.append((name, first, cnt, imgs[key]))
            else:
                print(f"  (跳过 {name}: 无对应备份)")
        plan.sort(key=lambda x: x[1])
    else:
        if not args.pack:
            sys.exit("请指定 --gpt（精确）或 --pack（推算）")
        lba = args.start_lba
        for key in PACK_ORDER:
            if key not in imgs:
                print(f"  (缺少 {key} 备份，跳过)")
                continue
            cnt = sectors(imgs[key])
            plan.append((key, lba, cnt, imgs[key]))
            lba += cnt

    total = max((l + c for _, l, c, _ in plan), default=0)
    print("\n%-16s %-12s %-12s %s" % ("分区", "起始 LBA", "字节偏移", "文件"))
    for name, lba, cnt, path in plan:
        print("%-16s 0x%-10x 0x%-10x %s" % (name, lba, lba * 512, os.path.basename(path)))
    print(f"\n合计占用到 LBA 0x{total:x} (约 {total * 512 / 2**30:.2f} GiB)")

    # parameter.txt
    pfile = os.path.join(args.out, "parameter.txt")
    pstr = ",".join(f"0x{c:08x}@0x{l:08x}({n})" for n, l, c, _ in plan)
    with open(pfile, "w", newline="\n") as fh:
        fh.write(f"FIRMWARE_VER: 11.0.0\nMACHINE_MODEL: RK3566\n"
                 f"MACHINE_ID: 007\nMANUFACTURER: RK3566\nMAGIC: 0x5041524B\n"
                 f"ATAG: 0x00200800\nMACHINE: 0xffffffff\n"
                 f"CHECK_MASK: 0x80\nPWR_HLD: 0,0,A,0,1\n"
                 f"TYPE: GPT\nCMDLINE: mtdparts=rk29xxnand:{pstr}\n")
    print(f"已写出 {pfile}")

    # restore.sh
    sh = os.path.join(args.out, "restore-android.sh")
    with open(sh, "w", newline="\n") as fh:
        fh.write("#!/bin/sh\nset -e\n# 需设备处于 MaskROM，并已 rkdeveloptool db <loader>\n")
        for name, lba, cnt, path in plan:
            fh.write(f'echo "== {name}"\nrkdeveloptool wl 0x{lba:x} "{os.path.abspath(path)}"\n')
        fh.write("rkdeveloptool rd\n")
    print(f"已写出 {sh}")

    if args.apply:
        for name, lba, cnt, path in plan:
            print(f"--> 写入 {name} @ LBA 0x{lba:x}")
            subprocess.run(["rkdeveloptool", "wl", hex(lba), path], check=True)
        subprocess.run(["rkdeveloptool", "rd"], check=False)


if __name__ == "__main__":
    main()
