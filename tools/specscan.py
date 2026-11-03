#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全频段频谱扫描（不依赖 numpy）
用法: python specscan.py <wav文件> [起始Hz] [结束Hz] [步进Hz]

作用: 对录音做 Goertzel 扫频, 输出相对噪声底最强的若干个频点,
      用来判定喇叭到底有没有发出任何声音(含频率偏掉的情况)。
"""
import sys, wave, struct, math


def load_mono(path):
    w = wave.open(path, 'rb')
    nch = w.getnchannels()
    sw = w.getsampwidth()
    rate = w.getframerate()
    raw = w.readframes(w.getnframes())
    w.close()
    if sw != 2:
        raise SystemExit('只支持 16bit wav, 当前 %d byte' % sw)
    total = len(raw) // (2 * nch)
    data = struct.unpack('<%dh' % (total * nch), raw[:total * nch * 2])
    if nch == 1:
        mono = list(data)
    else:
        mono = [sum(data[i * nch:(i + 1) * nch]) / float(nch) for i in range(total)]
    return mono, rate


def goertzel(samples, rate, freq):
    """返回该频率的幅度(归一化到 0dBFS=1.0)"""
    n = len(samples)
    k = int(0.5 + n * freq / rate)
    omega = 2.0 * math.pi * k / n
    coeff = 2.0 * math.cos(omega)
    s0 = s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    if power < 0:
        power = 0.0
    amp = 2.0 * math.sqrt(power) / n / 32768.0
    return amp


def rms(samples):
    if not samples:
        return 0.0
    s = 0.0
    for x in samples:
        s += x * x
    return math.sqrt(s / len(samples))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    f0 = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
    f1 = float(sys.argv[3]) if len(sys.argv) > 3 else 5000.0
    step = float(sys.argv[4]) if len(sys.argv) > 4 else 25.0

    mono, rate = load_mono(path)
    dur = len(mono) / float(rate)
    print('文件 %s' % path)
    print('采样率 %d Hz, 声道混单, 时长 %.2f s, 样本 %d' % (rate, dur, len(mono)))
    print('整体 RMS = %.1f LSB' % rms(mono))

    # 分段 RMS：看是否有 3 秒一循环的起伏（aplay 单次 30 秒，中间无缝）
    seg = int(rate * 0.5)
    parts = []
    for i in range(0, len(mono) - seg + 1, seg):
        parts.append(rms(mono[i:i + seg]))
    if parts:
        print('每 0.5s 的 RMS: ' + ' '.join('%.0f' % p for p in parts))

    # 取中间一段做频谱（避开开头启动瞬态）
    n = min(len(mono) // 2, int(rate * 1.5))
    if n < 2048:
        raise SystemExit('录音太短')
    start = (len(mono) - n) // 2
    block = mono[start:start + n]
    block = [x - sum(block) / len(block) for x in block]  # 去直流
    print('分析窗: %d 样本 (%.2f s), 从 %.2f s 开始' % (n, n / float(rate), start / float(rate)))
    print('频率分辨率约 %.1f Hz' % (rate / float(n)))

    freqs = []
    f = f0
    while f <= f1:
        freqs.append(f)
        f += step

    mags = []
    for f in freqs:
        mags.append((f, goertzel(block, rate, f)))

    vals = sorted(m for _, m in mags)
    floor = vals[len(vals) // 2]          # 中位数当噪声底
    top = vals[-1]
    db = [20 * math.log10((m + 1e-12) / (floor + 1e-12)) for _, m in mags]

    print('噪声底(中位) = %.6f  最大 = %.6f  动态范围 = %.1f dB' % (floor, top, 20 * math.log10((top + 1e-12) / (floor + 1e-12))))
    print('')
    print('--- 最强 12 个频点 ---')
    order = sorted(range(len(mags)), key=lambda i: -mags[i][1])[:12]
    for i in sorted(order, key=lambda i: -mags[i][1]):
        f, m = mags[i]
        bar = '#' * max(0, int(db[i] / 1.5))
        print('  %7.1f Hz  幅度 %.6f  %+6.1f dB  %s' % (f, m, db[i], bar))
    print('')

    # 关键判定
    strong = [(f, db[i]) for i, (f, m) in enumerate(mags) if db[i] > 12.0]
    if not strong:
        print('判定: 整个 %g-%g Hz 内没有任何超过噪声底 12 dB 的成分 → 喇叭在录这段时确实没有发声。' % (f0, f1))
    else:
        print('判定: 发现 %d 个显著频点（>噪声底 12 dB），最高 %+.1f dB:' % (len(strong), max(d for _, d in strong)))
        for f, d in strong[:10]:
            print('   %7.1f Hz  %+.1f dB' % (f, d))


if __name__ == '__main__':
    main()
