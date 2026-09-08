"""FIXED: Correct 3001 frame format from capture analysis."""
import socket, struct, time, threading, select

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13

def mk3001(req, flag, psize, extra1=0):
    """88-byte port 3001 frame. Fixed layout from capture."""
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x11] = b"video server\x00"       # 13 bytes (0x04-0x10)
    # 0x11-0x1B: 11 zeros (already zero)
    f[0x1C:0x22] = b"888888"                  # "888888" at offset 0x1C
    # 0x22-0x2F: 14 zeros (already zero)
    f[0x30:0x36] = b"888888"                  # "888888" at offset 0x30
    # 0x36-0x43: 14 zeros (already zero)
    struct.pack_into('<I', f, 0x44, req)       # request code
    struct.pack_into('<I', f, 0x48, flag)      # flag
    struct.pack_into('<I', f, 0x4C, extra1)    # extra field (1 for config, 0 for init)
    struct.pack_into('<I', f, 0x50, psize)     # payload size
    struct.pack_into('<I', f, 0x54, M2)        # MAGIC2
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
    except: pass
    return d

import subprocess
subprocess.run("taskkill /IM PCB_Client.exe /F", capture_output=True, shell=True)
time.sleep(10)

print("=" * 60)
print("FIXED 3001 FRAME FORMAT")
print("=" * 60)

# Verify our frame matches capture
our = mk3001(0x65, 0, 0, 1)
cap_hex = "78b63a12766964656f207365727665720000000000000000000000003838383838380000000000000000000000000000383838383838000000000000000000000000000000000000000000000000000000006500000001000000000000000000000021d36c87"
cap = bytes.fromhex(cap_hex)
print("Our frame matches capture: %s" % ("YES" if our == cap else "NO"))
if our != cap:
    for i in range(min(len(our), len(cap))):
        if our[i] != cap[i]:
            print("  byte %04x: ours=0x%02x cap=0x%02x" % (i, our[i], cap[i]))

# Phase 1: 3001 init
print("\n[1] 3001 init handshakes")
c3001 = []
for flag in [0, 0]:  # both flag=0 per capture
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x65, flag, 0, 1))
    time.sleep(0.1)
    r = rq(s, 2.0)
    print("  req=0x65 flag=%d: %d bytes" % (flag, len(r)))
    if r:
        print("    hex: %s" % r[:48].hex())
    c3001.append(s)

# Phase 2: 3000 login
print("\n[2] 3000 login")
s0 = socket.socket(); s0.settimeout(5); s0.connect((CAM, 3000))
s0.sendall(mklogin(0)); time.sleep(0.02); s0.sendall(PWD)
r = rq(s0, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch0: %d bytes cmd=0x%08X" % (len(r), cmd))

s1 = socket.socket(); s1.settimeout(5); s1.connect((CAM, 3000))
s1.sendall(mklogin(1)); time.sleep(0.02); s1.sendall(PWD)
r = rq(s1, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch1: %d bytes cmd=0x%08X" % (len(r), cmd))

# Phase 3: CLEANALARM
print("\n[3] CLEANALARM")
va = socket.socket(); va.settimeout(5); va.connect((CAM, 3000))
va.sendall(mkctrl(0xCCCC0002, 0, 8)); time.sleep(0.02)
va.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
ra = rq(va, 2)
cmd_a = struct.unpack_from('<I', ra, 0x1C)[0] if len(ra) >= 0x20 else -1
print("  ch0 34: %d bytes cmd=0x%08X" % (len(ra), cmd_a))

# Phase 4: 3001 config on NEW conns with correct frame
print("\n[4] 3001 config (FIXED frame)")
for chan, val in [(4, 0x35), (2, 0x34)]:
    s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
    s.sendall(mk3001(0x00010078, 0, 16, 1))
    time.sleep(0.1)
    r = rq(s, 2.0)
    print("  cfg handshake chan%d: %d bytes" % (chan, len(r)))
    if r:
        print("    hex: %s" % r[:48].hex())
    time.sleep(0.05)
    s.sendall(struct.pack('<IIII', 3, chan, val, 3000))
    time.sleep(0.1)
    r = rq(s, 2.0)
    print("  cfg config chan%d: %d bytes" % (chan, len(r)))
    if r:
        print("    hex: %s" % r[:48].hex())
    s.close()
    time.sleep(0.05)

# Phase 5: cmd 0x14
print("\n[5] cmd 0x14")
s0.sendall(mkctrl(0xCCCC0014, 0, 0))
r = rq(s0, 1)
print("  login0 0x14: %d bytes" % len(r))

# Phase 6: 3001 final
print("\n[6] 3001 final handshake")
s = socket.socket(); s.settimeout(5); s.connect((CAM, 3001))
s.sendall(mk3001(0x90, 0, 0, 0))
time.sleep(0.1)
r = rq(s, 2.0)
print("  0x90: %d bytes" % len(r))
s.close()

# Phase 7: Read video
print("\n[7] Reading video 20s...")
buf = bytearray()
start = time.time()
while time.time() - start < 20:
    va.settimeout(1)
    try:
        c = va.recv(65536)
        if c:
            buf += c
            if len(buf) <= 256:
                print("  t=%.1f: %d bytes (total %d)" % (time.time()-start, len(c), len(buf)))
    except: pass

print("\nTotal: %d bytes" % len(buf))
if buf:
    print("head: %s" % buf[:128].hex())
    print("ascii: %s" % ''.join(chr(b) if 32<=b<127 else '.' for b in buf[:128]))
    with open("D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_fixed.bin", 'wb') as f:
        f.write(bytes(buf))
    print("SAVED")

for s in [s0, s1, va] + c3001:
    try: s.close()
    except: pass
print("DONE")
