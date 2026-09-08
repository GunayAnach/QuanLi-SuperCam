"""EXACT capture sequence replication with fixed 3001 frames."""
import socket, struct, time, re

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13

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
            if not c: break
            d += c
    except: pass
    return d

def show_hex(data, maxlen=64):
    if not data: return '(empty)'
    return data[:maxlen].hex()

# Wait for camera to settle
print("Waiting 45s for camera to settle...")
time.sleep(45)

print("=" * 60)
print("EXACT CAPTURE SEQUENCE")
print("=" * 60)

# Phase 1: 3001 init req=0x65 (2 connections)
print("\n[1] 3001 init req=0x65")
init_conns = []
for i, extra1 in enumerate([1, 0]):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x65, 0, 0, extra1))
    time.sleep(0.05)
    r = rq(s, 3.0)
    print("  #%d extra1=%d: %d bytes" % (i, extra1, len(r)))
    if r: print("    %s" % show_hex(r))
    init_conns.append(s)

# Phase 2: 3001 init req=0x66 (2 connections)
print("\n[2] 3001 init req=0x66")
for i, (req, extra1) in enumerate([(0x66, 0), (0x00010066, 1)]):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(req, 0, 0, extra1))
    time.sleep(0.05)
    r = rq(s, 3.0)
    print("  #%d req=0x%08X extra1=%d: %d bytes" % (i, req, extra1, len(r)))
    if r: print("    %s" % show_hex(r))
    s.close()

# Close 3001 init conns for 0x65
for s in init_conns:
    try: s.close()
    except: pass
print("  (closed 3001 init connections)")
time.sleep(1)

# Phase 3: 3000 login (2 connections)
print("\n[3] 3000 login")
login0 = socket.socket(); login0.settimeout(5); login0.connect((CAM, 3000))
login0.sendall(mklogin(0)); time.sleep(0.02); login0.sendall(PWD)
r = rq(login0, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch0: %d bytes cmd=0x%08X" % (len(r), cmd))

login1 = socket.socket(); login1.settimeout(5); login1.connect((CAM, 3000))
login1.sendall(mklogin(1)); time.sleep(0.02); login1.sendall(PWD)
r = rq(login1, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch1: %d bytes cmd=0x%08X" % (len(r), cmd))
time.sleep(0.1)

# Phase 4: CLEANALARM on separate connections
print("\n[4] CLEANALARM")
# Connection for ch0 (34)
ca0 = socket.socket(); ca0.settimeout(5); ca0.connect((CAM, 3000))
ca0.sendall(mkctrl(0xCCCC0002, 0, 8))
r = rq(ca0, 1)
print("  ch0 header: %d bytes" % len(r))
time.sleep(0.02)
ca0.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca0, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch0 34: %d bytes cmd=0x%08X" % (len(r), cmd))

# Connection for ch1 (35)
ca1 = socket.socket(); ca1.settimeout(5); ca1.connect((CAM, 3000))
ca1.sendall(mkctrl(0xCCCC0002, 0, 8))
r = rq(ca1, 1)
print("  ch1 header: %d bytes" % len(r))
time.sleep(0.02)
ca1.sendall(b"\x35\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca1, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch1 35: %d bytes cmd=0x%08X" % (len(r), cmd))
time.sleep(0.1)

# Phase 5: 3001 config chan4/0x35
print("\n[5] 3001 config chan4/0x35")
s3001 = socket.socket(); s3001.settimeout(5); s3001.connect((CAM, 3001))
s3001.sendall(mk3001(0x00010078, 0, 16, 1))
r = rq(s3001, 3)
print("  handshake: %d bytes %s" % (len(r), show_hex(r)))
time.sleep(0.05)
s3001.sendall(struct.pack('<IIII', 3, 4, 0x35, 3000))
r = rq(s3001, 2)
print("  payload ack: %d bytes" % len(r))
time.sleep(0.05)
r = rq(s3001, 2)
print("  confirmation: %d bytes %s" % (len(r), show_hex(r)))
s3001.close()

# Phase 6: cmd 0x14 on login ch1
print("\n[6] cmd 0x14 on login ch1")
login1.sendall(mkctrl(0xCCCC0014, 1, 0))
r = rq(login1, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch1 0x14: %d bytes cmd=0x%08X" % (len(r), cmd))

# Phase 7: 3001 config chan2/0x34
print("\n[7] 3001 config chan2/0x34")
s3001 = socket.socket(); s3001.settimeout(5); s3001.connect((CAM, 3001))
s3001.sendall(mk3001(0x00010078, 0, 16, 0))
r = rq(s3001, 3)
print("  handshake: %d bytes %s" % (len(r), show_hex(r)))
time.sleep(0.05)
s3001.sendall(struct.pack('<IIII', 3, 2, 0x34, 3000))
r = rq(s3001, 2)
print("  payload ack: %d bytes" % len(r))
time.sleep(0.05)
r = rq(s3001, 2)
print("  confirmation: %d bytes %s" % (len(r), show_hex(r)))
s3001.close()

# Phase 8: cmd 0x14 on login ch0
print("\n[8] cmd 0x14 on login ch0")
login0.sendall(mkctrl(0xCCCC0014, 0, 0))
r = rq(login0, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch0 0x14: %d bytes cmd=0x%08X" % (len(r), cmd))

# Phase 9: 3001 req=0x90
print("\n[9] 3001 req=0x90")
s3001 = socket.socket(); s3001.settimeout(5); s3001.connect((CAM, 3001))
s3001.sendall(mk3001(0x90, 0, 0, 0))
r = rq(s3001, 3)
print("  0x90: %d bytes %s" % (len(r), show_hex(r)))
s3001.close()

# Phase 10: Read video on ca0 (ch0 CLEANALARM connection)
print("\n[10] Reading video 20s on ca0...")
buf = bytearray()
start = time.time()
last_report = 0
while time.time() - start < 20:
    ca0.settimeout(1)
    try:
        c = ca0.recv(65536)
        if c:
            buf += c
            t = time.time() - start
            if t - last_report >= 2 or len(buf) <= 256:
                print("  t=%.1f: +%d bytes (total %d)" % (t, len(c), len(buf)))
                last_report = t
    except: pass

print("\nTotal: %d bytes" % len(buf))
if buf:
    print("head: %s" % buf[:128].hex())
    with open("D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_exact.bin", 'wb') as f:
        f.write(bytes(buf))
    print("SAVED to stream_exact.bin")
else:
    print("NO VIDEO DATA")

for s in [login0, login1, ca0, ca1]:
    try: s.close()
    except: pass
print("DONE")
