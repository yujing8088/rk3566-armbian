#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HI846 上电时序实验 v2（零刷机）

v1 教训：直接写 DR/DDR 电平没生效，怀疑 RSTB/PWDN 引脚 IOMUX 不在 GPIO 功能。
v2 改进：
  1) 先把 GPIO4_B2 / GPIO3_D5 的 IOMUX 强制 mux=0（GPIO 功能）
  2) 写电平后回读 DR 寄存器验证写入是否生效
  3) 打印 vcc_camera(GPIO0_C5) 的 DR/DDR/EXT 三读数判断供电是否真的开着
  4) IOMUX 寄存器：
     bank1..4 在 GRF(0xFDC60000)，每 bank 0x20：
       bank1 0x00.., bank2 0x20.., bank3 0x40.., bank4 0x60..
     每寄存器 4 个引脚 x 4bit：A_L=pin0-3 A_H=pin4-7 B_L=8-11 B_H=12-15
       C_L=16-19 C_H=20-23 D_L=24-27 D_H=28-31
     GPIO4_B2 = bank4 pin10 -> B_L(0x68) bits 11:8
     GPIO3_D5 = bank3 pin29 -> D_H(0x5C) bits 7:4
     GPIO0 属 PMU GRF(0xFDD00000) + 0x00 区：GPIO0C_L = PMUGRF+0x10
