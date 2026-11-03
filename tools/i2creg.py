#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读 I2C 设备的 16bit 寄存器（sensor 常用：写 2 字节地址，读 N 字节）

用法:
  python3 i2creg.py <bus> <addr> <reg(hex)> [长度=2]

例：python3 i2creg.py 2 0x0c 0x0000     # 读 chip id
"""
import os
import sys
import ctypes
import fcntl

I2C_RDWR = 0x0707


class I2CMsg(ctypes.Structure):
    _fields_ = [
        ('addr', ctypes.c_uint16),
        ('flags', ctypes.c_uint16),
        ('len', ctypes.c_uint16),
        ('buf', ctypes.POINTER(ctypes.c_uint8)),
    ]


class I2CRdwrData(ctypes.Structure):
    _fields_ = [
        ('msgs', ctypes.POINTER(I2CMsg)),
        ('nmsgs', ctypes.c_uint32),
    ]


def read_regs(fd, addr, reg, length):
    wbuf = (ctypes.c_uint8 * 2)((reg >> 8) & 0xFF, reg & 0xFF)
    rbuf = (ctypes.c_uint8 * length)()
    msgs = (I2CMsg * 2)()
    msgs[0].addr = addr
    msgs[0].flags = 0            # write
    msgs[0].len = 2
    msgs[0].buf = wbuf
    msgs[1].addr = addr
    msgs[1].flags = 1            # I2C_M_RD
    msgs[1].len = length
    msgs[1].buf = rbuf
    data = I2CRdwrData(msgs, 2)
    fcntl.ioctl(fd, I2C_RDWR, data)
    return bytes(rbuf)


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    bus = int(sys.argv[1])
    addr = int(sys.argv[2], 0)
    reg = int(sys.argv[3], 0)
    length = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
    try:
        data = read_regs(fd, addr, reg, length)
        print('bus%d 0x%02x reg 0x%04x = %s'
              % (bus, addr, reg, ' '.join('0x%02x' % b for b in data)))
        if length == 2:
            print('  as u16 = 0x%02x%02x' % (data[0], data[1]))
    except OSError as e:
        print('读取失败: %s' % e)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
