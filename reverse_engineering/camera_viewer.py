"""
QuanLi SuperCam Real-Time Video Client
- Logs in to camera
- Starts video stream on both channels
- Saves raw H.264 stream
"""
import socket, struct, time, sys, os

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def mk3001(req, flag, psize, extra1=0):
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x11] = b"video server\x00"
    f[0x1C:0x22] = b"888888"
    f[0x30:0x36] = b"888888"
    struct.pack_into('<I', f, 0x44, req)
    struct.pack_into('<I', f, 0x48, flag)
    struct.pack_into('<I', f, 0x4C, extra1)
    struct.pack_into('<I', f, 0x50, psize)
    struct.pack_into('<I', f, 0x54, M2)
    return bytes(f)


def mklogin(ch):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x10] = b"video server"
    f[0x10:0x1C] = b"\x00" + b"\xcc"*11
    struct.pack_into('<I', f, 0x1C, 0xA8C00001)
    struct.pack_into('<I', f, 0x20, 0x0BB82002)
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, 40)
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f)


def mkctrl(cw, ch, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x1C] = b"\xcc"*24
    struct.pack_into('<I', f, 0x1C, cw)
    struct.pack_into('<I', f, 0x20, 0xCCCCCCCC)
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f)


def rq(sock, t=2):
    sock.settimeout(t)
    d = b''
    try:
        while True:
            c = sock.recv(65536)
            if not c:
                break
            d += c
    except:
        pass
    return d


def log(msg):
    print("[%.1f] %s" % (time.time() - t0, msg), flush=True)


t0 = time.time()

log("Connecting to %s..." % CAM)

# Phase 1: 3001 init req=0x65 (2 connections)
log("3001 init req=0x65")
for extra1 in [1, 0]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x65, 0, 0, extra1))
    time.sleep(0.05)
    r = rq(s, 3.0)
    log("  extra1=%d: %d bytes" % (extra1, len(r)))
    s.close()

# Phase 2: 3001 init req=0x66 (2 connections)
log("3001 init req=0x66")
for req, extra1 in [(0x66, 0), (0x00010066, 1)]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(req, 0, 0, extra1))
    time.sleep(0.05)
    r = rq(s, 3.0)
    log("  req=0x%08X: %d bytes" % (req, len(r)))
    s.close()

time.sleep(0.5)

# Phase 3: 3000 login
log("3000 login")
login0 = socket.socket(); login0.settimeout(5); login0.connect((CAM, 3000))
login0.sendall(mklogin(0)); time.sleep(0.02); login0.sendall(PWD)
r = rq(login0, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
log("  ch0: cmd=0x%08X" % cmd)

login1 = socket.socket(); login1.settimeout(5); login1.connect((CAM, 3000))
login1.sendall(mklogin(1)); time.sleep(0.02); login1.sendall(PWD)
r = rq(login1, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
log("  ch1: cmd=0x%08X" % cmd)
time.sleep(0.1)

# Phase 4: CLEANALARM
log("CLEANALARM")
ca1 = socket.socket(); ca1.settimeout(5); ca1.connect((CAM, 3000))
ca1.sendall(mkctrl(0xCCCC0002, 1, 8))
rq(ca1, 1)
time.sleep(0.02)
ca1.sendall(b"\x35\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca1, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
log("  ch1 (35): cmd=0x%08X" % cmd)

ca0 = socket.socket(); ca0.settimeout(5); ca0.connect((CAM, 3000))
ca0.sendall(mkctrl(0xCCCC0002, 0, 8))
rq(ca0, 1)
time.sleep(0.02)
ca0.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca0, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
log("  ch0 (34): cmd=0x%08X" % cmd)
time.sleep(0.1)

# Phase 5: 3001 config
log("3001 config")
for chan, val, extra1 in [(4, 0x35, 1), (2, 0x34, 0)]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x00010078, 0, 16, extra1))
    rq(s, 3)
    time.sleep(0.05)
    s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
    r = rq(s, 3)
    log("  chan%d/0x%02X: %d bytes" % (chan, val, len(r)))
    s.close()
    time.sleep(0.05)

# Phase 6: cmd 0x14 keepalive on login connections
log("cmd 0x14")
login1.sendall(mkctrl(0xCCCC0014, 1, 0))
r = rq(login1, 2)
log("  ch1: %d bytes" % len(r))

# Phase 7: 3001 req=0x90
log("3001 final handshake")
s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
s.sendall(mk3001(0x90, 0, 0, 0))
r = rq(s, 3)
log("  0x90: %d bytes" % len(r))
s.close()

# Phase 8: Read video
log("Reading video (30s)...")
streams = {
    'visible': {'sock': ca0, 'file': None, 'buf': bytearray()},
    'ir':      {'sock': ca1, 'file': None, 'buf': bytearray()},
}

for name in streams:
    path = os.path.join(OUT_DIR, 'stream_%s.h264' % name)
    streams[name]['file'] = open(path, 'wb')

start = time.time()
last_report = start
total_bytes = {k: 0 for k in streams}

try:
    while time.time() - start < 30:
        now = time.time()
        for name, info in streams.items():
            info['sock'].settimeout(0.1)
            try:
                c = info['sock'].recv(65536)
                if c:
                    info['file'].write(c)
                    total_bytes[name] += len(c)
            except:
                pass

        if now - last_report >= 3:
            elapsed = now - start
            for name in streams:
                log("  t=%.1f %s: %.1f KB" % (elapsed, name, total_bytes[name] / 1024))
            last_report = now
except KeyboardInterrupt:
    log("Interrupted")

for name in streams:
    streams[name]['file'].close()
    log("%s: saved %s (%.1f MB)" % (name, streams[name]['file'].name, total_bytes[name] / 1024 / 1024))

for s in [login0, login1, ca0, ca1]:
    try:
        s.close()
    except:
        pass

log("Done")
log("Total: visible=%.1f MB, ir=%.1f MB" % (total_bytes['visible']/1024/1024, total_bytes['ir']/1024/1024))
