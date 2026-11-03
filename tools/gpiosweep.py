#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPIO0 引脚扫描器：把候选引脚依次拉高/拉低，配合万用表定位隐藏的 5V 使能脚。
用法:
  gpiosweep.py read <pins>          # 打印引脚 DR/DDR/pad 状态
  gpiosweep.py sweep <pins> <sec>   # 全组拉高 sec 秒 → 悬空 1 秒 → 全组拉低 sec 秒 → 恢复
  gpiosweep.py set <pins> <0|1>     # 全组输出指定电平（保持）
  gpiosweep.py restore              # 恢复 sweep/set 前保存的原始状态
pins = 逗号分隔的 GPIO0 引脚号(0-31)
RK3566 GPIO0 base=0xFDD60000；寄存器高 16 位为写掩码。
"""
import mmap
import os
import struct
import sys
import json
import time

PAGE = 4096
BANKS = {
    0: 0xFDD60000,
    1: 0xFE740000,
    2: 0xFE750000,
    3: 0xFE760000,
    4: 0xFE770000,
}
STATE_FILE = "/tmp/gpiosweep_state.json"

DR = {0: 0x0000, 1: 0x0004}      # SWPORT_DR_L / _H
DDR = {0: 0x0008, 1: 0x000C}     # SWPORT_DDR_L / _H
EXT = {0: 0x0070, 1: 0x0074}     # EXT_PORT_L / _H


def mmap0(bank=0):
    base = BANKS[bank]
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, PAGE, mmap.MAP_SHARED,
                  mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
    return fd, m


def rd32(m, off):
    return struct.unpack("<I", m[off:off + 4])[0]


def wr32(m, off, v):
    m[off:off + 4] = struct.pack("<I", v)


def wbit(m, off, bit, val):
    """带写掩码地修改某一位。"""
    cur = rd32(m, off)
    new = (cur & 0xffff & ~(1 << bit)) | (val << bit)
    wr32(m, off, new | (1 << bit) << 16)


def pin2h(p):
    return 0 if p < 16 else 1


def save_state(m, pins, bank):
    st = {"bank": bank, "pins": {}}
    for p in pins:
        h = pin2h(p)
        b = p & 15
        st["pins"][str(p)] = {
            "dr": (rd32(m, DR[h]) >> b) & 1,
            "ddr": (rd32(m, DDR[h]) >> b) & 1,
        }
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)
    return st


def restore_state(m):
    if not os.path.exists(STATE_FILE):
        print("无保存的状态")
        return
    st = json.load(open(STATE_FILE))
    for p, v in st["pins"].items():
        p = int(p)
        h, b = pin2h(p), p & 15
        wbit(m, DR[h], b, v["dr"])
        wbit(m, DDR[h], b, v["ddr"])
    print("已恢复 bank%s %d 个引脚的原始状态"
          % (st.get("bank"), len(st["pins"])))


def read_pins(m, pins):
    for p in pins:
        h, b = pin2h(p), p & 15
        dr = (rd32(m, DR[h]) >> b) & 1
        ddr = (rd32(m, DDR[h]) >> b) & 1
        pad = (rd32(m, EXT[h]) >> b) & 1
        label = "GPIO0_%s%d" % ("ABCD"[p // 8], p % 8)
        print("pin %-3d %-9s dir=%s out=%d pad=%d"
              % (p, label, "out" if ddr else "in ", dr, pad))


def drive(m, pins, out, val=None):
    for p in pins:
        h, b = pin2h(p), p & 15
        if out:
            wbit(m, DDR[h], b, 1)
            wbit(m, DR[h], b, val)
        else:
            wbit(m, DDR[h], b, 0)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    mode = sys.argv[1]
    bank = int(sys.argv[2]) if sys.argv[1] in ("read", "sweep", "set") else 0
    if bank not in BANKS:
        print("bank 必须是 0-4")
        return 1
    fd, m = mmap0(bank)
    try:
        if mode == "read":
            pins = [int(x) for x in sys.argv[3].split(",")]
            read_pins(m, pins)
        elif mode == "sweep":
            pins = [int(x) for x in sys.argv[3].split(",")]
            sec = float(sys.argv[4]) if len(sys.argv) > 4 else 6
            save_state(m, pins, bank)
            print("[%s] bank%d 拉高 %s ..." % (time.strftime("%H:%M:%S"), bank, pins))
            drive(m, pins, True, 1)
            time.sleep(sec)
            print("[%s] 悬空 ..." % time.strftime("%H:%M:%S"))
            drive(m, pins, False)
            time.sleep(1)
            print("[%s] 拉低 ..." % time.strftime("%H:%M:%S"))
            drive(m, pins, True, 0)
            time.sleep(sec)
            print("[%s] 恢复原始状态 ..." % time.strftime("%H:%M:%S"))
            restore_state(m)
        elif mode == "set":
            pins = [int(x) for x in sys.argv[3].split(",")]
            val = int(sys.argv[4])
            save_state(m, pins, bank)
            drive(m, pins, True, val)
            print("[%s] bank%d %s 已置 %d（保持中，测完记得 restore）"
                  % (time.strftime("%H:%M:%S"), bank, pins, val))
        elif mode == "restore":
            restore_state(m)
        else:
            print("未知模式: %s" % mode)
            return 1
    finally:
        m.close()
        os.close(fd)
    return 0


sys.exit(main())
