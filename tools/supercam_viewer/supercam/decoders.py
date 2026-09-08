"""decoders.py - stream decoding for the SuperCam viewer.

- IRParser:  on-the-fly framing of the RAW 39448B thermal frames -> numpy (120,160)
- VisDecoder: live H.264 ES decode (PyAV over a seekable memory buffer) -> BGR
- classify: content sniffing used by the camera session (RAW vs H264)
"""
import io
import threading

import numpy as np

# IR frame layout (Addendum 6/7): fixed 39448B, LAUNCHDIGITAL+RAW header,
# 38400B of u16-LE 12-bit samples, small tail.
IR_FRAME = 39448
IR_HEADER = 80
IR_SAMPLES = 38400   # = 19200 * u16 = 160 x 120


def classify(first):
    if b'RAW\x00' in first:
        return 'ir'
    if b'H264' in first or b'\x00\x00\x00\x01\x67' in first:
        return 'vis'
    return None


class IRParser:
    """Frames a byte stream into 39448B thermal frames, returns raw byte frames."""

    def __init__(self):
        self._buf = b''

    def feed(self, data):
        self._buf += data
        frames = []
        while True:
            i = self._buf.find(b'\x00\x00\x01\xb3')
            if i < 0:
                self._buf = self._buf[-4:]
                break
            if i > 0:
                self._buf = self._buf[i:]
            if len(self._buf) < IR_FRAME:
                break
            f, self._buf = self._buf[:IR_FRAME], self._buf[IR_FRAME:]
            frames.append(f)
        return frames

    @staticmethod
    def to_image(fr):
        """39448B frame -> (120,160) float32, NaN for dead/0 samples."""
        arr = np.frombuffer(fr, dtype=np.uint8, offset=IR_HEADER,
                            count=IR_SAMPLES).astype(np.uint16, copy=True)
        arr = (arr[1::2] << 8) | arr[0::2]          # reinterpret u16-LE
        img = arr.reshape(120, 160).astype(np.float32)
        img[img == 0] = np.nan
        return img

    @staticmethod
    def stats(img):
        v = img[~np.isnan(img)]
        if v.size == 0:
            return None
        return float(np.nanmin(v)), float(np.nanmean(v)), float(np.nanmax(v))


class ChunkBuffer(io.RawIOBase):
    """Seekable, growing buffer that blocks reads on empty until more data or EOF.
    Lets PyAV probe/grow-append/FIFO-style decode without OS pipes."""

    def __init__(self):
        super().__init__()
        self._buf = bytearray()
        self._pos = 0
        self._eof = False
        self._cv = threading.Condition()

    def write(self, data):
        with self._cv:
            self._buf += data
            self._cv.notify_all()

    def close(self):
        with self._cv:
            self._eof = True
            self._cv.notify_all()

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return True

    def readinto(self, b):
        with self._cv:
            while True:
                avail = len(self._buf) - self._pos
                if avail > 0:
                    break
                if self._eof:
                    return 0
                self._cv.wait()
            n = min(len(b), avail)
            b[:n] = self._buf[self._pos:self._pos + n]
            self._pos += n
            return n

    def seek(self, offset, whence=0):
        with self._cv:
            if whence == 0:
                p = offset
            elif whence == 1:
                p = self._pos + offset
            elif whence == 2:
                p = len(self._buf) + offset
            else:
                raise ValueError(whence)
            if p < 0:
                raise ValueError('negative seek pos')
            self._pos = p
            return p

    def tell(self):
        return self._pos


class VisDecoder:
    """Live H.264 elementary-stream decoder via PyAV -> BGR ndarray."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frame = None    # latest BGR ndarray
        self._fps_count = 0
        self._closed = False
        self._thread = None
        try:
            import av
        except Exception as e:            # pragma: no cover
            raise RuntimeError('PyAV required: pip install av (%r)' % e)
        self._av = av
        self._buf = ChunkBuffer()

    def start(self):
        buf = self._buf

        def _loop():
            import traceback
            try:
                c = self._av.open(buf, format='h264', mode='r')
            except Exception:
                traceback.print_exc()
                return
            try:
                for packet in c.demux():
                    for frame in packet.decode():
                        with self._lock:
                            self._frame = frame.to_ndarray(format='bgr24')
                            self._fps_count += 1
            except Exception:
                traceback.print_exc()
            finally:
                try:
                    c.close()
                except Exception:
                    pass

        self._thread = threading.Thread(target=_loop, daemon=True, name='vis-decode')
        self._thread.start()
        return self

    def write(self, chunk):
        if self._closed:
            return
        self._buf.write(chunk)

    def latest(self):
        with self._lock:
            return self._frame

    def fps(self):
        """Decoded frames since the previous call (rolling 1s estimate helper)."""
        with self._lock:
            n = self._fps_count
            self._fps_count = 0
        return n

    def close(self):
        self._closed = True
        self._buf.close()