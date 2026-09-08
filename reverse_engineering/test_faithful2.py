"""Definitive faithful capture replication v2.

Runs the EXACT capture order (#1-#62) with correctly-built frames and keeps
all 3001 connections OPEN (as the vendor client did). Run ONCE on a freshly
power-cycled camera.
"""
import socket, struct, time

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


def rq(sock, t=3):
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


def rdloop(sock, label, dur):
    start = time.time()
    total = 0
    first = b''
    while time.time() - start < dur:
        sock.settimeout(0.15)
        try:
            c = sock.recv(65536)
            if c:
                if not first:
                    first = c[:32]
                total += len(c)
        except:
            pass
    print("      %s: %d bytes  head=%s" % (label, total, first.hex()))


OK = {}
socks = []

def open3001(req, flag, psize, extra1, tag):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(req, flag, psize, extra1))
    r = rq(s, 3)
    print("  [+] 3001 %-9s req=0x%08X extra1=%d: %dB response (kept open)" %
          (tag, req, extra1, len(r)))
    return s


print("=" * 66)
print("FAITHFUL v2 - exact capture order, all conns OPEN")
print("=" * 66)

# [#1-#16] 3001 init in / homeCameras kept open
A = open3001(0x65, 0, 0, 1, "init-1")
time.sleep(0.2)
B = open3001(0x65, 0, 0, 0, "init-2")
time.sleep(0.2)
C = open3001(0x66, 0, 0, 0, "init-3")
time.sleep(0.2)
D = open3001(0x00010066, 0, 0, 1, "init-4")
time.sleep(0.5)

# [#17-#26] 3000 login both channels (ch0 conn first, passwords)
print("[#17-26] login")
l0 = socket.socket(); l0.settimeout(5); l0.connect((CAM, 3000))
l0.sendall(mklogin(0)); time.sleep(0.02); l0.sendall(PWD)
r = rq(l0, 3)
print("  ch0 login: cmd=0x%08X (%dB)" % (struct.unpack_from('<I', r, 0x1C)[0], len(r)))
time.sleep(0.2)
l1 = socket.socket(); l1.settimeout(5); l1.connect((CAM, 3000))
l1.sendall(mklogin(1)); time.sleep(0.02); l1.sendall(PWD)
r = rq(l1, 3)
print("  ch1 login: cmd=0x%08X (%dB)" % (struct.unpack_from('<I', r, 0x1C)[0], len(r)))

# [#27-#36] CLEANALARM: ch1 first, then ch0
print("[#27-36] CLEANALARM")
ca1 = socket.socket(); ca1.settimeout(5); ca1.connect((CAM, 3000))
ca1.sendall(mkctrl(0xCCCC0002, 1, 8)); time.sleep(0.02)
ca1.sendall(b"\x35\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca1, 3)
print("  ch1 first: cmd=0x%08X (%dB)" % (struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1, len(r)))
time.sleep(0.2)
ca0 = socket.socket(); ca0.settimeout(5); ca0.connect((CAM, 3000))
ca0.sendall(mkctrl(0xCCCC0002, 0, 8)); time.sleep(0.02)
ca0.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca0, 3)
print("  ch0 second: cmd=0x%08X (%dB)" % (struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1, len(r)))

# [#37-#42] config IR
print("[#37-42] 3001 config chan4/0x35 extra1=1")
E = socket.socket(); E.settimeout(5); E.connect((CAM, 3001))
E.sendall(mk3001(0x00010078, 0, 16, 1))
r = rq(E, 3)
print("  handshake: %dB" % len(r))
time.sleep(0.05)
E.sendall(struct.pack('<IIII', 3, 4, 0x35, 3000))
r = rq(E, 3)
print("  config app: %dB  tail=%s" % (len(r), r[-16:].hex()))

# [#43-#47] raw 96B cmd
print("[#43-47] 3001 raw req=0x00006051")
F = socket.socket(); F.settimeout(5); F.connect((CAM, 3001))
F.sendall(mk3001(0x00006051, 0, 96, 1))
r = rq(F, 3)
print("  handshake: %dB" % len(r))
time.sleep(0.05)
raw96 = bytearray(96)
raw96[4] = 0x58
F.sendall(bytes(raw96))
r = rq(F, 3)
print("  raw app: %dB  tail=%s" % (len(r), r[-20:].hex()))

# [#48-#50] cmd 0x14 on login ch1
print("[#48] cmd 0x14 (login ch1)")
l1.sendall(mkctrl(0xCCCC0014, 1, 0))
r = rq(l1, 2)
print("  %dB" % len(r))

# [#51-#55] config visible
print("[#51-55] 3001 config chan2/0x34 extra1=0")
G = socket.socket(); G.settimeout(5); G.connect((CAM, 3001))
G.sendall(mk3001(0x00010078, 0, 16, 0))
r = rq(G, 3)
print("  handshake: %dB" % len(r))
time.sleep(0.05)
G.sendall(struct.pack('<IIII', 3, 2, 0x34, 3000))
r = rq(G, 3)
print("  config app: %dB  tail=%s" % (len(r), r[-16:].hex()))

# [#56-#57] cmd 0x14 on login ch0
print("[#56] cmd 0x14 (login ch0)")
l0.sendall(mkctrl(0xCCCC0014, 0, 0))
r = rq(l0, 2)
print("  %dB" % len(r))

# [#59-#61] 3001 req=0x90
print("[#59-61] 3001 req=0x90")
H = socket.socket(); H.settimeout(5); H.connect((CAM, 3001))
H.sendall(mk3001(0x90, 0, 0, 0))
r = rq(H, 3)
print("  %dB" % len(r))

# [#62+] read video
print("[#62+] read video 10s...")
import threading
buf = {'vis': bytearray(), 'ir': bytearray()}
def reader(sock, key):
    while time.time() - start_read < 10:
        try:
            sock.settimeout(0.1)
            c = sock.recv(65536)
            if c:
                buf[key] += c
        except:
            pass
start_read = time.time()
t1 = threading.Thread(target=reader, args=(ca0, 'vis')); t1.start()
t2 = threading.Thread(target=reader, args=(ca1, 'ir')); t2.start()
t1.join(); t2.join()
print("RESULT visible=%d bytes, ir=%d bytes" % (len(buf['vis']), len(buf['ir'])))
if buf['ir']:
    print("  IR head:", buf['ir'][:48].hex())

for s in [A, B, C, D, l0, l1, ca0, ca1, E, F, G, H]:
    try:
        s.close()
    except:
        pass
print("DONE")