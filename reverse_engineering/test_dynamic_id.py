"""Dynamic source-id test: use the login-reported source id for CLEANALARM.

Run on a FRESH camera. Reads the srcid from each login response payload
(XX 00 00 00 ff ff ff ff) and uses it as the CLEANALARM payload.
"""
import socket, struct, time, threading

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13


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


def login_get_id(ch):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3000))
    s.sendall(mklogin(ch)); time.sleep(0.02); s.sendall(PWD)
    r = rq(s, 3)
    ps = struct.unpack_from('<I', r, 0x28)[0] if len(r) >= 0x30 else 0
    pl = r[0x30:0x30+ps]
    srcid = pl[0] if len(pl) >= 4 else -1
    cw = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
    print("  login ch%d: cmd=0x%08X payload=%s -> srcid=0x%02X" % (ch, cw, pl.hex(), srcid))
    return s, srcid


print("Waiting 8s for camera boot settle...")
time.sleep(8)

print("Logins...")
l0, id0 = login_get_id(0)
l1, id1 = login_get_id(1)
time.sleep(0.3)

# CLEANALARM each channel with its OWN reported id
socks = []
for ch, srcid in [(0, id0), (1, id1)]:
    if srcid <= 0:
        print("  ch%d: no id, skipping" % ch)
        continue
    ca = socket.socket(); ca.settimeout(5); ca.connect((CAM, 3000))
    ca.sendall(mkctrl(0xCCCC0002, ch, 8)); time.sleep(0.05)
    ca.sendall(struct.pack('<II', srcid, 1))
    r = rq(ca, 3)
    cw = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x30 else -1
    print("  CA ch%d srcid=0x%02X -> cmd=0x%08X" % (ch, srcid, cw))
    if cw == 0x00000002:
        socks.append((ch, srcid, ca))
    time.sleep(0.3)

print("Reading 10s...")
results = {}
for ch, srcid, ca in socks:
    ca.settimeout(0.2)
    results[ch] = []
start = time.time()
readers = []
stop = threading.Event()
def reader(ca, ch):
    total = 0
    head = b''
    while not stop.is_set():
        try:
            ca.settimeout(0.2)
            c = ca.recv(65536)
            if c:
                if not head:
                    head = c[:48]
                total += len(c)
        except:
            pass
    results[ch].append((total, head))
for ch, srcid, ca in socks:
    readers.append(threading.Thread(target=reader, args=(ca, ch)))
    r = readers[-1]
    r.start()
time.sleep(10)
stop.set()
for r in readers:
    r.join()
for ch, srcid, ca in socks:
    total, head = results[ch][0]
    print("  ch%d srcid=0x%02X: %d bytes" % (ch, srcid, total))
    if head:
        print("    head:", head.hex())
        print("    ascii:", ''.join(chr(b) if 32 <= b < 127 else '.' for b in head))

for s in socks:
    try: s[2].close()
    except: pass
for s in (l0, l1):
    try: s.close()
    except: pass
print("DONE")