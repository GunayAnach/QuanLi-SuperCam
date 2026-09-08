"""Focused probe: send commands one at a time with proper delays."""
import socket, struct, time, sys

CAM = "192.168.2.32"; PORT = 3000
M1 = 0x123AB678; M2 = 0x876CD321

def bf(cmd, ch=0, pl=b''):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1); struct.pack_into('<I', f, 0x1C, cmd)
    struct.pack_into('<I', f, 0x24, ch); struct.pack_into('<I', f, 0x28, len(pl))
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f) + pl

def rcv_frame(sock, timeout=10):
    """Read until we get a 48-byte magic frame, skipping 6-byte zero markers."""
    sock.settimeout(timeout)
    data = b''
    start = time.time()
    while time.time() - start < timeout:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
        except:
            break
        # Check if we have a complete frame
        pos = 0
        while pos + 0x30 <= len(data):
            if data[pos:pos+4] == struct.pack('<I', M1):
                m2 = struct.unpack_from('<I', data, pos+0x2C)[0]
                if m2 == M2:
                    ps = struct.unpack_from('<I', data, pos+0x28)[0]
                    end = pos + 0x30 + ps
                    if len(data) >= end:
                        return data[pos:end]
            pos += 1
    return data

def send_and_recv(cmd, ch=0, pl=b'', timeout=10):
    """Connect, send one command, return response frame."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((CAM, PORT))
        s.sendall(bf(cmd, ch, pl))
        time.sleep(0.1)  # Give camera time to process
        resp = rcv_frame(s, timeout=timeout)
        if len(resp) >= 0x30:
            cmd_word = struct.unpack_from('<I', resp, 0x1C)[0]
            ps = struct.unpack_from('<I', resp, 0x28)[0]
            payload = resp[0x30:0x30+ps] if ps > 0 else b''
            return cmd_word, ps, payload, len(resp)
        return 0, 0, resp, len(resp)
    except Exception as e:
        return -1, 0, str(e).encode(), 0
    finally:
        s.close()

# Wait for camera to be idle
print("Waiting 30s for camera to be idle...")
time.sleep(30)

# ================================================================
# TEST 1: Key commands with 10s timeout each
# ================================================================
print("=" * 60)
print("TEST 1: Key commands (10s timeout each)")
print("=" * 60)

key_cmds = [
    (1, "SERVERCHS"),
    (5, "keepalive"),
    (6, "GETGLOBALPARAM"),
    (8, "GETCHANNELPARAM"),
    (16, "GETSERIAL"),
    (20, "GETSERIALNO"),
    (21, "AFFIRMUSER"),
    (22, "GETSYSUSER"),
    (34, "GETSUBCHANNELPARAM"),
    (90, "GETVIEWPARAM"),
    (103, "GETENCODETYPE"),
    (157, "GET_COLORPALETTE"),
    (159, "GET_TEMPPARAM"),
    (161, "GET_AGCPARAM"),
    (170, "GET_GETTEMPVALUE"),
    (171, "GET_IMAGEFUSEPARAM"),
    (187, "GETREGIONTEMPINFOLIST"),
]

for cmd, name in key_cmds:
    cw, ps, payload, total = send_and_recv(cmd, timeout=10)
    if cw > 0:
        echo = cw & 0xFF
        print("  %3d(0x%02X) %-25s: resp cmd=0x%08X ps=%d total=%d" % (
            cmd, cmd, name, cw, ps, total))
        if ps > 0:
            print("    payload(%d): %s" % (ps, payload[:128].hex()))
    else:
        print("  %3d(0x%02X) %-25s: NO RESP (raw=%d bytes: %s)" % (
            cmd, cmd, name, total, str(payload)[:40]))
    time.sleep(1)  # Wait between connections

# ================================================================
# TEST 2: Multi-command on same connection (with wait between commands)
# ================================================================
print("\n" + "=" * 60)
print("TEST 2: Multi-command on SAME connection (with 3s wait)")
print("=" * 60)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected.")

    cmds = [
        (1, "SERVERCHS"),
        (21, "AFFIRMUSER"),
        (5, "keepalive"),
        (8, "GETCHANNELPARAM"),
        (170, "GET_TEMPVALUE"),
    ]

    for cmd, name in cmds:
        s.sendall(bf(cmd, 0))
        print("  Sent %s(0x%02X). Waiting for response..." % (name, cmd))
        resp = rcv_frame(s, timeout=10)
        if len(resp) >= 0x30:
            cw = struct.unpack_from('<I', resp, 0x1C)[0]
            ps = struct.unpack_from('<I', resp, 0x28)[0]
            print("  Resp: cmd=0x%08X echo=%d ps=%d" % (cw, cw & 0xFF, ps))
            if ps > 0:
                payload = resp[0x30:0x30+ps]
                print("  PAYLOAD: %s" % payload[:128].hex())
        else:
            print("  Resp: %d bytes (not a frame): %s" % (len(resp), resp[:32].hex() if resp else "empty"))
        time.sleep(1)
except Exception as e:
    print("Error:", e)
finally:
    s.close()

# ================================================================
# TEST 3: AFFIRMUSER with different payloads on fresh connections
# ================================================================
print("\n" + "=" * 60)
print("TEST 3: AFFIRMUSER with different payloads")
print("=" * 60)

payloads = [
    ("empty", b''),
    ("admin", b'admin'),
    ("admin\\0", b'admin\x00'),
    ("admin\\0admin\\0", b'admin\x00admin\x00'),
    ("admin\\01234\\0", b'admin\x001234\x00'),
    ("admin\\0admin\\0\\x01", b'admin\x00admin\x00\x01'),
    ("4B:21,0,0,0", struct.pack('<IHH', 21, 0, 0)),
    ("4B:1,0,0,0", struct.pack('<IHH', 1, 0, 0)),
    ("8B:1,0,0,0,0,0,0,0", struct.pack('<II', 1, 0)),
    ("8B:21,0,0,0,0,0,0,0", struct.pack('<II', 21, 0)),
]

for name, payload in payloads:
    cw, ps, resp_payload, total = send_and_recv(21, pl=payload, timeout=10)
    if cw > 0:
        print("  AFFIRMUSER(%s, %dB): cmd=0x%08X ps=%d" % (name, len(payload), cw, ps))
        if ps > 0:
            print("    resp payload: %s" % resp_payload[:128].hex())
    else:
        print("  AFFIRMUSER(%s, %dB): NO RESP" % (name, len(payload)))
    time.sleep(1)

print("\n=== ALL DONE ===")
