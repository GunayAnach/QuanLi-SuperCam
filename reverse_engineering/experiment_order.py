"""Experiment matrix to find what makes CLEANALARM return 0x00000002 instead of 0xFF9B0002."""
import socket, struct, time, sys

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
    except:
        pass
    return d


def do_login(ch):
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3000))
    s.sendall(mklogin(ch)); time.sleep(0.02); s.sendall(PWD)
    r = rq(s, 3)
    cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
    return s, cmd


def do_ca(ch, pay, verbose=False):
    ca = socket.socket(); ca.settimeout(5); ca.connect((CAM, 3000))
    ca.sendall(mkctrl(0xCCCC0002, ch, 8))
    ack1 = rq(ca, 2)
    time.sleep(0.05)
    ca.sendall(pay)
    ack2 = rq(ca, 2)
    r = rq(ca, 3)
    cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
    if verbose:
        print("    ca ch%d: ack1=%d ack2=%d response=%d cmd=0x%08X" %
              (ch, len(ack1), len(ack2), len(r), cmd))
    return ca, cmd


def variant_3001_config_first():
    print("VARIANT C: 3001 config SET first, then login+CLEANALARM")
    for chan, val, extra1 in [(4, 0x35, 1), (2, 0x34, 0)]:
        s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
        s.sendall(mk3001(0x00010078, 0, 16, extra1))
        rq(s, 3); time.sleep(0.05)
        s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
        r = rq(s, 3)
        print("  config chan%d/0x%02X: %d bytes" % (chan, val, len(r)))
        s.close(); time.sleep(0.05)
    time.sleep(0.3)
    l0, c0 = do_login(0)
    l1, c1 = do_login(1)
    print("  login ch0=0x%08X ch1=0x%08X" % (c0, c1))
    ca1, r1 = do_ca(1, b"\x35\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    ca0, r0 = do_ca(0, b"\x34\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    print("  RESULT: ch1=0x%08X ch0=0x%08X" % (r1, r0))
    for s in (l0, l1, ca1, ca0):
        try: s.close()
        except: pass


def variant_no_init():
    print("VARIANT A: login + CLEANALARM only (no 3001 inits)")
    l0, c0 = do_login(0)
    l1, c1 = do_login(1)
    print("  login ch0=0x%08X ch1=0x%08X" % (c0, c1))
    ca1, r1 = do_ca(1, b"\x35\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    ca0, r0 = do_ca(0, b"\x34\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    print("  RESULT: ch1=0x%08X ch0=0x%08X" % (r1, r0))
    for s in (l0, l1, ca1, ca0):
        try: s.close()
        except: pass


def variant_inits_then_login_ca():
    print("VARIANT B: 3001 inits, then login+CLEANALARM (reference)")
    for extra1 in [1, 0]:
        s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
        s.sendall(mk3001(0x65, 0, 0, extra1)); time.sleep(0.2); rq(s, 3); s.close(); time.sleep(0.3)
    for req, extra1 in [(0x66, 0), (0x00010066, 1)]:
        s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
        s.sendall(mk3001(req, 0, 0, extra1)); time.sleep(0.2); rq(s, 3); s.close(); time.sleep(0.3)
    time.sleep(0.5)
    l0, c0 = do_login(0)
    l1, c1 = do_login(1)
    print("  login ch0=0x%08X ch1=0x%08X" % (c0, c1))
    ca1, r1 = do_ca(1, b"\x35\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    ca0, r0 = do_ca(0, b"\x34\x00\x00\x00\x01\x00\x00\x00", verbose=True)
    print("  RESULT: ch1=0x%08X ch0=0x%08X" % (r1, r0))
    for s in (l0, l1, ca1, ca0):
        try: s.close()
        except: pass


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    time.sleep(2)
    if which in ("a", "all"):
        variant_no_init()
        time.sleep(1)
    if which in ("b", "all"):
        variant_inits_then_login_ca()
        time.sleep(1)
    if which in ("c", "all"):
        variant_3001_config_first()