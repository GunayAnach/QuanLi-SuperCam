"""Parse relay3000.log / relay_3001.log into protocol frames (bytes-fast path).

Relay log: headers `== HH:MM:SS.mmm conn#N C->S 88B  data 88B` then hexdump rows
`   000000  78 b6 3a 12 ...  x.:.video server`. Assembled with byte-level regex.
"""
import re, sys, struct, collections

INPROC = re.compile(rb'(?m)^== (\S+) conn#(\d+) (C->S|S->C) \d+B  data (\d+)B\r?\n')
HEXROW = re.compile(rb'^  [0-9a-f]{4,6}  ((?:[0-9a-f]{2} )+)', re.M)


def read_hex_log(path):
    data = open(path, 'rb').read()
    out = []
    marks = list(INPROC.finditer(data))
    for i, m in enumerate(marks):
        ts = m.group(1).decode()
        cid = int(m.group(2))
        dr = m.group(3).decode()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(data)
        body = data[m.end():end]
        raw = b''.join(bytes.fromhex(h.group(1)[:-1].decode()) for h in HEXROW.finditer(body))
        out.append((ts, cid, dr, raw))
    return out


def has_magic(b):
    return len(b) >= 4 and b[:4] == b'\x78\xb6\x3a\x12'


def frames_and_stream(path):
    items = read_hex_log(path)
    fr = sum(1 for _, _, _, b in items if has_magic(b))
    stream = sum(len(b) for _, _, _, b in items if not has_magic(b))
    return items, fr, stream


if __name__ == "__main__":
    import time
    port = sys.argv[1] if len(sys.argv) > 1 else '3000'
    t0 = time.time()
    items, nf, nb = frames_and_stream(r'D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\relay_%s.log' % port)
    print('items:', len(items), 'magic:', nf, 'stream bytes:', nb, 'in %.1fs' % (time.time() - t0))