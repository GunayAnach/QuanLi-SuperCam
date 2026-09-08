"""FAITHFUL replication of the exact capture sequence #1-#62."""
import socket, struct, time, threading, sys

CAM = "192.168.2.32"
M1 = 0x123AB678
M2 = 0x876CD321
PWD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13

def mk3001(req, flag, psize):
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x11] = b"video server\x00"
    f[0x11:0x14] = b"\x00"*3
    f[0x14:0x18] = b"8888"
    f[0x18:0x20] = b"\x00"*8
    f[0x20:0x27] = b"888888\x00"
    f[0x27:0x30] = b"\x00"*9
    f[0x30:0x37] = b"888888\x00"
    f[0x37:0x44] = b"\x00"*13
    struct.pack_into('<I', f, 0x44, req)
    struct.pack_into('<I', f, 0x48, flag)
    struct.pack_into('<I', f, 0x4C, 0)
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

def mkctrl(cw, ch, ps, unk4=0xCCCCCCCC):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1)
    f[0x04:0x1C] = b"\xcc"*24
    struct.pack_into('<I', f, 0x1C, cw)
    struct.pack_into('<I', f, 0x20, unk4)
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f)

def rq(sock, t=1.5):
    sock.settimeout(t)
    d = b''
    try:
        while True:
            c = sock.recv(65536)
            if not c: break
            d += c
    except: pass
    return d

def s3001(req, flag, psize, payload=b""):
    s = socket.socket()
    s.settimeout(3)
    s.connect((CAM, 3001))
    s.sendall(mk3001(req, flag, psize))
    r = rq(s, 0.5)
    if payload:
        s.sendall(payload)
        r2 = rq(s, 0.5)
        r = r + r2
    return s, r

import subprocess
subprocess.run("taskkill /IM PCB_Client.exe /F", capture_output=True, shell=True)
time.sleep(10)

print("=" * 60)
print("FAITHFUL CAPTURE REPLICATION")
print("=" * 60)

# #1-2: 3001 handshake req=0x65, flag=1/0
print("\n[#1-2] 3001 handshake req=0x65")
s1, r = s3001(0x65, 1, 1)
print("  flag=1 -> %d bytes" % len(r))
s2, r = s3001(0x65, 0, 1)
print("  flag=0 -> %d bytes" % len(r))

# #9-10: 3001 handshake req=0x66 (flag 0, 1)
print("[#9-10] 3001 handshake req=0x66")
s3, r = s3001(0x66, 0, 0)
print("  flag=0 -> %d bytes" % len(r))
s4, r = s3001(0x66, 1, 0)
print("  flag=1 -> %d bytes" % len(r))

