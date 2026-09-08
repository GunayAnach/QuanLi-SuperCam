"""pcb_client.py - definitive QuanLi/LangChi SuperCam mirror-client (rev 2).

Replicates the EXACT vendor (PCB_Client.exe) session decoded from the relay MITM
capture (reverse_engineering_NOTES.md Addendum 6), but tolerant of the camera's
per-boot slot quirks:

  0) 3001 0x65(0), 0x65(1)         -> "Neptune" (152B on wire; 64B body)
  1) 3001 0x66(0), 0x66(1)         -> capability report for both channels
       healthy unit:  extra1=0 -> H264 1920x1080, extra1=1 -> RAW 160x120
       degraded unit: extra1=1 -> H264 640x480  (power-cycle needed)
  2) 3000 logins ch0..ch5          -> sids (global per-boot counter; first slot
       on this unit is often DEAD, later slots LIVE)
  3) per sid: ONE 0x78 config + ONE CLEANALARM{ sid,1 }, sniff ~1.5s,
       classify by content (H264 vs RAW vs silent), keep first VIS + first IR.
  4) capture + keepalives (0x14 every ~10s) + optional 0x6051 stats.

Frame bytes are byte-exact (verified against relay_3000/3001.log):
- 3001 header (0x58): magic@0, "video server"@4, 00x12@0x10, "8888"@0x1C,
  "88"+00x14@0x20, "888888"+00x10@0x30, 00x4@0x40, req@0x44, flag@0x48,
  extra1@0x4C, psize@0x50, MAGIC2@0x54, payload@0x58.
- 3000 login (0x30): magic@0, "video server"@4, 00+ccx11@0x10, 01007f00@0x1C,
  0001b80b@0x20, channel@0x24, psize=40@0x28, MAGIC2@0x2C,
  "888888"+00 + ccx13 + "888888"+00 + ccx13 (40B).  resp: {sid, ffffffff}.
- CLEANALARM (0x30): magic@0, ccx24@4, 0200@0x1C, ccx6@0x1E, 00000000@0x24,
  psize=8@0x28, MAGIC2@0x2C, {sid,1}. KEEPALIVE: 1400@0x1C, psize=0.

Usage:
  python pcb_client.py --host 192.168.2.32 [--secs 30] [--outdir out]
"""
import socket, struct, time, threading, argparse, os, datetime

MAGIC1 = struct.pack('<I', 0x123AB678)
MAGIC2 = struct.pack('<I', 0x876CD321)
USER = b'video server'
PWD_PAYLOAD = b'888888\x00' + b'\xcc' * 13 + b'888888\x00' + b'\xcc' * 13   # 40 bytes
LOGIN_1C = bytes.fromhex('01007f00')
PORT_WORD = bytes.fromhex('0001b80b')   # 0x0BB8 = 3000
REQ6051_PAYLOAD = (
    bytes.fromhex('0000000058000000') + b'\x00' * 32 +
    bytes.fromhex('0000000004000000') + b'\x00' * 16 +
    b'\x00' * 32 + bytes.fromhex('ffffffff') + b'\x00' * 8)
# ^ 96 bytes: matches vendor req 0x6051 payload exactly


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
    f[4:16] = USER
    f[0x10] = 0x00
    f[0x11:0x1C] = b'\xcc' * 11
    f[0x1C:0x20] = LOGIN_1C
    f[0x20:0x24] = PORT_WORD
    f[0x24:0x28] = struct.pack('<I', channel)
    f[0x28:0x2C] = struct.pack('<I', 40)
    f[0x2C:0x30] = MAGIC2
    return bytes(f) + PWD_PAYLOAD


def mk_ca(channel, sid):
    f = bytearray(0x30)
    f[0:4] = MAGIC1
    f[4:0x1C] = b'\xcc' * 24
    f[0x1C:0x1E] = b'\x02\x00'
    f[0x1E:0x24] = b'\xcc' * 6
    f[0x24:0x28] = struct.pack('<I', channel)
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


def conn(host, port):
    s = socket.create_connection((host, port), timeout=6)
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
    # '30' -> 3000-style (0x30 hdr, psize@0x28); '58' -> 3001 (0x58 hdr, psize@0x50)
    hl = 0x58 if layout == '58' else 0x30
    po = 0x50 if layout == '58' else 0x28
    hdr = recv_exact(s, hl, label, timeout)
    if hdr[:4] != MAGIC1:
        raise IOError('%s: bad magic %s' % (label, hdr[:4].hex()))
    psize = struct.unpack('<I', hdr[po:po + 4])[0]
    body = recv_exact(s, psize, label, timeout) if psize else b''
    return hdr, body


