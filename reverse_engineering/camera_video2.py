"""Complete faithful client - port 3001 config + port 3000 login + video."""
import socket, struct, time, sys, os

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321
PWD_PAYLOAD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13

def make_3000_login(cmd_word, unknown, channel, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x10] = b"video server"
    f[0x10:0x1C] = b"\x00" + b"\xcc"*11
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

def make_3000_control(cmd_word, channel, ps, unk4=0xCCCCCCCC):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x1C] = b"\xcc" * 24
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unk4)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

def make_3001_frame(req_code, flag, psize):
    """88B port 3001 frame. req_code at 0x44, psize at 0x50."""
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x11] = b"video server\x00"
    f[0x11:0x14] = b"\x00" * 3
    f[0x14:0x18] = b"8888"
    f[0x18:0x20] = b"\x00" * 8
    f[0x20:0x27] = b"888888\x00"
    f[0x27:0x30] = b"\x00" * 9
    f[0x30:0x37] = b"888888\x00"
    f[0x37:0x44] = b"\x00" * 13
    struct.pack_into('<I', f, 0x44, req_code)
    struct.pack_into('<I', f, 0x48, flag)
    struct.pack_into('<I', f, 0x4C, 0)
    struct.pack_into('<I', f, 0x50, psize)
    struct.pack_into('<I', f, 0x54, MAGIC2)
    return bytes(f)

def recv_until_quiet(sock, timeout=2):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            c = sock.recv(65536)
            if not c: break
            data += c
    except socket.timeout: pass
    except: pass
    return data

def dump(name, data, limit=48):
    return "%s(%dB): %s" % (name, len(data), data[:limit].hex())

print("=" * 60)
print("FULL FAITHFUL CLIENT")
print("=" * 60)

# ---- Port 3001 login handshake (req 0x65) ----
print("\n[1] Port 3001 login handshakes (req 0x65)")
for flag in [1, 0]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((CAM, 3001))
        s.sendall(make_3001_frame(0x65, flag, 1))
        recv_until_quiet(s, 0.5)
    except Exception as e:
        print("  err:", e)
    s.close()
    time.sleep(0.01)

# ---- Port 3000 login ----
print("\n[2] Port 3000 login")
login_conns = []
for ch in [0, 1]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        s.sendall(make_3000_login(0xA8C00001, 0x0BB82002, ch, 40))
        time.sleep(0.03)
        s.sendall(PWD_PAYLOAD)
        resp = recv_until_quiet(s, 3)
        cmd = struct.unpack_from('<I', resp, 0x1C)[0] if len(resp) >= 0x20 else -1
        print("  ch=%d login cmd=0x%08X" % (ch, cmd))
        login_conns.append(s)
    except Exception as e:
        print("  ch=%d err:", ch, e)
        s.close()
    time.sleep(0.02)

# ---- Port 3001 config (req 0x78) ----
print("\n[3] Port 3001 config (req 0x78)")
for chan, val in [(4, 0x35), (2, 0x34)]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((CAM, 3001))
        s.sendall(make_3001_frame(0x00010078, 1, 16))
        recv_until_quiet(s, 0.4)
        cfg = struct.pack('<IIII', 3, chan, val, 3000)
        s.sendall(cfg)
        resp = recv_until_quiet(s, 0.5)
        print("  cfg chan=%d val=0x%02X -> %s" % (chan, val, dump("resp", resp)))
    except Exception as e:
        print("  cfg chan=%d err: %s" % (chan, e))
    s.close()
    time.sleep(0.02)

# ---- Video start on fresh port 3000 conns ----
print("\n[4] Video start")
video_conns = {}
for pl in [b"\x34\x00\x00\x00\x01\x00\x00\x00", b"\x35\x00\x00\x00\x01\x00\x00\x00"]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        s.sendall(make_3000_control(0xCCCC0002, 0, 8))
        time.sleep(0.02)
        s.sendall(pl)
        resp = recv_until_quiet(s, 2)
        cmd = struct.unpack_from('<I', resp, 0x1C)[0] if len(resp) >= 0x20 else -1
        print("  payload=%s -> cmd=0x%08X" % (pl.hex(), cmd))
        video_conns[pl[0]] = s
    except Exception as e:
        print("  payload=%s err: %s" % (pl.hex(), e))
    time.sleep(0.02)

# ---- GetSerialNo / trigger (cmd 0x14) on login conns ----
print("\n[5] cmd 0x14 on login conns")
for s in login_conns:
    try:
        s.sendall(make_3000_control(0xCCCC0014, 0, 0))
        resp = recv_until_quiet(s, 2)
        print("  0x14 -> %s" % dump("r", resp))
    except Exception as e:
        print("  0x14 err:", e)

# ---- Read video ----
print("\n[6] Reading video 12s")
outfile = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/vis_stream.bin"
out = open(outfile, 'wb')
start = time.time()
total = 0
while time.time() - start < 12:
    for pl, s in video_conns.items():
        s.settimeout(0.4)
        try:
            c = s.recv(65536)
            if c:
                out.write(c)
                total += len(c)
        except socket.timeout: pass
        except: pass
out.close()
print("  captured %d bytes" % total)
with open(outfile, 'rb') as f:
    head = f.read(128)
print("  head: %s" % head.hex())
print("  ascii: %s" % ''.join(chr(b) if 32<=b<127 else '.' for b in head))

for s in video_conns.values():
    try: s.close()
    except: pass
for s in login_conns:
    try: s.close()
    except: pass
print("DONE")
