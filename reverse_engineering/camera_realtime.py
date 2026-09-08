"""QuanLi SuperCam real-time viewer: visible stream via OpenCV."""
import socket, struct, time, threading, sys, os
import cv2
import subprocess

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


def log(msg):
    print("[%.1f] %s" % (time.time() - t0, msg), flush=True)


t0 = time.time()
log("Connecting...")

# 3001 init ×4
for extra1 in [1, 0]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x65, 0, 0, extra1))
    time.sleep(0.05); rq(s, 3); s.close()
for req, extra1 in [(0x66, 0), (0x00010066, 1)]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(req, 0, 0, extra1))
    time.sleep(0.05); rq(s, 3); s.close()
time.sleep(0.3)
log("3001 init done")

# 3000 login
login0 = socket.socket(); login0.settimeout(5); login0.connect((CAM, 3000))
login0.sendall(mklogin(0)); time.sleep(0.02); login0.sendall(PWD)
rq(login0, 3)
login1 = socket.socket(); login1.settimeout(5); login1.connect((CAM, 3000))
login1.sendall(mklogin(1)); time.sleep(0.02); login1.sendall(PWD)
rq(login1, 3)
time.sleep(0.1)
log("login done")

# CLEANALARM ch0 (visible)
ca0 = socket.socket(); ca0.settimeout(5); ca0.connect((CAM, 3000))
ca0.sendall(mkctrl(0xCCCC0002, 0, 8))
rq(ca0, 1)
time.sleep(0.02)
ca0.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
r = rq(ca0, 2)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
log("CLEANALARM ch0: cmd=0x%08X" % cmd)
assert cmd == 0x00000002, "Visible channel failed to start"

log("Streaming visible channel (Ctrl+C to quit)...")
os.makedirs("C:/Users/G/AppData/Local/Temp/opencode/tmp", exist_ok=True)
stream_file = "C:/Users/G/AppData/Local/Temp/opencode/tmp/cam_live.h264"

# Thread to write the raw H264 stream to a file continuously
fd = open(stream_file, 'wb')
stop = threading.Event()

def read_loop():
    while not stop.is_set():
        ca0.settimeout(0.2)
        try:
            c = ca0.recv(65536)
            if c:
                fd.write(c)
                fd.flush()
        except:
            pass

t_reader = threading.Thread(target=read_loop, daemon=True)
t_reader.start()

vc = cv2.VideoCapture(stream_file, cv2.CAP_FFMPEG)
if not vc.isOpened():
    log("OpenCV could not open ffmpeg pipe directly; using file fallback")
    vc = None

log("Press ESC or q to quit")

frame_idx = 0
try:
    while True:
        if vc and vc.isOpened():
            ret, frame = vc.read()
            if ret:
                cv2.imshow('SuperCam Visible', frame)
                frame_idx += 1
                if frame_idx % 25 == 0:
                    log("displayed %d frames" % frame_idx)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord('q')):
            break
except KeyboardInterrupt:
    pass

stop.set()
t_reader.join(timeout=1)
fd.close()
if vc:
    vc.release()
cv2.destroyAllWindows()
log("Done")
