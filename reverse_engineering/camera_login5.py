"""Corrected camera login - exact 40B payload from capture."""
import socket, struct, time

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

def make_3000_login(cmd_word, unknown, channel, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x10] = b"video server"     # 12 bytes
    f[0x10:0x1C] = b"\x00" + b"\xcc"*11  # \0 + 11 CC = 12 bytes -> offset 0x04..0x1B = 24 bytes
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

# EXACT 40B payload: "888888\0" + CC*13 + "888888\0" + CC*13
PWD_PAYLOAD = b"888888\x00" + b"\xcc"*13 + b"888888\x00" + b"\xcc"*13
assert len(PWD_PAYLOAD) == 40

def recv_until_quiet(sock, timeout=2):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            c = sock.recv(65536)
            if not c: break
            data += c
    except socket.timeout: pass
    except: pass
    return data

# Verify frame matches working capture #17
working17 = "78b63a12766964656f2073657276657200cccccccccccccccccccccccc0100c0a80220b80b000000002800000021d36c87"

print("Testing corrected password payload:")
print("  hex:", PWD_PAYLOAD.hex())
print()

# Do TWO connections like PCB tool
for ch, srcport_unk in [(0, 0x0BB82002), (1, 0x0BB82002)]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        hdr = make_3000_login(0xA8C00001, srcport_unk, ch, 40)
        print("conn ch=%d" % ch)
        print("  hdr match working17:", hdr.hex() == working17.replace('0220b80b','0220b80b'))
        s.sendall(hdr)
        time.sleep(0.03)
        s.sendall(PWD_PAYLOAD)
        resp = recv_until_quiet(s, 3)
        print("  resp(%dB): %s" % (len(resp), resp.hex()))
        if len(resp) >= 0x1C:
            cmd = struct.unpack_from('<I', resp, 0x1C)[0]
            print("  -> cmd_word=0x%08X" % cmd)
            if cmd == 0x00000001:
                print("  *** LOGIN OK! ***")
            else:
                print("  login status: 0x%02X" % (cmd & 0xFF))
    except Exception as e:
        print("  conn ch=%d error: %s" % (ch, e))
    finally:
        s.close()
    time.sleep(0.1)

print("\nDONE")
