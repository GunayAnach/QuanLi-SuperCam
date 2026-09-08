"""Faithful replica of PCB tool login - based on captured wire data.

Two stream channels: vis (camera/visible) and ir (infrared).
This implements the vis (camera) login sequence from the capture.
"""
import socket, struct, time, threading, sys, os

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321
USERNAME = b"video server\x00"    # 13 bytes: "video server" + NUL
PASSWORD = b"888888\x00"          # password for 3001 setup
# Password payload for 3000 = username+password fields
# From capture #21/#22: "888888\0" + "888888\0" + CC padding
PASSWORD3000 = b"888888\x00" + b"888888\x00" + b"\xcc" * 24  # 40 bytes
# From capture #22: 38 38 38 38 38 38 00 cc cc cc cc cc cc cc cc cc cc cc cc 38 38 38 38 38 38 00 cc cc cc cc cc cc cc cc cc cc cc cc
# That's "888888\0" + 11 CC + "888888\0" + 13 CC = 7+11+7+13 = 38... need exact 40
# Capture #22 hex: 38 38 38 38 38 38 00 | cc cc cc cc cc cc cc cc cc cc cc cc | 38 38 38 38 38 38 00 | cc cc cc cc cc cc cc cc cc cc cc cc
# 7 + 12 + 7 + 12 = 38 bytes. But header says 40B. The 4th line shows 8 more CC? Let me recheck.

# Actually line 0030 of #21: "cc cc cc cc cc cc cc cc" = 8 bytes -> total 7+12+7+12+8 = 46? 
# Frame #21 said 40B. Header ps=0x28=40. Let me build exactly 40: "888888\0"(7) + CC*12 + "888888\0"(7) + CC*14 = 40
PASSWORD3000 = b"888888\x00" + b"\xcc"*12 + b"888888\x00" + b"\xcc"*14

def dump(name, data):
    return "%s(%dB): %s" % (name, len(data), data.hex())

def build_port3000_login(cmd, channel=0, ps=0):
    """48-byte frame for port 3000. From capture #17/#18."""
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    # offset 0x04: username "video server\0"
    frame[0x04] = ord('v')  # placeholder, set below
    # Actually from capture #17, offset 0x04 = "video server\0" then CC padding
    return frame

# Let me rebuild from exact capture bytes instead
# Frame #17 (48B, C2S port 3000, SERVERCHS for channel 0x0000):
# 78 b6 3a 12 76 69 64 65 6f 20 73 65 72 76 65 72 (video server)
# 00 cc cc cc cc cc cc cc cc cc cc cc 01 00 c0 a8
# 02 20 b8 0b 00 00 00 00 28 00 00 00 21 d3 6c 87
FRAME17 = bytes.fromhex(
    "78b63a12" +          # MAGIC1
    "766964656f20736572766572" +  # "video server"
    "00" +                 # \0
    "cccccccccc" +         # wait, need to count
    ""
)

# Let me just construct programmatically

def port3000_header(cmd_word, channel, port_src=3000, ps=0):
    """Build 48B header matching capture #17.
    Layout:
      0x00: MAGIC1
      0x04: "video server\0" + CC*11  (offset 0x04..0x1B = 24 bytes)
      0x1C: cmd_word (uint32 LE)
      0x20: ?? (in #17 = 02 20 b8 0b ; in control cmds = cccc..)
      0x24: channel (uint32 LE)
      0x28: payload size (uint32 LE)
      0x2C: MAGIC2
    """
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    frame[0x04:0x11] = USERNAME  # 13 bytes
    frame[0x11:0x1C] = b"\xcc" * 0x0B  # 11 bytes -> 0x04..0x1B filled
    struct.pack_into('<I', frame, 0x1C, cmd_word)
    struct.pack_into('<I', frame, 0x20, 0x0BB80202 if False else 0x0BB80202)
    # In #17 offset 0x20 = 02 20 b8 0b = 0x0BB80202? little endian: 02 20 b8 0b = 0x0BB82002
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, ps)
    struct.pack_into('<I', frame, 0x2C, MAGIC2)
    return bytes(frame)

