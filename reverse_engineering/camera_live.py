"""QuanLi SuperCam real-time viewer (dynamic source-id).

Logs in both channels, reads each login's video-source id, starts CLEANALARM on
both with matched ids, and pipes whichever channel produces H.264 into ffmpeg ->
OpenCV for live display. Works across camera units where the visible stream may
arrive on ch0 or ch1 (source value 0x34 = visible, 0x35 = IR on the capture unit).

Requires a healthy (freshly power-cycled) camera. Press ESC / q to quit.
"""
import socket, struct, time, threading, subprocess, os, sys

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
    print(msg, flush=True)


def login_get_id(ch):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3000))
    s.sendall(mklogin(ch)); time.sleep(0.02); s.sendall(PWD)
    r = rq(s, 3)
    if len(r) < 0x30:
        log("[login] ch%d FAILED (%d bytes)" % (ch, len(r)))
        return None, None
    cw = struct.unpack_from('<I', r, 0x1C)[0]
    ps = struct.unpack_from('<I', r, 0x28)[0]
    pl = r[0x30:0x30 + ps]
    srcid = pl[0] if len(pl) >= 4 else -1
    log("[login] ch%d cmd=0x%08X srcid=0x%02X" % (ch, cw, srcid))
    return s, srcid


def ca_start(ch, srcid):
    ca = socket.socket(); ca.settimeout(5); ca.connect((CAM, 3000))
    ca.sendall(mkctrl(0xCCCC0002, ch, 8)); time.sleep(0.02)
    ca.sendall(struct.pack('<II', srcid, 1))
    r = rq(ca, 3)
    cw = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x30 else -1
    log("[cleanalarm] ch%d srcid=0x%02X cmd=0x%08X" % (ch, srcid, cw))
    return ca, cw == 0x00000002


def main():
    import cv2
    import numpy as np

    l0, id0 = login_get_id(0)
    l1, id1 = login_get_id(1)
    if l0 is None or l1 is None:
        log("login(s) failed - camera not ready")
        return
    time.sleep(0.3)

    conns = []
    for ch, srcid in [(0, id0), (1, id1)]:
        if srcid <= 0:
            continue
        ca, ok = ca_start(ch, srcid)
        if ok:
            conns.append(ca)
        time.sleep(0.2)

    if not conns:
        log("no channel accepted - power-cycle the camera and retry")
        return

    # config phase (visible config = the active stream)
    for extra1, chan, val in [(1, 4, 0x35), (0, 2, 0x34)]:
        s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
        s.sendall(mk3001(0x00010078, 0, 16, extra1))
        rq(s, 2); time.sleep(0.02)
        s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
        rq(s, 3)
        s.close(); time.sleep(0.2)
    for s, ch in [(l1, 1), (l0, 0)]:
        try:
            s.sendall(mkctrl(0xCCCC0014, ch, 0)); rq(s, 2)
        except:
            pass
    time.sleep(0.3)

    log("[stream] launching ffmpeg decoder (raw BGR pipe)...")
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "h264", "-i", "pipe:0",
        "-an", "-vf", "scale=1280:720",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, bufsize=0)

    stop = threading.Event()
    totals = {id(c): [0] for c in conns}

    def read_and_feed():
        while not stop.is_set():
            for c in conns:
                c.settimeout(0.3)
                try:
                    chunk = c.recv(65536)
                    if chunk:
                        totals[id(c)][0] += len(chunk)
                        try:
                            proc.stdin.write(chunk)
                            proc.stdin.flush()
                        except BrokenPipeError:
                            return
                except:
                    pass

    threading.Thread(target=read_and_feed, daemon=True).start()

    FRAME_SIZE = 1280 * 720 * 3
    fbuf = bytearray()
    displayed = 0
    log("[stream] LIVE - ESC/q to quit")
    try:
        while not stop.is_set():
            if proc.poll() is not None:
                err = proc.stderr.read().decode(errors='ignore')
                log("[stream] ffmpeg exited: %s" % err[-400:])
                break
            chunk = proc.stdout.read(FRAME_SIZE * 2)
            if not chunk:
                time.sleep(0.02)
                continue
            fbuf += chunk
            while len(fbuf) >= FRAME_SIZE:
                img = np.frombuffer(bytes(fbuf[:FRAME_SIZE]), dtype=np.uint8).reshape(720, 1280, 3)
                del fbuf[:FRAME_SIZE]
                cv2.imshow("SuperCam Visible (live)", img)
                displayed += 1
                if cv2.waitKey(1) & 0xFF in (27, ord('q')):
                    stop.set()
                    break
    except KeyboardInterrupt:
        pass

    stop.set()
    try:
        proc.terminate()
    except:
        pass
    for c in conns:
        try:
            c.close()
        except:
            pass
    for s in (l0, l1):
        try:
            s.close()
        except:
            pass
    cv2.destroyAllWindows()
    log("[done] displayed %d frames, bytes/ch: %s" % (displayed, [t[0] for t in totals.values()]))


if __name__ == "__main__":
    main()