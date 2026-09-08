"""Fixed: CLEANALARM channel=0 for payload 34, channel=1 for payload 35."""
import socket, struct, time, threading, sys

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
    struct.pack_into('<I', f, 0x50, psize)
    struct.pack_into('<I', f, 0x54, MAGIC2)
    return bytes(f)

def recv_quiet(sock, timeout=2):
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

# Kill PCB
import subprocess
subprocess.run("taskkill /IM PCB_Client.exe /F", capture_output=True, shell=True)
time.sleep(8)

print("=" * 60)
print("FIXED: CLEANALARM with correct channel mapping")
print("=" * 60)

# Step 1: Port 3001 handshakes (keep open)
print("\n[1] 3001 login handshakes (keep open)")
c3001 = []
for flag in [1, 0]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect((CAM, 3001))
    s.sendall(make_3001_frame(0x65, flag, 1))
    recv_quiet(s, 0.3)
    c3001.append(s)
    time.sleep(0.01)

# Step 2: Port 3000 login (keep open)
print("[2] 3000 login (keep open)")
login_conns = []
for ch in [0, 1]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((CAM, 3000))
    s.sendall(make_3000_login(0xA8C00001, 0x0BB82002, ch, 40))
    time.sleep(0.02)
    s.sendall(PWD_PAYLOAD)
    resp = recv_quiet(s, 2)
    cmd = struct.unpack_from('<I', resp, 0x1C)[0] if len(resp) >= 0x20 else 0
    print("  ch=%d -> cmd=0x%08X resp_len=%d" % (ch, cmd, len(resp)))
    login_conns.append(s)
    time.sleep(0.01)

# Step 3: Port 3001 config (keep open)
print("[3] 3001 config (keep open)")
cfg_conns = []
for chan, val in [(4, 0x35), (2, 0x34)]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect((CAM, 3001))
    s.sendall(make_3001_frame(0x00010078, 1, 16))
    recv_quiet(s, 0.3)
    s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
    resp = recv_quiet(s, 0.5)
    print("  cfg chan=%d val=0x%02X -> resp_len=%d" % (chan, val, len(resp)))
    cfg_conns.append(s)

# Step 4: CLEANALARM video start
print("[4] CLEANALARM (correct channels)")
# Channel 0 -> payload 0x34, Channel 1 -> payload 0x35
video_conns = []
for ch, pl in [(0, b"\x34\x00\x00\x00\x01\x00\x00\x00"), (1, b"\x35\x00\x00\x00\x01\x00\x00\x00")]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((CAM, 3000))
    s.sendall(make_3000_control(0xCCCC0002, ch, 8))  # ch=0 for 0x34, ch=1 for 0x35
    time.sleep(0.02)
    s.sendall(pl)
    resp = recv_quiet(s, 2)
    cmd = struct.unpack_from('<I', resp, 0x1C)[0] if len(resp) >= 0x20 else 0
    print("  ch=%d payload=%s -> cmd=0x%08X resp_len=%d" % (ch, pl.hex(), cmd, len(resp)))
    video_conns.append((s, ch))

# Step 5: cmd 0x14 on login conns
print("[5] cmd 0x14 on login conns")
for i, s in enumerate(login_conns):
    try:
        s.sendall(make_3000_control(0xCCCC0014, i, 0))
        resp = recv_quiet(s, 1)
        print("  login[%d] 0x14 -> %d bytes" % (i, len(resp)))
    except Exception as e:
        print("  login[%d] err: %s" % (i, e))

# Step 6: Read video
print("\n[6] Reading video 15s...")
bufs = [bytearray(), bytearray()]
threads = []
for i, (s, ch) in enumerate(video_conns):
    def reader(sock=s, idx=i):
        try:
            while True:
                c = sock.recv(65536)
                if not c: break
                bufs[idx] += c
        except: pass
    t = threading.Thread(target=reader)
    t.start()
    threads.append(t)

time.sleep(15)

for i, (s, ch) in enumerate(video_conns):
    sz = len(bufs[i])
    print("  ch%d: %d bytes" % (ch, sz))
    if sz > 0:
        print("    head: %s" % bufs[i][:64].hex())
        print("    ascii: %s" % ''.join(chr(b) if 32<=b<127 else '.' for b in bufs[i][:64]))
        fn = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_ch%d.bin" % ch
        with open(fn, 'wb') as f:
            f.write(bytes(bufs[i]))
        print("    saved: %s" % fn)

# Cleanup
for s in video_conns:
    try: s[0].close()
    except: pass
for s in login_conns + cfg_conns + c3001:
    try: s.close()
    except: pass
print("\nDONE")