"""
import os
import mmap
import struct
import time
import fcntl
import errno

GRF = 0xFDC60000
PMUGRF = 0xFDD00000
CRU = 0xFDD20000
GPIO0 = 0xFDD60000
GPIO3 = 0xFE760000
GPIO4 = 0xFE770000

IOMUX_GPIO4C_L = 0x70
IOMUX_GPIO4B_L = 0x68
IOMUX_GPIO3D_H = 0x5C
IOMUX_GPIO0C_L = 0x10          # PMU GRF
CLKSEL35 = 0x100 + 35 * 4
CLKGATE19 = 0x300 + 19 * 4

PWDN_PIN = 10   # GPIO4_B2
RST_PIN = 29    # GPIO3_D5
VCC_PIN = 21    # GPIO0_C5

I2C_SLAVE = 0x0703


def openmem(addr, size=0x1000):
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    return fd, mmap.mmap(fd, size, mmap.MAP_SHARED,
                         mmap.PROT_READ | mmap.PROT_WRITE, offset=addr)


def rd(m, off):
    return struct.unpack('<I', m[off:off + 4])[0]


def hiword(m, off, mask, value):
    m[off:off + 4] = struct.pack('<I', ((value & 0xFFFF) | ((mask & 0xFFFF) << 16)))


class Gpio:
    def __init__(self, base):
        self.fd, self.m = openmem(base)

    def out(self, pin, level):
        if pin < 16:
            ddr, dr, bit = 0x08, 0x00, pin
        else:
            ddr, dr, bit = 0x0C, 0x04, pin - 16
        m = 1 << bit
        hiword(self.m, ddr, m, m)                  # 方向=输出
        hiword(self.m, dr, m, (level & 1) << bit)  # 电平

    def get_dr(self, pin):
        off = 0x00 if pin < 16 else 0x04
        return (rd(self.m, off) >> (pin % 16)) & 1

    def get_ddr(self, pin):
        off = 0x08 if pin < 16 else 0x0C
        return (rd(self.m, off) >> (pin % 16)) & 1

    def get_ext(self, pin):
        return (rd(self.m, 0x50) >> pin) & 1   # GPIO_EXT_PORT 单个 32bit 寄存器

    def close(self):
        self.m.close()
        os.close(self.fd)


def force_gpio_mux(grf_m, off, pin):
    """把指定引脚的 IOMUX 字段清 0（GPIO 功能）"""
    field = (pin % 4) * 4
    mask = 0xF << field
    hiword(grf_m, off, mask, 0)


def get_mux(grf_m, off, pin):
    field = (pin % 4) * 4
    return (rd(grf_m, off) >> field) & 0xF


def i2c_probe(bus, addr):
    try:
        fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
    except OSError as e:
        return 'open-fail:' + str(e)
    try:
        try:
            fcntl.ioctl(fd, I2C_SLAVE, addr)
        except OSError as e:
            return 'ioctl:' + errno.errorcode.get(e.errno, str(e.errno))
        try:
            os.write(fd, b'\x00')
            return 'ACK'
        except OSError as e:
            return None
    finally:
        os.close(fd)


def i2c_read16(bus, addr, reg):
    fd = None
    try:
        fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
        fcntl.ioctl(fd, I2C_SLAVE, addr)
        os.write(fd, struct.pack('>H', reg))
        data = os.read(fd, 2)
        return struct.unpack('>H', data)[0]
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


def scan(bus=2):
    return [a for a in range(3, 0x78) if i2c_probe(bus, a) == 'ACK']


def report(tag, g4, g3):
    hits = scan()
    extra = ''
    for a in (0x20, 0x22):
        if a in hits:
            id0 = i2c_read16(2, a, 0x0000)
            id1 = i2c_read16(2, a, 0x0001)
            extra += '  ID@0x%02x: %s %s' % (
                a, '%04x' % id0 if id0 is not None else '--',
                '%04x' % id1 if id1 is not None else '--')
    print('[%s] PWDN drv=%d RSTB drv=%d | 扫描: %s%s'
          % (tag, g4.get_dr(PWDN_PIN), g3.get_dr(RST_PIN),
             hits if hits else '无', extra))


def main():
    fdg_, grf = openmem(GRF)
    _, pmugrf = openmem(PMUGRF)
    fdc_, cru = openmem(CRU)
    g4 = Gpio(GPIO4)
    g3 = Gpio(GPIO3)
    g0 = Gpio(GPIO0)

    print('=== 前状态 ===')
    print('GPIO0_C5: PMUGRF+0x10=0x%08x mux=%d | DR=%d DDR=%d EXT=%d'
          % (rd(pmugrf, IOMUX_GPIO0C_L), get_mux(pmugrf, IOMUX_GPIO0C_L, VCC_PIN),
             g0.get_dr(VCC_PIN), g0.get_ddr(VCC_PIN), g0.get_ext(VCC_PIN)))
    print('GPIO4_B2: GRF+0x68=0x%08x mux=%d | DR=%d DDR=%d EXT=%d'
          % (rd(grf, IOMUX_GPIO4B_L), get_mux(grf, IOMUX_GPIO4B_L, PWDN_PIN),
             g4.get_dr(PWDN_PIN), g4.get_ddr(PWDN_PIN), g4.get_ext(PWDN_PIN)))
    print('GPIO3_D5: GRF+0x5C=0x%08x mux=%d | DR=%d DDR=%d EXT=%d'
          % (rd(grf, IOMUX_GPIO3D_H), get_mux(grf, IOMUX_GPIO3D_H, RST_PIN),
             g3.get_dr(RST_PIN), g3.get_ddr(RST_PIN), g3.get_ext(RST_PIN)))

    # 1) 供电：GPIO0_C5 强制输出高
    force_gpio_mux(pmugrf, IOMUX_GPIO0C_L, VCC_PIN)
    g0.out(VCC_PIN, 1)
    print('vcc_camera 强制高: DR=%d EXT=%d' % (g0.get_dr(VCC_PIN), g0.get_ext(VCC_PIN)))

    # 2) xvclk：GPIO4_C0 -> cif_clkout 24MHz + gate 开
    hiword(grf, IOMUX_GPIO4C_L, 0xF, 1)
    hiword(cru, CLKSEL35, 0xC000, 2 << 14)
    hiword(cru, CLKSEL35, 0x3F00, 1 << 8)
    hiword(cru, CLKGATE19, 1 << 8, 0)
    print('xvclk: C0mux=%d gate=%d CLKSEL35=0x%08x'
          % (get_mux(grf, IOMUX_GPIO4C_L, 16), (rd(cru, CLKGATE19) >> 8) & 1,
             rd(cru, CLKSEL35)))

    # 3) PWDN/RSTB 强制 GPIO 功能
    force_gpio_mux(grf, IOMUX_GPIO4B_L, PWDN_PIN)
    force_gpio_mux(grf, IOMUX_GPIO3D_H, RST_PIN)
    print('IOMUX 已强制 GPIO: B2mux=%d D5mux=%d'
          % (get_mux(grf, IOMUX_GPIO4B_L, PWDN_PIN),
             get_mux(grf, IOMUX_GPIO3D_H, RST_PIN)))

    # 4) 矩阵
    for pwdn in (0, 1):
        for rst in (0, 1):
            g4.out(PWDN_PIN, pwdn)
            g3.out(RST_PIN, rst)
            time.sleep(0.05)
            report('静态', g4, g3)

    # 5) 完整脉冲：断电->上电->复位释放
    for p_down in (1, 0):
        g4.out(PWDN_PIN, p_down)
        g3.out(RST_PIN, 0)
        time.sleep(0.02)
        g4.out(PWDN_PIN, 1 - p_down)
        time.sleep(0.02)
        g3.out(RST_PIN, 1)
        time.sleep(0.05)
        report('pulse pwdn_down=%d' % p_down, g4, g3)
        g3.out(RST_PIN, 0)
        time.sleep(0.01)
        g3.out(RST_PIN, 1)
        time.sleep(0.05)
        report('pulse+rst', g4, g3)

    # 收尾
    g4.out(PWDN_PIN, 0)
    g3.out(RST_PIN, 1)

    for x in (g4, g3, g0):
        x.close()
    grf.close(); pmugrf.close(); cru.close()
    os.close(fdg_); os.close(fdc_)
    print('done')


if __name__ == '__main__':
    main()
