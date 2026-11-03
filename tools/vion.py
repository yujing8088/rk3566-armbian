#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动上电 RK3566 VI 电源域（零刷机验证 power-domains=<&power RK3568_PD_VI> 假说）

寄存器（PMU 基址 0xFDD90000，取自 6.18 pm-domains.c rk3568_pmu）：
  PWR_CON  = 0xa0   VI 域 bit6：0=上电请求
  STATUS   = 0x98   VI 域 bit6：0=已上电，1=断电
  REQ      = 0x50   VI 域 bit3（NIU 请求）
  IDLE     = 0x68   VI 域 bit3：1=空闲
  ACK      = 0x60   VI 域 bit3
  时钟：CRU CLKGATE_CON(18)=0x348 bit0/1/2 = ACLK/HCLK/PCLK_VI，0=开

序列（复刻 rockchip_pd_power → on）：
  1) 开 HCLK/PCLK/ACLK_VI 门控
  2) PWR_CON bit6 清 0
  3) 轮询 STATUS bit6 == 0（最多 10ms）
  4) REQ bit3 清 0（解除 idle 请求），轮询 ACK bit3 == 0
"""
import os
import mmap
import struct
import time
import fcntl
import errno

PMU = 0xFDD90000
CRU = 0xFDD20000
GPIO4 = 0xFE770000

PWR_CON, STATUS = 0xA0, 0x98
REQ, IDLE, ACK = 0x50, 0x68, 0x60
CLKGATE18 = 0x300 + 18 * 4      # 0x348
CLKGATE19 = 0x300 + 19 * 4      # 0x34C


def openmem(addr):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, 0x1000, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def hiword(m, off, mask, value):
    m[off:off + 4] = struct.pack('<I', ((value & 0xFFFF) | ((mask & 0xFFFF) << 16)))


def i2c_probe(addr):
    try:
        fd = os.open('/dev/i2c-2', os.O_RDWR)
        fcntl.ioctl(fd, 0x0703, addr)
        try:
            os.read(fd, 1)
            return True
        except OSError:
            return False
        finally:
            os.close(fd)
    except OSError:
        return False


def main():
    fdm, m = openmem(PMU)
    fdc, c = openmem(CRU)
    fdg, g = openmem(GPIO4)

    st = rd(m, STATUS)
    print('上电前: STATUS bit6(PWR)=%d PWR_CON=0x%08x REQ=0x%08x ACK=0x%08x'
          % ((st >> 6) & 1, rd(m, PWR_CON), rd(m, REQ), rd(m, ACK)))
    print('        CLKGATE18=0x%08x (bit0/1/2 = ACLK/HCLK/PCLK_VI, 0=开)'
          % rd(c, CLKGATE18))

    # 1) 开 VI 时钟门控
    hiword(c, CLKGATE18, 0x7, 0)
    print('VI 时钟门控已开: CLKGATE18=0x%08x' % rd(c, CLKGATE18))

    # 2) 上电请求
    hiword(m, PWR_CON, 1 << 6, 0)
    # 3) 轮询 STATUS
    ok = False
    for _ in range(100):
        if ((rd(m, STATUS) >> 6) & 1) == 0:
            ok = True
            break
        time.sleep(0.0001)
    print('PWR_CON=0x%08x STATUS bit6=%d -> %s'
          % (rd(m, PWR_CON), (rd(m, STATUS) >> 6) & 1,
             'VI 域已上电' if ok else '超时！'))

    # 4) 解除 idle 请求
    hiword(m, REQ, 1 << 3, 0)
    for _ in range(100):
        if ((rd(m, ACK) >> 3) & 1) == 0:
            break
        time.sleep(0.0001)
    print('REQ=0x%08x ACK bit3=%d' % (rd(m, REQ), (rd(m, ACK) >> 3) & 1))

    # 验证 MCLK 引脚
    vals = ''.join(str((rd(g, 0x70) >> 16) & 1) for _ in range(30))
    print('MCLK C0 采样30次:', vals)

    # 扫 I2C
    hits = [a for a in range(3, 0x78) if i2c_probe(a)]
    print('I2C 扫描命中:', [hex(a) for a in hits] if hits else '无')

    m.close(); c.close(); g.close()
    os.close(fdm); os.close(fdc); os.close(fdg)


if __name__ == '__main__':
    main()
