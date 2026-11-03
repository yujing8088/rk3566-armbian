#!/usr/bin/env python3
"""解码 RK3568 I2S TDM 控制器的 TXCR / CKR / CLKDIV，判断发送格式是否与外置 DAC 匹配

用法: i2sdecode.py [秒数]
播放一张 1kHz wav 的同时采样，避免空闲时门控关闭读出全 0。
"""
import os
import sys
import time
import mmap
import struct
import subprocess

I2S = 0xFE410000

REG = {
    'TXCR': 0x00, 'RXCR': 0x04, 'CKR': 0x08, 'TXFIFOLR': 0x0C,
    'DMACR': 0x10, 'INTCR': 0x14, 'INTSR': 0x18, 'XFER': 0x1C,
    'CLR': 0x20, 'CLKDIV': 0x38,
}


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def decode(v):
    """把一份快照翻译成人话"""
    txcr, ckr, ckdiv = v['TXCR'], v['CKR'], v['CLKDIV']

    vdw = (txcr & 0x1F) + 1
    csr = (txcr >> 15) & 0x3
    tfs = (txcr >> 5) & 0x3
    ibm = (txcr >> 9) & 0x3
    fbm = (txcr >> 11) & 0x1
    sjm = (txcr >> 12) & 0x1
    hwt = (txcr >> 14) & 0x1

    trcm = (ckr >> 28) & 0x3
    mss = (ckr >> 27) & 0x1
    mdiv = ((ckr >> 16) & 0xFF) + 1
    tsd = (ckr & 0xFF) + 1

    txm = ckdiv & 0xFF

    tfs_name = {0: 'I2S', 1: 'PCM', 2: 'TDM_PCM', 3: 'TDM_I2S'}[tfs]
    ibm_name = {0: 'NORMAL', 1: 'LSJM(left-justified)', 2: 'RSJM'}[ibm]
    chn = {0: 1, 1: 2, 2: 4, 3: 8}.get(csr, '?')
    trcm_name = {0: 'TXRX', 1: 'TXONLY', 2: 'RXONLY'}.get(trcm, '?')

    print('  TXCR     = 0x%08x  VDW=%dbit  CHN=%s  TFS=%s  IBM=%s  FBM=%s  SJM=%s  HWT=%d'
          % (txcr, vdw, chn, tfs_name, ibm_name,
             'LSB' if fbm else 'MSB', 'L' if sjm else 'R', hwt))
    print('  CKR      = 0x%08x  MSS=%s  TRCM=%s  MDIV=%d  TSD(LRCK分频)=%d'
          % (ckr, 'SLAVE' if mss else 'MASTER', trcm_name, mdiv, tsd))
    print('  CLKDIV   = 0x%08x  TXM(BCLK分频)=%d' % (ckdiv, txm))
    print('  XFER     = 0x%08x  TXS=%d RXS=%d'
          % (v['XFER'], v['XFER'] & 1, (v['XFER'] >> 1) & 1))
    print('  TXFIFOLR = 0x%08x  (TX FIFO 未读字数 = %d)'
          % (v['TXFIFOLR'], v['TXFIFOLR'] & 0x3F))

    # 关键一致性检查
    print()
    if not (v['XFER'] & 1):
        print('  !! XFER.TXS=0 —— 发送引擎没启动，SDO 上不会有数据')
    if mss:
        print('  !! MSS=SLAVE —— SoC 不从外部取 BCLK/LRCK，主模式下应为 MASTER')
    if tsd < 2:
        print('  !! TSD=%d 不合理（LRCK 分频至少 2）' % tsd)
    if vdw not in (16, 24, 32):
        print('  !! VDW=%d 不是常见位宽' % vdw)


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    fd, m = openmem(I2S)
    print('播放 1kHz 测试音，期间采样 I2S 寄存器…\n')
    p = subprocess.Popen(['aplay', '-D', 'hw:0,0', '/tmp/long.wav'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)

    snaps = []
    for i in range(3):
        snap = {k: rd(m, off) for k, off in REG.items()}
        snaps.append(snap)
        time.sleep(0.4)
    p.terminate()
    p.wait()

    print('=== 第 1 次采样 ===')
    decode(snaps[0])
    print('\n=== 第 2 次采样（XFER/FIFO 应随时间变化）===')
    decode(snaps[1])
    print('\n=== 第 3 次采样 ===')
    decode(snaps[2])
    os.close(fd)


if __name__ == '__main__':
    main()
