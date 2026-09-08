"""proto.py - byte-exact SuperCam wire protocol builders (ported from pcb_client.py rev 5).

All frames are verified verbatim against the vendor MITM captures
(reverse_engineering_NOTES.md Addenda 6-7). Pure stdlib, cross-platform.
"""
import socket
import struct

MAGIC1 = struct.pack('<I', 0x123AB678)
MAGIC2 = struct.pack('<I', 0x876CD321)
USER = b'video server'
PWD_PAYLOAD = b'888888\x00' + b'\xcc' * 13 + b'888888\x00' + b'\xcc' * 13   # 40 bytes
LOGIN_1C = bytes.fromhex('01007f00')
PORT_WORD = bytes.fromhex('0001b80b')   # 0x0BB8 = 3000


def mk3001(req, flag, extra1, psize, payload=b''):
    h = bytearray(0x58)
    h[0:4] = MAGIC1
    h[4:16] = USER
    h[0x10:0x1C] = b'\x00' * 12
    h[0x1C:0x20] = b'8888'
    h[0x20:0x22] = b'88'
    h[0x22:0x30] = b'\x00' * 14
    h[0x30:0x36] = b'888888'
    h[0x36:0x40] = b'\x00' * 10
    h[0x40:0x44] = b'\x00' * 4
    h[0x44:0x48] = struct.pack('<I', req)
    h[0x48:0x4C] = struct.pack('<I', flag)
    h[0x4C:0x50] = struct.pack('<I', extra1)
    h[0x50:0x54] = struct.pack('<I', psize)
    h[0x54:0x58] = MAGIC2
    return bytes(h) + payload


def mk_login(channel):
    f = bytearray(0x30)
    f[0:4] = MAGIC1
    f[4:0x1C] = USER + b'\x00' * 10
    f[0x10] = 0x00
    f[0x11:0x1C] = b'\xcc' * 11
    f[0x1C:0x20] = LOGIN_1C
    f[0x20:0x24] = PORT_WORD
    f[0x24:0x28] = struct.pack('<I', channel)
    f[0x28:0x2C] = struct.pack('<I', 40)
    f[0x2C:0x30] = MAGIC2
    return bytes(f) + PWD_PAYLOAD


def mk_ca(channel_byte, sid):
    """CLEANALARM 56B. channel_byte: 1 = IR engine, 0 = VIS engine."""
    f = bytearray(0x30)
    f[0:4] = MAGIC1
    f[4:0x1C] = b'\xcc' * 24
    f[0x1C:0x1E] = b'\x02\x00'
    f[0x1E:0x24] = b'\xcc' * 6
    f[0x24:0x28] = struct.pack('<I', channel_byte)
    f[0x28:0x2C] = struct.pack('<I', 8)
    f[0x2C:0x30] = MAGIC2
    return bytes(f) + struct.pack('<II', sid, 1)


def mk_keepalive(channel):
    f = bytearray(0x30)
    f[0:4] = MAGIC1
    f[4:0x1C] = b'\xcc' * 24
    f[0x1C:0x1E] = b'\x14\x00'
    f[0x1E:0x24] = b'\xcc' * 6
    f[0x24:0x28] = struct.pack('<I', channel)
    f[0x28:0x2C] = struct.pack('<I', 0)
    f[0x2C:0x30] = MAGIC2
    return bytes(f)


def connect(host, port, timeout=6):
    s = socket.create_connection((host, port), timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s


def recv_exact(s, n, label='', timeout=8):
    s.settimeout(timeout)
    buf = b''
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise IOError('%s: closed (%d/%d)' % (label, len(buf), n))
        buf += chunk
    return buf


def recv_frame(s, label='', timeout=8, layout='30'):
    """'30' -> 3000-style (0x30 hdr, psize@0x28); '58' -> 3001 (0x58 hdr, psize@0x50)."""
    hl = 0x58 if layout == '58' else 0x30
    po = 0x50 if layout == '58' else 0x28
    hdr = recv_exact(s, hl, label, timeout)
    if hdr[:4] != MAGIC1:
        raise IOError('%s: bad magic %s' % (label, hdr[:4].hex()))
    psize = struct.unpack('<I', hdr[po:po + 4])[0]
    body = recv_exact(s, psize, label, timeout) if psize else b''
    return hdr, body


def request(host, port, frame, label=''):
    s = connect(host, port)
    s.sendall(frame)
    hdr, body = recv_frame(s, label, layout=('58' if port == 3001 else '30'))
    s.close()
    return body


def config_req(host, chan, sid):
    """0x78 CONFIG bind. chan 4 + extra1=1 -> IR RAW; chan 2 + extra1=0 -> VIS H.264."""
    extra1 = 1 if chan == 4 else 0
    return request(host, 3001, mk3001(0x00010078, 0, extra1, 16,
                                      struct.pack('<IIII', 3, chan, sid, 3000)),
                   '0x78 ch%d' % chan)