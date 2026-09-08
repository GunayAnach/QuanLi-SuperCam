"""Debug: get raw login response bytes."""
import socket, struct, time, binascii

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321
PWD_PAYLOAD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13

def make_3000_login(cmd_word, unknown, channel, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x10] = b"video server"
    f[0x10:0x1C] = b"\x00" + b"\xcc"*11
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

def recv_all(sock, timeout=2):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            c = sock.recv(65536)
            if not c: break
            data += c
    except socket.timeout: pass
    return data

def login(ch):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((CAM, 3000))
    
    frame = make_3000_login(0xA8C00001, 0x0BB82002, ch, 40)
    print("ch%d login frame:" % ch)
    print("  %s" % frame.hex())
    s.sendall(frame)
    
    time.sleep(0.03)
    s.sendall(PWD_PAYLOAD)
    print("  pwd payload sent")
    
    resp = recv_all(s, 3)
    print("  resp %d bytes: %s" % (len(resp), resp.hex()))
    if len(resp) >= 0x38:
        m1 = struct.unpack_from('<I', resp, 0)[0]
        cw = struct.unpack_from('<I', resp, 0x1C)[0]
        unk = struct.unpack_from('<I', resp, 0x20)[0]
        chn = struct.unpack_from('<I', resp, 0x24)[0]
        ps = struct.unpack_from('<I', resp, 0x28)[0]
        m2 = struct.unpack_from('<I', resp, 0x2C)[0]
        print("  MAGIC1=0x%08X cmd=0x%08X unk=0x%08X ch=%d ps=%d MAGIC2=0x%08X" % (m1, cw, unk, chn, ps, m2))
    elif len(resp) > 0:
        print("  first 48 bytes hex-dumped:")
        for i in range(0, min(len(resp), 48), 16):
            chunk = resp[i:i+16]
            print("    %04x: %s" % (i, ' '.join('%02x' % b for b in chunk)))
    else:
        print("  EMPTY RESPONSE")
    return s

# Kill any PCB tool
import subprocess
subprocess.run("taskkill /IM PCB_Client.exe /F", capture_output=True, shell=True)
time.sleep(5)

print("=" * 60)
print("DEBUG LOGIN RESPONSE")
print("=" * 60)

s0 = login(0)
s1 = login(1)

# Keep alive and check
time.sleep(1)

print("\nDone")
s0.close()
s1.close()
