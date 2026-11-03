#!/usr/bin/env python3
"""喇叭声学闭环自检：用板载 PDM 麦克风当"耳朵"，判断扬声器到底有没有发声。

流程：
  1) 生成指定频率的正弦测试音（48k/16bit/立体声）
  2) 先录 3 秒"静音基线"，再边播边录 5 秒
  3) 对录音做 Goertzel 单频检测，比较基线段与播放段的能量
     —— 若播放段在 f0 处的能量显著高于基线，说明喇叭真的响了

用法:
  spkcheck.py [频率Hz] [时长s] [振幅]
返回码: 0 = 喇叭响; 2 = 没响; 3 = 录音失败
"""
import os
import re
import struct
import subprocess
import sys
import time
import wave
import math

RATE = 48000
TMP_TONE = "/tmp/spk_tone.wav"
TMP_REC = "/tmp/spk_rec.wav"


def cards():
    """解析 /proc/asound/cards，返回 {name: index}。"""
    out = {}
    try:
        txt = open("/proc/asound/cards").read()
    except OSError:
        return out
    for line in txt.splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]", line)
        if m:
            out[m.group(2).strip().lower()] = int(m.group(1))
    return out


def find(cardmap, needle):
    for name, idx in cardmap.items():
        if needle in name:
            return idx
    return None


def make_tone(path, freq, dur, amp):
    n = int(RATE * dur)
    buf = bytearray()
    step = 2.0 * math.pi * freq / RATE
    for i in range(n):
        v = int(amp * math.sin(step * i))
        buf += struct.pack("<hh", v, v)
    w = wave.open(path, "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(bytes(buf))
    w.close()


def goertzel(samples, freq):
    """返回该频率上的归一化幅值（均方根意义）。"""
    n = len(samples)
    if n == 0:
        return 0.0
    k = 2.0 * math.cos(2.0 * math.pi * freq / RATE)
    s0 = s1 = s2 = 0.0
    for x in samples:
        s0 = x + k * s1 - s2
        s2 = s1
        s1 = s0
    power = s1 * s1 + s2 * s2 - k * s1 * s2
    # 归一化：满幅正弦的 Goertzel 功率约为 (n*amp/2)^2
    return math.sqrt(max(power, 0.0)) / (n / 2.0)


def read_wav(path):
    w = wave.open(path, "rb")
    nch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    if width != 2:
        raise ValueError("只支持 16bit wav")
    total = len(raw) // 2
    chans = [[] for _ in range(nch)]
    vals = struct.unpack("<%dh" % total, raw)
    for i, v in enumerate(vals):
        chans[i % nch].append(v)
    return chans, rate


def rms(xs):
    if not xs:
        return 0.0
    return math.sqrt(sum(float(x) * x for x in xs) / len(xs))


def main():
    freq = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    amp = int(sys.argv[3]) if len(sys.argv) > 3 else 24000

    cm = cards()
    spk = find(cm, "cs4333")
    mic = find(cm, "pdm")
    print("声卡: %s" % cm)
    if spk is None or mic is None:
        print("!! 找不到 cs4333 或 pdm 声卡")
        return 3

    make_tone(TMP_TONE, freq, dur, amp)
    lead = 3.0
    total = lead + dur + 0.5
    print("录音 %0.1fs（前 %0.0fs 静音基线，后段边播边录）…" % (total, lead))

    rec = subprocess.Popen(
        ["arecord", "-D", "hw:%d,0" % mic, "-f", "S16_LE", "-r", str(RATE),
         "-c", "2", "-d", "%d" % int(total + 1), TMP_REC],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(lead)
    t0 = time.time()
    play = subprocess.run(
        ["aplay", "-D", "hw:%d,0" % spk, TMP_TONE],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pout = play.stdout.decode("utf-8", "replace").strip()
    print("aplay 返回 %d %s" % (play.returncode, ("| " + pout) if pout else ""))
    rout, _ = rec.communicate()
    rtxt = rout.decode("utf-8", "replace").strip()
    if rtxt:
        print("arecord: %s" % rtxt.splitlines()[-1])

    if not os.path.exists(TMP_REC):
        print("!! 没有录音文件")
        return 3
    chans, rate = read_wav(TMP_REC)
    nlead = int(lead * rate)
    ntot = len(chans[0])
    if ntot < nlead + int(dur * rate * 0.6):
        print("!! 录音太短: %d 帧 (rate=%d)" % (ntot, rate))
        return 3

    print("录音: %d 帧  %d 声道  %d Hz" % (ntot, len(chans), rate))
    verdict = 2
    for ci, ch in enumerate(chans):
        base = ch[int(0.8 * rate):nlead]
        sig = ch[nlead + int(0.3 * rate):nlead + int(0.3 * rate) + int(dur * rate * 0.6)]
        gb = goertzel(base, freq)
        gs = goertzel(sig, freq)
        rb, rs = rms(base), rms(sig)
        ratio = (gs / gb) if gb > 0.5 else (gs / 0.5)
        print("ch%d  基线: rms=%7.1f  @%0.0fHz=%7.1f | 播放: rms=%7.1f  @%0.0fHz=%7.1f | 增强 %.1fx"
              % (ci, rb, freq, gb, rs, freq, gs, ratio))
        if gs > 60 and ratio > 3.0:
            verdict = 0
    if verdict == 0:
        print(">>> 判定: 喇叭有声音（麦克风在测试频率上检测到显著能量）")
    else:
        print(">>> 判定: 喇叭没有可闻声音（测试频率上无显著能量）")
    return verdict


if __name__ == "__main__":
    sys.exit(main())
