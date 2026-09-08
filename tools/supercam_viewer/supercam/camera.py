"""camera.py - threaded dual-stream SuperCam client (IR + VIS) for the viewer.

Replicates the proven rev-5 connection (reverse_engineering_NOTES.md Addendum 7):
negotiate -> RAW-hunt chan4/extra1=1 (one probe per sid) -> VIS on next sid
(chan2/extra1=0) -> keepalives -> continuous pumps with callbacks.
"""
import socket
import struct
import threading
import time

from . import proto

NEG_OPENS = [(0x65, 0), (0x66, 0), (0x10066, 1)]
KEEPALIVE_EVERY = 9.0
SNIFF_SECONDS = 2.0
CH_MAX = 20


class CameraClient:
    def __init__(self, host, port=3000, on_ir_frame=None, on_vis_frame=None,
                 on_state=None, on_status=None):
        self.host = host
        self.port = port
        self.on_ir_frame = on_ir_frame
        self.on_vis_frame = on_vis_frame
        self.on_state = on_state
        self.on_status = on_status
        self._stop = threading.Event()
        self._thread = None
        self._status_lock = threading.Lock()
        self._status = dict(ir=0, vis=0, sid='-', state='idle', err='', bytes=0)

    # ---- public ---------------------------------------------------------
    def start(self):
        self._status_lock.acquire()
        self._status = dict(ir=0, vis=0, sid='-', state='connecting', err='', bytes=0)
        self._status_lock.release()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name='supercam-client')
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._state('stopping')

    @property
    def status(self):
        with self._status_lock:
            return dict(self._status)

    # ---- internals ------------------------------------------------------
    def _state(self, s, err=''):
        with self._status_lock:
            self._status['state'] = s
            self._status['err'] = err
        cb = self.on_state
        if cb:
            cb(s, err)

    def _set_status(self, **kw):
        with self._status_lock:
            self._status.update(kw)

    def _emit_ir(self, img, fstats, rate):
        self._set_status(ir=rate)
        if self.on_ir_frame:
            self.on_ir_frame(img, fstats, rate)

    def _emit_vis(self, frame, rate):
        self._set_status(vis=rate)
        if self.on_vis_frame:
            self.on_vis_frame(frame, rate)

    def _run(self):
        from .decoders import classify, IRParser
        try:
            self._login_socks = []
            self._sids = []
            self._ca_socks = []
            self._state('negotiating')
            for req, e1 in NEG_OPENS:
                proto.request(self.host, 3001, proto.mk3001(req, 0, e1, 0),
                              'neg 0x%x' % req)

            have_ir = have_vis = False
            started = time.time()
            ok_ir = ok_vis = None
            sids = []

            from .decoders import VisDecoder
            vis = VisDecoder()
            vis.start()
            self._vis = vis

            for li in range(CH_MAX):
                if self._stop.is_set():
                    break
                ch = li & 1
                sock = proto.connect(self.host, self.port)
                sock.sendall(proto.mk_login(ch))
                hdr, body = proto.recv_frame(sock, 'login ch%d' % ch)
                sid = struct.unpack('<I', body[:4])[0] if len(body) >= 4 else 0xFFFFFFFF
                if sid == 0xFFFFFFFF:
                    sock.close()
                    continue
                sids.append(sid)
                self._login_socks.append(sock)
                self._set_status(sid=str(sid))

                if not have_ir:
                    self._state('hunting IR sid=0x%x' % sid)
                    proto.request(self.host, 3001, proto.mk3001(0x10066, 0, 1, 0),
                                  'pre-CA re-neg')
                    ca = proto.connect(self.host, self.port)
                    ca.sendall(proto.mk_ca(1, sid))
                    proto.recv_frame(ca, 'CA ir')
                    try:
                        proto.config_req(self.host, 4, sid)
                    except OSError:
                        pass
                    kind = self._sniff(ca)
                    if kind == 'ir':
                        have_ir = True
                        ok_ir = sid
                        self._ca_socks.append(ca)
                        self._state('IR on sid=0x%x' % sid)
                        self._pump_ir(ca)
                    else:
                        print('[camera] ch%d sid=0x%x -> %s (open another)' % (ch, sid, kind))
                        ca.close()
                elif not have_vis:
                    self._state('VIS sid=0x%x' % sid)
                    proto.request(self.host, 3001, proto.mk3001(0x0066, 0, 0, 0),
                                  'pre-VIS re-neg')
                    ca = proto.connect(self.host, self.port)
                    ca.sendall(proto.mk_ca(0, sid))
                    proto.recv_frame(ca, 'CA vis')
                    try:
                        proto.config_req(self.host, 2, sid)
                    except OSError:
                        pass
                    kind = self._sniff(ca)
                    if kind == 'vis':
                        have_vis = True
                        ok_vis = sid
                        self._ca_socks.append(ca)
                        self._state('VIS on sid=0x%x' % sid)
                        self._pump_vis(ca)
                    else:
                        print('[camera] ch%d sid=0x%x -> %s' % (ch, sid, kind))
                        ca.close()
                    if have_ir and have_vis:
                        break
                else:
                    sock.close()

            if not have_ir:
                raise IOError('no IR stream found (sids tried: %s)' %
                              ', '.join('0x%x' % x for x in sids))
            if not have_vis:
                self._state('IR OK, VIS MISSING')
            self._state('streaming IR=0x%x VIS=%s' % (ok_ir or 0, ('0x%x' % ok_vis) if ok_vis else 'n/a'))

            keep = threading.Thread(target=self._keepalive, daemon=True,
                                    name='keepalive')
            keep.start()
            while not self._stop.is_set():
                time.sleep(0.2)
            self._state('stopped')
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._state('error', '%s: %s' % (type(e).__name__, e))
        finally:
            for s in getattr(self, '_ca_socks', []):
                try:
                    s.close()
                except Exception:
                    pass
            for s in getattr(self, '_login_socks', []):
                try:
                    s.close()
                except Exception:
                    pass

    def _sniff(self, ca):
        """Read briefly on a freshly-bound CA socket, classify content."""
        from .decoders import classify
        first = b''
        ca.settimeout(SNIFF_SECONDS)
        deadline = time.time() + SNIFF_SECONDS
        while time.time() < deadline and len(first) < 128 * 1024:
            try:
                chunk = ca.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            first += chunk
            k = classify(first)
            if k:
                return k
        return None

    def _keepalive(self):
        while not self._stop.is_set():
            time.sleep(KEEPALIVE_EVERY)
            if self._stop.is_set():
                break
            for i, s in enumerate(self._login_socks):
                try:
                    s.sendall(proto.mk_keepalive(i & 1))
                except OSError:
                    pass

    def _pump_ir(self, ca):
        from .decoders import IRParser
        parser = IRParser()
        ca.settimeout(5)
        last = time.time()
        img = None

        def loop():
            nonlocal last, img
            while not self._stop.is_set():
                try:
                    data = ca.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                self._set_status(bytes=self._status['bytes'] + len(data))
                produced = 0
                for fr in parser.feed(data):
                    img = IRParser.to_image(fr)
                    fs = IRParser.stats(img)
                    produced += 1
                    self._emit_ir(img, fs, 0)
                if produced:
                    now = time.time()
                    rate = produced / (now - last) if now > last else 0
                    last = now
                    self._set_status(ir=rate)

        t = threading.Thread(target=loop, daemon=True, name='pump-ir')
        t.start()
        return t

    def _pump_vis(self, ca):
        ca.settimeout(5)

        def loop():
            last = time.time()
            while not self._stop.is_set():
                try:
                    data = ca.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                self._set_status(bytes=self._status['bytes'] + len(data))
                self._vis.write(data)
                rate = self._vis.fps()
                if rate:
                    self._set_status(vis=rate)
                    frame = self._vis.latest()
                    if frame is not None:
                        self._emit_vis(frame, rate)

        t = threading.Thread(target=loop, daemon=True, name='pump-vis')
        t.start()
        return t