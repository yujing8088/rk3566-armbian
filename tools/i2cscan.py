#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
I2C 总线扫描（板上没有 i2cdetect，用 ioctl 自己实现）

用法: python3 i2cscan.py [总线号=2]

原理：对每个 7bit 地址 open /dev/i2c-N -> ioctl(I2C_SLAVE, addr) -> write 1 字节。
设备存在会 ACK（写成功），不存在会返回 ENXIO/EIO/EREMOTEIO。
写入的 0x00 只相当于"把寄存器指针指到 0"，对 sensor 无副作用。
"""
import os
import sys
import fcntl
import errno

I2C_SLAVE = 0x0703


def probe(fd, addr):
    try:
        fcntl.ioctl(fd, I2C_SLAVE, addr)
    except OSError as e:
        return 'ioctl-error(%s)' % errno.errorcode.get(e.errno, e.errno)
    try:
        os.write(fd, b'\x00')
        return 'ACK'
    except OSError as e:
        code = errno.errorcode.get(e.errno, str(e.errno))
        if e.errno in (errno.ENXIO, errno.EIO, errno.EREMOTEIO):
            return None
        return 'err(%s)' % code


def main():
    bus = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    path = '/dev/i2c-%d' % bus
    if not os.path.exists(path):
        raise SystemExit('没有 %s，检查 DTS 里 i2c%d 是否 status=okay' % (path, bus))

    print('扫描 %s ...' % path)
    found = []
    for addr in range(0x08, 0x78):
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError as e:
            raise SystemExit('打开 %s 失败: %s' % (path, e))
        try:
            r = probe(fd, addr)
        finally:
            os.close(fd)
        if r == 'ACK':
            found.append(addr)
            print('  0x%02x  ACK   <-- 有设备' % addr)

    print('')
    if found:
        print('发现 %d 个设备: %s' % (len(found), ', '.join('0x%02x' % a for a in found)))
        for a in found:
            if a in (0x20, 0x22):
                print('  >>> 0x%02x 与 HI846 地址吻合' % a)
    else:
        print('整条总线无任何 ACK —— 传感器可能未上电 / PWDN 未释放 / 走错总线')


if __name__ == '__main__':
    main()