# Simpler: use exact captured frames as templates
FRAME17 = bytes.fromhex(
    "78b63a12"               # MAGIC1
    "766964656f20736572766572"  # "video server"
    "00"
    "ccccccccccc"            # 11 CCs? total has to make offset 0x1C
)

# I'll just byte-fill precisely
def make_3000_frame(cmd_word, ch, ps):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, MAGIC1)
    f[4:17] = USERNAME           # "video server\0" 13 bytes -> offset 4..16
    f[17:28] = b'\xcc' * 11      # offset 17..27 = 11 bytes -> offset 4..27 filled
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, 0x0BB82002)  # matches 02 20 b8 0b
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

def make_3000_control(cmd_word, ch, ps):
    """Control frame - CC padding, like #27/31/48/56."""
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, MAGIC1)
    f[4:28] = b'\xcc' * 24
    struct.pack_into('<I', f, 0x1C, cmd_word)
    struct.pack_into('<I', f, 0x20, 0xCCCCCCCC)
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

def make_3001_handshake(ch):
    """88-byte frame from capture #1/#2 for port 3001."""
    f = bytearray(0x58)
    struct.pack_into('<I', f, 0, MAGIC1)
    f[4:17] = USERNAME           # "video server\0"
    f[17:28] = b'\x00' * 11
    f[0x14:0x18] = b"8888"       # offset 0x14 = "8888"
    f[0x18:0x1C] = b'\x00' * 4
    f[0x20:0x27] = b"888888\x00"
    f[0x27:0x30] = b'\x00' * 9   # fill to 0x30
    f[0x30:0x37] = b"888888\x00"
    f[0x37:0x44] = b'\x00' * 13
    # cmd byte at 0x44 (offset 0x44 = after 0x40)
    # From capture: offset 0x44 = 0x65 or 0x66 etc (request type)
    # offset 0x50 = request, offset 0x54 = MAGIC2
    struct.pack_into('<I', f, 0x54, MAGIC2)
    return bytes(f)

def recv_any(sock, timeout=3):
    sock.settimeout(timeout)
    try:
        return sock.recv(65536)
    except:
        return b''

def recv_until_quiet(sock, timeout=2, min_bytes=0):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    except:
        pass
    return data

print("=" * 60)
print("CAMERA LOGIN REPLICA")
print("=" * 60)

# =========================================================
# PHASE A: Port 3001 handshakes (must happen first)
# =========================================================
print("\n[Phase A] Port 3001 handshakes")
conn3001 = []
for ch in [0x65, 0x66, 0x78, 0x90]:  # from capture 0x65,0x66,0x78,0x90
    pass

# From capture, the 3001 handshakes are on separate connections with
# request codes 0x65, 0x65, 0x66, 0x66, 0x78, 0x90
# Then config commands. Let me replicate just the essentials.

# Actually, let me replicate the EXACT port 3000 login since that's what
# triggers video. The 3001 stuff is for config/discovery.

# =========================================================
# PHASE B: Port 3000 login (the critical part)
# =========================================================
print("\n[Phase B] Port 3000 login (2 connections)")

serverchs_cmd = 0xA8C00001  # from capture #17 (01 00 c0 a8)

def do_login_connection():
    """Replicate connection #17/#18: SERVERCHS + password."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((CAM, 3000))

    # Send SERVERCHS 48B frame with username in header, ps=40
    hdr = make_3000_frame(serverchs_cmd, 0, 40)
    print("  Sending SERVERCHS:", dump("hdr", hdr))
    s.sendall(hdr)
    time.sleep(0.02)

    # Send 40B password payload
    print("  Sending password:", dump("pwd", PASSWORD3000))
    s.sendall(PASSWORD3000)

    # Read response
    resp = recv_until_quiet(s, timeout=3)
    print("  Response:", dump("resp", resp))
    return s

# Original capture does 2 connections with different channel values (0x0000 and 0x0001)
# conn1 = port 62562 -> channel 0, conn2 = port 62563 -> channel 1

s1 = do_login_connection()
# keep these open
print("  Login connection 1 open:", s1.fileno())

# Let's try the ping/keepalive on the login connection and see if video starts
time.sleep(2)
try:
    data = s1.recv(65536)
    if data:
        print("  Data on login conn:", dump("video?", data[:200]))
except:
    pass

s1.close()
print("\nDONE")
