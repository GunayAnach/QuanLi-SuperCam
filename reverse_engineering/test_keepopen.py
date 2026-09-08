"""Test: keep 3001 init connections OPEN while doing CLEANALARM (capture ports stayed open)."""
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


print("[1] opening 4x 3001 init connections and keeping them OPEN...")
inits = []
for req, extra1 in [(0x65, 1), (0x65, 0), (0x66, 0), (0x00010066, 1)]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(req, 0, 0, extra1))
    r = rq(s, 3)
    print("    init req=0x%08X extra1=%d: %d bytes (conn kept open)" % (req, extra1, len(r)))
    inits.append(s)

print("[2] logins...")
l0 = socket.socket(); l0.settimeout(5); l0.connect((CAM, 3000))
l0.sendall(mklogin(0)); time.sleep(0.02); l0.sendall(PWD)
r = rq(l0, 3)
print("    ch0 login: 0x%08X" % (struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1))
l1 = socket.socket(); l1.settimeout(5); l1.connect((CAM, 3000))
l1.sendall(mklogin(1)); time.sleep(0.02); l1.sendall(PWD)
r = rq(l1, 3)
print("    ch1 login: 0x%08X" % (struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1))

print("[3] CLEANALARM ch1 FIRST (capture order)...")
ca1 = socket.socket(); ca1.settimeout(5); ca1.connect((CAM, 3000))
ca1.sendall(mkctrl(0xCCCC0002, 1, 8))
time.sleep(0.05)
ca1.sendall(b"\x35\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca1, 3)
cmdc = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("    ch1: cmd=0x%08X (%d bytes)" % (cmdc, len(r)))

print("[4] CLEANALARM ch0...")
ca0 = socket.socket(); ca0.settimeout(5); ca0.connect((CAM, 3000))
ca0.sendall(mkctrl(0xCCCC0002, 0, 8))
time.sleep(0.05)
ca0.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca0, 3)
cmdc0 = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("    ch0: cmd=0x%08X (%d bytes)" % (cmdc0, len(r)))

print("[5] reading both 8s while inits stay open...")
start = time.time(); t0 = t1 = 0
while time.time() - start < 8:
    for sock, tag in [(ca0, "vis"), (ca1, "ir")]:
        sock.settimeout(0.15)
        try:
            c = sock.recv(65536)
            if c:
                if tag == "vis":
                    t0 += len(c)
                else:
                    t1 += len(c)
        except:
            pass
print("RESULT visible=%d B, ir=%d B" % (t0, t1))

for s in inits + [l0, l1, ca0, ca1]:
    try:
        s.close()
    except:
        pass