def req(host, port, frame, label):
    s = conn(host, port)
    s.sendall(frame)
    hdr, body = recv_frame(s, label, layout=('58' if port == 3001 else '30'))
    s.close()
    return hdr, body


def classify(first):
    if b'RAW\x00' in first:
        return 'ir'
    if b'H264' in first or b'\x00\x00\x00\x01\x67' in first:
        return 'vis'
    return None


def codec_summary(body_extra0, body_extra1):
    def fmt(b):
        if b[:4] == b'H264':
            w, h = struct.unpack_from('<HH', b, 6)
            return 'H264 %dx%d' % (w, h)
        if b[:3] == b'RAW':
            return 'RAW %dx%d' % (struct.unpack_from('<H', b, 4)[0],
                                  struct.unpack_from('<H', b, 6)[0])
        return b[:16]
    return fmt(body_extra0), fmt(body_extra1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='192.168.2.32')
    ap.add_argument('--secs', type=int, default=30)
    ap.add_argument('--logins', type=int, default=10, help='max 3000 login attempts (ch0/1 alternate)')
    ap.add_argument('--outdir', default=os.path.join(os.getcwd(), 'out'))
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    vis_path = os.path.join(args.outdir, 'vis_%s.bin' % stamp)
    ir_path = os.path.join(args.outdir, 'ir_%s.bin' % stamp)
    log = open(os.path.join(args.outdir, 'session_%s.log' % stamp), 'w')

    def note(*a):
        line = ' '.join(str(x) for x in a)
        print(line)
        log.write(line + '\n')
        log.flush()

    t0 = time.time()

    # --- 3001 negotiation (EXACT vendor req words; 0x10066 for the IR/RAW slot) ---
    for extra1 in (0, 1):
        h, body = req(args.host, 3001, mk3001(0x65, 0, extra1, 0), '3001/0x65')
        note('0x65 extra1=%d -> %dB %r' % (extra1, len(body), body[:16]))
    bodies = []
    for extra1, reqw in ((0, 0x0066), (1, 0x10066)):
        h, body = req(args.host, 3001, mk3001(reqw, 0, extra1, 0), '3001/%#x extra1=%d' % (reqw, extra1))
        bodies.append(body)
        note('0x%05x extra1=%d -> %dB %r' % (reqw, extra1, len(body), body[:40]))
    if bodies and len(bodies) == 2:
        v, i = codec_summary(bodies[0], bodies[1])
        note('CODECS: ch0=%s  ch1=%s' % (v, i))
        if 'RAW' not in i:
            note('WARN: IR channel does NOT advertise RAW (gets %s) - camera likely '
                 'degrebated; a power-cycle usually restores RAW 160x120' % i)

    # --- logins + probes (vendor-interleaved; one config+CA per sid) ---
    logins = []
    stop = threading.Event()
    counts = {'vis': 0, 'ir': 0}
    errors = []
    pumps = []            # (sock, fh, name)
    threads = []

    def pump(sock, fh, name):
        sock.settimeout(8)
        while not stop.is_set():
            try:
                chunk = sock.recv(262144)
            except socket.timeout:
                errors.append('%s timeout' % name)
                break
            if not chunk:
                errors.append('%s closed' % name)
                break
            fh.write(chunk)
            counts[name] = counts.get(name, 0) + len(chunk)

    visf = open(vis_path, 'wb')
    irf = open(ir_path, 'wb')
    have = {'vis': False, 'ir': False}
    route_files = {}     # route -> index counter for file naming
    stream_handles = []  # (handle, basename)

    def try_stream(ch, sid, chan, want):
        # CA FIRST (vendor: conn#6/9 CA at t, stream starts immediately),
        # then config on 3001; sniff ~2s, classify.
        # Vendor couples the codec negotiation to the CA: the RAW 0x10066 is
        # (re)sent RIGHT BEFORE the IR login+CA, and the CA channel byte is
        # 1 for the RAW engine, 0 for VIS.
        try:
            if want == 'ir':
                req(args.host, 3001, mk3001(0x10066, 0, 1, 0), '3001/0x10066 pre-CA')
            else:
                req(args.host, 3001, mk3001(0x0066, 0, 0, 0), '3001/0x0066 pre-CA')
            ca = conn(args.host, 3000)
            ca.sendall(mk_ca(1 if want == 'ir' else 0, sid))
            h, ack = recv_frame(ca, 'ca ch%d 0x%02x' % (ch, sid))
            req(args.host, 3001, mk3001(0x00010078, 0, 0 if want == 'vis' else 1, 16,
                                        struct.pack('<IIII', 3, chan, sid, 3000)),
                '3001/0x78 ch%d' % chan)
            ca.settimeout(2.0)
            first = b''
            tend = time.time() + 2.0
            while time.time() < tend and len(first) < 65536:
                try:
                    part = ca.recv(65536 - len(first))
                except socket.timeout:
                    break
                if not part:
                    break
                first += part
            kind = classify(first)
            note('probe ch%d sid=0x%02x chan%d -> %s (%dB sniffed)' % (
                ch, sid, chan, kind if kind else 'silent', len(first)))
            if not first:
                ca.close()
                return None
            # route by content; unclassified streamers are saved as 'unk' but
            # never satisfy the 'ir'/'vis' requirements (a raw stream always
            # shows 00 00 01 b3 + RAW markers within 64KB, so a markerless
            # stream is a compressed view, not RAW).
            kind = classify(first)
            if kind == 'ir':
                route = 'ir'
            elif kind == 'vis':
                route = 'vis' if want == 'vis' else 'ir640'
            else:
                route = 'unk'
            return ca, route
        except OSError as e:
            note('probe ch%d sid=0x%02x chan%d err: %s' % (ch, sid, chan, e))
        return None

    # RAW-hunt: the camera allocates sids per session and which slot carries RAW
    # IR varies per session (vendor today: chan4 on its ch1 sid 0x36 -> RAW).
    # Probe chan4 on each fresh sid until RAW found, then chan2 on the next
    # fresh sid for VIS. One probe per sid (re-configuring a sid's channel
    # silently wedges the camera). Alternate ch0/ch1 logins (vendor used
    # ch0, ch1, ch0-again).
    for li in range(args.logins):
        if have.get('ir') and have.get('vis'):
            break
        ch = li & 1
        try:
            s = conn(args.host, 3000)
            s.sendall(mk_login(ch))
            h, b = recv_frame(s, 'login%d' % ch)
            sid = struct.unpack('<I', b[:4])[0] if len(b) >= 4 else 0xFFFFFFFF
        except OSError:
            continue
        note('login ch%d -> sid=0x%02x resp=%s' % (ch, sid, b.hex()))
        if sid == 0xFFFFFFFF:
            s.close()
            continue
        logins.append((ch, s, sid))   # kept open as control/keepalive conn
        if not have.get('ir'):
            want, chn = 'ir', 4
        elif not have.get('vis'):
            want, chn = 'vis', 2
        else:
            continue
        ca = try_stream(ch, sid, chn, want)
        if ca is None:
            continue
        ca, route = ca
        route_files[route] = route_files.get(route, 0) + 1
        idx = route_files[route]
        fname = '%s%d_%s.bin' % (route, idx, stamp)
        fh = open(os.path.join(args.outdir, fname), 'wb')
        stream_handles.append((fh, fname))
        have[route] = True
        pumps.append((ca, fh, route))

    for ca, fh, name in pumps:
        t = threading.Thread(target=pump, args=(ca, fh, name))
        t.start()
        threads.append(t)

    # --- optional 0x6051 stats (3001) ---
    try:
        h, body = req(args.host, 3001, mk3001(0x6051, 0, 1, 96, REQ6051_PAYLOAD), '3001/0x6051')
        if len(body) >= 8 and len(body) % 8 == 0:
            note('0x6051 -> %dB doubles=%s' % (len(body), ', '.join('%.3f' % v for v in
                 struct.unpack_from('<%dd' % (len(body) // 8), body))[:200]))
        else:
            note('0x6051 -> %dB raw=%s' % (len(body), body[:32].hex()))
    except Exception as e:
        note('0x6051 err', e)

    # --- capture window + keepalives ---
    end = time.time() + args.secs
    last_ka = time.time()
    while time.time() < end:
        if time.time() - last_ka > 10:
            for ch, s, sid in logins:
                try:
                    s.sendall(mk_keepalive(ch))
                except OSError:
                    pass
            last_ka = time.time()
        time.sleep(0.2)

    stop.set()
    for t in threads:
        t.join(timeout=4)
    for fh, _ in stream_handles:
        fh.close()
    visf.close()
    irf.close()

    if not pumps:
        note('WARN: no streams detected; camera may need a power-cycle')

    extra = ''
    if counts['ir'] > 0:
        extra = '  ir frames=%d (39448B each incl. 80B hdr + 38400B 12-bit raw + tail)' % (counts['ir'] // 39448)
    note('DONE %.1fs  vis=%d bytes  ir=%d bytes  %s' % (time.time() - t0, counts['vis'], counts['ir'], extra))
    note('  visible: %s    ffmpeg -f h264 -i "%s" out.mp4' % (vis_path, vis_path))
    note('  ir:      %s' % ir_path)
    if errors:
        note('  errors:', '; '.join(errors))
    log.close()


if __name__ == '__main__':
    main()