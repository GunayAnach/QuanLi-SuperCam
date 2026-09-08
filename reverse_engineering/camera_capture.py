"""QuanLi SuperCam video capture tool (dynamic source-id).

Run IMMEDIATELY after a fresh power-cycle of the camera:
  python camera_capture.py [seconds]

Logs in both channels, reads the source-id from each login response, starts
CLEANALARM on both with MATCHED source ids, and captures raw streams to
stream_date/vis+ir files. Falls back to other ids if a channel yields no bytes.

Earlier verified: visible channel = H.264 Annex-B (00 00 01 b3 + LAUCHDIGITAL),
decodes to 1920x1080. IR channel (if it activates) = RAW 160x120 16-bit thermal.
"""
import socket, struct, time, sys, os, datetime

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13
OUT = os.path.dirname(os.path.abspath(__file__))


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


def rcvs(sock, t=3):
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
    if len(r) < 0x30:
        print("  login ch%d FAILED (%d bytes)" % (ch, len(r)))
        return None, None
    cw = struct.unpack_from('<I', r, 0x1C)[0]
    ps = struct.unpack_from('<I', r, 0x28)[0]
    pl = r[0x30:0x30+ps]
    srcid = pl[0] if len(pl) >= 4 else -1
    print("  login ch%d: cmd=0x%08X payload=%s srcid=0x%02X" % (ch, cw, pl.hex(), srcid))
    return s, srcid


def ca_start(ch, srcid):
    ca = socket.socket(); ca.settimeout(5); ca.connect((CAM, 3000))
    ca.sendall(mkctrl(0xCCCC0002, ch, 8)); time.sleep(0.03)
    ca.sendall(struct.pack('<II', srcid, 1))
    r = rq(ca, 3)
    cw = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x30 else -1
    print("  CA ch%d srcid=0x%02X -> cmd=0x%08X" % (ch, srcid, cw))
    return ca, cw == 0x00000002


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print("=" * 62)
    print("SuperCam capture - dynamic source id  (%.0fs)" % secs)
    print("=" * 62)

    l0, id0 = login_get_id(0)
    l1, id1 = login_get_id(1)
    if l0 is None or l1 is None:
        print("login(s) failed - camera not ready?")
        return
    time.sleep(0.3)

    # CLEANALARM per channel with its own matched id
    streams = []
    for ch, srcid in [(1, id1), (0, id0)]:  # ch1 first like the capture
        if srcid <= 0:
            print("  ch%d: no srcid, skip" % ch)
            continue
        ca, ok = ca_start(ch, srcid)
        if ok:
            streams.append((ch, srcid, ca))
        time.sleep(0.3)

    if not streams:
        print("no channels accepted; camera may need a power cycle")
        for s in (l0, l1):
            s.close()
        return

    # ---- config phase (proven-working viewer does this before reading) ----
    print("Config phase (3001)...")
    for extra1, chan, val in [(1, 4, 0x35), (0, 2, 0x34)]:
        s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
        s.sendall(mk3001(0x00010078, 0, 16, extra1))
        rcvs(s, 2); time.sleep(0.02)
        s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
        r2 = rcvs(s, 3)
        print("  config chan%d/0x%02X -> %d bytes" % (chan, val, len(r2)))
        s.close(); time.sleep(0.2)
    # cmd 0x14 keepalive on login conns
    for s, ch in [(l1, 1), (l0, 0)]:
        try:
            s.sendall(mkctrl(0xCCCC0014, ch, 0))
            rcvs(s, 2)
        except:
            pass
    time.sleep(0.3)

    # Fallback: if a channel yields no data after a few sec, try other ids
    starts = {ch: 0 for ch, _, _ in streams}
    discovered = dict(starts)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    files = {}
    print("Capturing for %ds..." % secs)
    start = time.time()
    last = start
    totals = {}

    while time.time() - start < secs:
        now = time.time()
        for ch, srcid, ca in list(streams):
            ca.settimeout(0.2)
            try:
                c = ca.recv(65536)
                if c:
                    if ch not in files:
                        kind = {0x35: "ir", 0x34: "vis"}.get(srcid, "src%02x" % srcid)
                        path = os.path.join(OUT, "stream_%s_%s.bin" % (kind, stamp))
                        files[ch] = open(path, "wb")
                        print("  ch%d (src 0x%02X => %s) -> %s" % (ch, srcid, kind, path))
                        discovered[ch] = srcid
                    files[ch].write(c)
                    totals[ch] = totals.get(ch, 0) + len(c)
            except:
                pass
        if now - last >= 3:
            last = now
            line = "  t=%.1f " % (now - start)
            for ch, srcid, ca in streams:
                got = totals.get(ch, 0)
                if got == 0 and now - start - starts[ch] > 3 and srcid < 0x40:
                    # try next source id
                    newid = srcid + 1
                    starts[ch] = now - start
                    try:
                        ca.sendall(struct.pack('<II', newid, 1))
                        print("    ch%d: no data w/ 0x%02X, trying 0x%02X" % (ch, srcid, newid))
                    except:
                        pass
                line += "ch%d=%d " % (ch, got)
            print(line, flush=True)

    for ch in files:
        files[ch].close()
        print("  saved ch%d: %.2f MB" % (ch, totals.get(ch, 0) / 1048576))
    for ch, srcid, ca in streams:
        try:
            ca.close()
        except:
            pass
    for s in (l0, l1):
        try:
            s.close()
        except:
            pass
    print("DONE")


if __name__ == "__main__":
    main()