# #17-18: 3000 login
print("\n[#17-18] 3000 login")
s5 = socket.socket(); s5.settimeout(5); s5.connect((CAM, 3000))
s5.sendall(mklogin(0)); time.sleep(0.02); s5.sendall(PWD)
r = rq(s5, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch0: %d bytes cmd=0x%08X" % (len(r), cmd))

s6 = socket.socket(); s6.settimeout(5); s6.connect((CAM, 3000))
s6.sendall(mklogin(1)); time.sleep(0.02); s6.sendall(PWD)
r = rq(s6, 3)
cmd = struct.unpack_from('<I', r, 0x1C)[0] if len(r) >= 0x20 else -1
print("  ch1: %d bytes cmd=0x%08X" % (len(r), cmd))

# #27-36: CLEANALARM
print("\n[#27-36] CLEANALARM")
# ch1 first (payload 35), then ch0 (payload 34) - matching capture order
vb = socket.socket(); vb.settimeout(5); vb.connect((CAM, 3000))
vb.sendall(mkctrl(0xCCCC0002, 1, 8))
time.sleep(0.02)
vb.sendall(b"\x35\x00\x00\x00\x01\x00\x00\x00")
rb = rq(vb, 2)
cmd_b = struct.unpack_from('<I', rb, 0x1C)[0] if len(rb) >= 0x20 else -1
print("  ch1 35: %d bytes cmd=0x%08X" % (len(rb), cmd_b))

va = socket.socket(); va.settimeout(5); va.connect((CAM, 3000))
va.sendall(mkctrl(0xCCCC0002, 0, 8))
time.sleep(0.02)
va.sendall(b"\x34\x00\x00\x00\x01\x00\x00\x00")
ra = rq(va, 2)
cmd_a = struct.unpack_from('<I', ra, 0x1C)[0] if len(ra) >= 0x20 else -1
print("  ch0 34: %d bytes cmd=0x%08X" % (len(ra), cmd_a))

# #37-42: 3001 config (req 0x00010078, psize 16) for chan=4 val=0x35
print("\n[#37-42] 3001 config ch4/0x35")
s7 = socket.socket(); s7.settimeout(3); s7.connect((CAM, 3001))
s7.sendall(mk3001(0x00010078, 1, 16))
r = rq(s7, 0.5)
print("  handshake: %d bytes" % len(r))
s7.sendall(struct.pack('<IIII', 3, 4, 0x35, 3000))
r = rq(s7, 0.5)
print("  config+resp: %d bytes" % len(r))

# #43-49: 3001 raw command (req 0x00006051, psize 96) + 96B payload
print("\n[#43-49] 3001 raw cmd (req 0x6051)")
s8 = socket.socket(); s8.settimeout(3); s8.connect((CAM, 3001))
s8.sendall(mk3001(0x00006051, 0, 96))
r = rq(s8, 0.5)
print("  handshake: %d bytes" % len(r))
# 96B payload (from capture: all zeros except first 8 bytes: 00 00 00 00 58 00 00 00)
raw96 = bytearray(96)
raw96[4] = 0x58  # 88 decimal
s8.sendall(bytes(raw96))
r = rq(s8, 0.5)
print("  payload+resp: %d bytes" % len(r))

# #48: cmd 0x14 on login ch1
print("\n[#48] cmd 0x14 on login ch1")
s6.sendall(mkctrl(0xCCCC0014, 1, 0))
r = rq(s6, 1)
print("  %d bytes" % len(r))

# #51-55: 3001 config (req 0x00010078, psize 16) for chan=2 val=0x34
print("\n[#51-55] 3001 config ch2/0x34")
s9 = socket.socket(); s9.settimeout(3); s9.connect((CAM, 3001))
s9.sendall(mk3001(0x00010078, 1, 16))
r = rq(s9, 0.5)
print("  handshake: %d bytes" % len(r))
s9.sendall(struct.pack('<IIII', 3, 2, 0x34, 3000))
r = rq(s9, 0.5)
print("  config+resp: %d bytes" % len(r))

# #56: cmd 0x14 on login ch0
print("\n[#56] cmd 0x14 on login ch0")
s5.sendall(mkctrl(0xCCCC0014, 0, 0))
r = rq(s5, 1)
print("  %d bytes" % len(r))

# #59: 3001 handshake req=0x90 (no payload)
print("\n[#59] 3001 handshake req=0x90")
s10, r = s3001(0x90, 0, 0)
print("  %d bytes" % len(r))

# #62: video data should flow now!
print("\n[#62+] Reading video on both CLEANALARM conns (15s)...")
bufs = [bytearray(), bytearray()]  # va=ch0, vb=ch1
threads = []
for i, vs in enumerate([va, vb]):
    def reader(sock=vs, idx=i):
        try:
            while True:
                c = sock.recv(65536)
                if not c: break
                bufs[idx] += c
        except: pass
    t = threading.Thread(target=reader)
    t.start()
    threads.append(t)

time.sleep(15)

for i, label in enumerate(["ch0(0x34)", "ch1(0x35)"]):
    sz = len(bufs[i])
    print("  %s: %d bytes" % (label, sz))
    if sz > 0:
        print("    head: %s" % bufs[i][:64].hex())
        print("    ascii: %s" % ''.join(chr(b) if 32<=b<127 else '.' for b in bufs[i][:64]))
        with open("D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_%s.bin" % label, 'wb') as f:
            f.write(bytes(bufs[i]))
        print("    SAVED")

# Cleanup
for s in [va, vb, s5, s6, s7, s8, s9, s10]:
    try: s.close()
    except: pass
for s in [s1, s2, s3, s4]:
    try: s.close()
    except: pass
print("\nDONE")
