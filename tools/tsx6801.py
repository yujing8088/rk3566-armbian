import ctypes, fcntl, os, struct, time

ADDR = 0x40
GPIO = '/sys/class/gpio/gpio14/value'
INTF = '/sys/class/gpio/gpio13/value'
FW = '/lib/firmware/silead/gslx680_fw.fw'
STATUS_OK = b'\x5a\x5a\x5a\x5a'


class Msg(ctypes.Structure):
    _fields_ = [('addr', ctypes.c_uint16), ('flags', ctypes.c_uint16),
                ('len', ctypes.c_uint16), ('buf', ctypes.POINTER(ctypes.c_uint8))]


class Req(ctypes.Structure):
    _fields_ = [('msgs', ctypes.POINTER(Msg)), ('nmsgs', ctypes.c_uint32)]


fd = os.open('/dev/i2c-1', os.O_RDWR)
fcntl.ioctl(fd, 0x0703, ADDR)


def xfer(specs):
    n = len(specs)
    arr = (Msg * n)()
    keep = []
    for i, (wr_, d) in enumerate(specs):
        if wr_:
            ln = len(d)
            buf = (ctypes.c_uint8 * ln)(*d)
        else:
            ln = d
            buf = (ctypes.c_uint8 * ln)()
        keep.append(buf)
        arr[i].addr = ADDR
        arr[i].flags = 0 if wr_ else 1
        arr[i].len = ln
        arr[i].buf = buf
    fcntl.ioctl(fd, 0x0707, Req(ctypes.cast(arr, ctypes.POINTER(Msg)), n))
    return [bytes(b)[:len(d)] if w else bytes(b) for (w, d), b in zip(specs, keep)]


def w(reg, data=b''):
    xfer([(1, bytes([reg & 0xff]) + bytes(data))])


def rd_rs(reg, n):
    return xfer([(1, bytes([reg & 0xff])), (0, n)])[1]


def rd_sp(reg, n):
    xfer([(1, bytes([reg & 0xff]))])
    return xfer([(0, n)])[0]


def rdb(reg, n):
    for fn in (rd_sp, rd_rs):
        try:
            return fn(reg, n)
        except OSError:
            pass
    return None


def power(v):
    with open(GPIO, 'w') as f:
        f.write('1' if v else '0')


def intval():
    try:
        return open(INTF).read().strip()
    except OSError:
        return '?'


def probe_f0(tag):
    try:
        rd_sp(0xF0, 1)
        return True
    except OSError as e:
        print('   [%s] 0xF0 探测失败: errno %d' % (tag, e.errno))
        return False


def reset_chip():
    w(0xE0, b'\x88'); time.sleep(0.020)
    w(0xE4, b'\x04'); time.sleep(0.010)
    w(0xBC, b'\x00\x00\x00\x00'); time.sleep(0.010)


def startup_chip():
    w(0xE0, b'\x00'); time.sleep(0.010)


def download(recs):
    buf = bytearray(129)
    cur = 1
    flag = 1
    n = 0
    for reg, val in recs:
        if reg == 0xF0:
            w(0xF0, struct.pack('<I', val))
            flag = 1
            cur = 1
        else:
            if flag % 32 == 1:
                buf[0] = reg & 0xff
                cur = 1
            buf[cur:cur + 4] = struct.pack('<I', val)
            cur += 4
            if flag % 32 == 0:
                w(buf[0], bytes(buf[1:cur]))
                n += 1
                cur = 1
            flag += 1
    return n


def init_chip(tag):
    print('   [%s] 复位脉冲 20ms@0 / 20ms@1' % tag)
    power(0); time.sleep(0.020)
    power(1); time.sleep(0.020)
    probe_f0(tag + ' probe1')
    time.sleep(0.0025)
    w(0xF0, b'\x12'); time.sleep(0.0025)
    probe_f0(tag + ' probe2')
    w(0xE0, b'\x88'); time.sleep(0.020)
    w(0x80, b'\x03'); time.sleep(0.005)
    w(0xE4, b'\x04'); time.sleep(0.005)
    w(0xE0, b'\x00'); time.sleep(0.020)
    reset_chip()
    t0 = time.time()
    nb = download(recs)
    startup_chip()
    reset_chip()
    startup_chip()
    time.sleep(0.030)
    print('   [%s] 下发 %d 组 / %.2fs' % (tag, nb, time.time() - t0))
    return rdb(0xB0, 4)


blob = open(FW, 'rb').read()
recs = [struct.unpack_from('<II', blob, i) for i in range(0, len(blob), 8)]
print('fw=%s  %d records  (期望 5247)' % (os.path.basename(FW), len(recs)))

try:
    open('/sys/bus/i2c/drivers/silead_ts/unbind', 'w').write('1-0040')
    print('driver unbound')
    time.sleep(0.3)
except OSError as e:
    print('unbind: %s' % e)
for g in (14, 13):
    try:
        open('/sys/class/gpio/export', 'w').write(str(g))
    except OSError:
        pass
time.sleep(0.1)
try:
    open('/sys/class/gpio/gpio14/direction', 'w').write('out')
    open('/sys/class/gpio/gpio13/direction', 'w').write('in')
except OSError as e:
    print('gpio dir: %s' % e)

power(1); time.sleep(0.2)
print('上电后 0xFC = %s' % (rdb(0xFC, 4) or b'').hex(' '))
print('上电后 0xB0 = %s' % (rdb(0xB0, 4) or b'').hex(' '))

st = None
for attempt in (1, 2):
    print('\n== 尝试 %d' % attempt)
    st = init_chip('try%d' % attempt)
    s = st.hex(' ') if st else 'READ FAIL'
    print('   0xB0 = %s   %s' % (s, '<<<<< 固件已启动 5a5a5a5a !' if st == STATUS_OK else ''))
    if st == STATUS_OK:
        break

print('\n最终 0xFC = %s' % (rdb(0xFC, 4) or b'').hex(' '))

if st == STATUS_OK:
    print('\n*** 现在用一根手指按住屏幕，保持 4 秒 ***')
    hit = 0
    for i in range(28):
        v = rdb(0x80, 8)
        if v is None:
            print('   NAK')
        else:
            nr = v[0]
            if nr:
                hit += 1
            print('   nr=%02X data=%s irq=%s %s' % (
                nr, v.hex(' '), intval(), '  <<<<< TOUCH!' if nr else ''))
        time.sleep(0.15)
    print('\n有触点的采样数 = %d' % hit)
else:
    print('\n固件状态仍不是 5a5a5a5a，跳过触摸测试')
    print('0xE0=%s  0xBC=%s  0xF0=%s  0x80=%s' % (
        (rdb(0xE0, 4) or b'').hex(' '), (rdb(0xBC, 4) or b'').hex(' '),
        (rdb(0xF0, 4) or b'').hex(' '), (rdb(0x80, 8) or b'').hex(' ')))

print('\n-- restoring driver')
for g in (14, 13):
    try:
        open('/sys/class/gpio/unexport', 'w').write(str(g))
    except OSError:
        pass
time.sleep(0.2)
try:
    open('/sys/bus/i2c/drivers/silead_ts/bind', 'w').write('1-0040')
    print('driver rebound')
except OSError as e:
    print('bind: %s' % e)
