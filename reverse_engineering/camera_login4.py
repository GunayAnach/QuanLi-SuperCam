"""Faithful camera login - exact bytes from capture #17-#26."""
import socket, struct, time

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

# ============================================================
# EXACT frame #17 (48B, C2S port 3000, SERVERCHS)
# 78b63a12 | "video server\0" | CC*11 | 01 00 c0 a8 | 02 20 b8 0b | 00 00 00 00 | 28 00 00 00 | 21 d3 6c 87
# Count: 4 + 13 + 11 + 4 + 4 + 4 + 4 + 4 = 48
#   MAGIC1(4) user(13) CC(11) | cmd_word(4) | ???(4) | channel(4) | ps(4) | MAGIC2(4)
# offsets: 0x00-0x03 MAGIC1, 0x04-0x10 user(13), 0x11-0x1B CC(11),
#          0x1C-0x1F cmd_word, 0x20-0x23 ???, 0x24-0x27 channel, 0x28-0x2B ps, 0x2C-0x2F MAGIC2
# ============================================================
def make_3000_login(cmd_word, unknown, channel, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x11] = b"video server\x00"    # 13 bytes
    f[0x11:0x1C] = b"\xcc" * 11
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

# ============================================================
# EXACT payload #21/#22 (40B, C2S port 3000, after SERVERCHS)
# 38 38 38 38 38 38 00 cc cc cc cc cc cc cc cc cc | cc cc cc cc 38 38 38 38 38 38 00 cc cc cc cc cc | cc cc cc cc cc cc cc cc
#   "888888\0"(7) + CC(12) + "888888\0"(7) + CC(14) = 40
# ============================================================
PWD_PAYLOAD = b"888888\x00" + b"\xcc"*12 + b"888888\x00" + b"\xcc"*14
assert len(PWD_PAYLOAD) == 40, len(PWD_PAYLOAD)

# Exact password hex from capture #21:
# 38383838383800cc cccccccccccccccc cccccccccccc38 38383838383800cc
# cccccccccccccccc cccccccccccc = ?
print("PWD_PAYLOAD(len=%d): %s" % (len(PWD_PAYLOAD), PWD_PAYLOAD.hex()))

# ============================================================
# Responses:
# #25 S2C (56B) = login success for channel 0:
#   cmd_word=0x00000001, ps=8, payload=34 00 00 00 ff ff ff ff
# #26 S2C (56B) = login success for channel 1:
#   cmd_word=0x00000001, ps=8, payload=35 00 00 00 ff ff ff ff
# ============================================================

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

print("=" * 60)
print("PORT 3000 LOGIN (faithful replica)")
print("=" * 60)

# Establish on TWO connections (channel 0 and channel 1) like the PCB tool
conns = []
for ch, unk in [(0, 0x0BB82002), (1, 0x0BB82002)]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, 3000))
        # SERVERCHS frame
        hdr = make_3000_login(0xA8C00001, unk, ch, 40)
        print("\nConn ch=%d: sending SERVERCHS" % ch)
        print("  hdr: %s" % hdr.hex())
        s.sendall(hdr)
        time.sleep(0.02)
        # 6B ack
        ack = recv_until_quiet(s, 0.5)
        print("  ack: %s" % ack.hex())
        # password payload
        print("  sending pwd: %s" % PWD_PAYLOAD.hex())
        s.sendall(PWD_PAYLOAD)
        # response
        resp = recv_until_quiet(s, 3)
        print("  resp(%dB): %s" % (len(resp), resp.hex()))
        conns.append(s)
    except Exception as e:
        print("  conn ch=%d error: %s" % (ch, e))
        try: s.close()
        except: pass
    time.sleep(0.05)

# Keep connections open and check for video
print("\nChecking for video data (keep open 5s)...")
for i, s in enumerate(conns):
    s.settimeout(3)
    try:
        while True:
            c = s.recv(65536)
            if not c: break
            print("  conn%d video data %dB: %s" % (i, len(c), c[:64].hex()))
    except socket.timeout:
        print("  conn%d: no more data (timeout)" % i)
    except Exception as e:
        print("  conn%d err: %s" % (i, e))

for s in conns:
    try: s.close()
    except: pass
print("\nDONE")
