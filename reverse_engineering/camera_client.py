"""Complete camera client - login + start video stream.

Based on captured wire data. Two channels: vis (camera/visual) and ir.
For vis: video on port 3000, uses cc-padding control frames.
"""
import socket, struct, time, threading, sys, os

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

# ============================================================
# Port 3000 LOGIN frame (confirmed working, cmd=0x00000001)
# ============================================================
def make_3000_login(cmd_word, unknown, channel, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x10] = b"video server"     # 12 bytes
    f[0x10:0x1C] = b"\x00" + b"\xcc"*11  # \0 + 11 CC = 12 bytes => 0x04..0x1B = 24 bytes
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

PWD_PAYLOAD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13  # 40B

# ============================================================
# Port 3000 CONTROL frame (CC padding) - for video start etc
# From capture #27/#31: cmd=0xCCCC0002, channel, ps, then payload
# ============================================================
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

def make_3000_control1(cmd_word, channel, ps, unk4=0xCCCCCCCC, srcport=0):
    """Like #27 but with srcport field (for commands that use it)."""
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x1C] = b"\xcc" * 24
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unk4)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

# ============================================================
# Port 3001 88B handshake frame
# ============================================================
def make_3001_handshake(req_code, flag):
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x11] = b"video server\x00"     # 13 bytes
    f[0x11:0x14] = b"\x00" * 3
    f[0x14:0x18] = b"8888"
    f[0x18:0x20] = b"\x00" * 8
    f[0x20:0x27] = b"888888\x00"
    f[0x27:0x30] = b"\x00" * 9
    f[0x30:0x37] = b"888888\x00"
    f[0x37:0x44] = b"\x00" * 13
    # request code at 0x44
    struct.pack_into('<I', f, 0x44, req_code)
    struct.pack_into('<I', f, 0x48, flag)
    # 0x50 = 0
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

def dump(name, data, limit=96):
    return "%s(%dB): %s%s" % (name, len(data), data[:limit].hex(), "..." if len(data) > limit else "")

print("=" * 70)
print("COMPLETE CAMERA CLIENT")
print("=" * 70)

# ============================================================
# Phase 1: Port 3001 handshakes (2 conns, req 0x65)
# ============================================================
print("\n[Phase 1] Port 3001 handshake (req 0x65, 2 conns)")
c3001 = []
for flag in [1, 0]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3001))
        h = make_3001_handshake(0x65, flag)
        s.sendall(h)
        r1 = recv_until_quiet(s, 0.5)
        print("  sent 88B flag=%d, ack=%s" % (flag, dump("ack", r1)))
        r2 = recv_until_quiet(s, 2)
        print("  resp: %s" % dump("r", r2))
        c3001.append(s)
    except Exception as e:
        print("  err: %s" % e)
    time.sleep(0.02)

# ============================================================
# Phase 2: Port 3000 LOGIN (2 conns, channel 0 and 1)
# ============================================================
print("\n[Phase 2] Port 3000 login (channel 0, 1)")
login_conns = []
for ch in [0, 1]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        hdr = make_3000_login(0xA8C00001, 0x0BB82002, ch, 40)
        s.sendall(hdr)
        time.sleep(0.03)
        s.sendall(PWD_PAYLOAD)
        resp = recv_until_quiet(s, 3)
        cmd = struct.unpack_from('<I', resp, 0x1C)[0] if len(resp) >= 0x20 else -1
        print("  ch=%d login resp cmd=0x%08X" % (ch, cmd))
        if cmd != 0x00000001:
            print("    FAILED login! Aborting.")
            sys.exit(1)
        login_conns.append(s)
    except Exception as e:
        print("  ch=%d login error: %s" % (ch, e))
        sys.exit(1)
    time.sleep(0.02)

print("  Login OK on both channels!")

# ============================================================
# Phase 3: Video start controls (CLEANALARM cmd=2)
# From capture: connection port 62565 (ch1 payload 0x35), port 62564 (ch0 payload 0x34)
# ============================================================
print("\n[Phase 3] Video start (CLEANALARM)")
video_conns = []
payloads = [b"\x34\x00\x00\x00\x01\x00\x00\x00", b"\x35\x00\x00\x00\x01\x00\x00\x00"]
for i, pl in enumerate(payloads):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        hdr = make_3000_control(0xCCCC0002, 0, 8)
        s.sendall(hdr)
        time.sleep(0.02)
        s.sendall(pl)
        resp = recv_until_quiet(s, 2)
        print("  video%c: sent cmd=2 payload=%s -> resp %s" % ("AB"[i], pl.hex(), dump("r", resp)))
        video_conns.append(s)
    except Exception as e:
        print("  video%c error: %s" % ("AB"[i], e))
    time.sleep(0.02)

# ============================================================
# Phase 4: Read video stream
# ============================================================
print("\n[Phase 4] Reading video stream (10s)...")
outfile = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/vis_stream.mpg"
out = open(outfile, 'wb')
start = time.time()
total = 0
try:
    while time.time() - start < 10:
        for s in video_conns:
            s.settimeout(0.5)
            try:
                c = s.recv(65536)
                if c:
                    out.write(c)
                    total += len(c)
            except socket.timeout:
                pass
            except:
                pass
except Exception as e:
    print("  read err: %s" % e)
out.close()
print("  Captured %d bytes -> %s" % (total, outfile))

# check first bytes
if total > 0:
    with open(outfile, 'rb') as f:
        head = f.read(64)
    print("  head: %s" % head.hex())
    if b"\x00\x00\x01\xb3" in open(outfile,'rb').read()[:len(open(outfile,'rb').read())]:
        print("  Contains MPEG1 start code")

for c in login_conns + video_conns:
    try: c.close()
    except: pass
print("\nDONE")
