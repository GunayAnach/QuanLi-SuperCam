"""Command scan with LONG timeouts (camera has 3-6s response delay)."""
import socket, struct, time, sys

CAM = "192.168.2.32"; PORT = 3000
M1 = 0x123AB678; M2 = 0x876CD321

def bf(cmd, ch=0, pl=b''):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1); struct.pack_into('<I', f, 0x1C, cmd)
    struct.pack_into('<I', f, 0x24, ch); struct.pack_into('<I', f, 0x28, len(pl))
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f) + pl

def rcv_all(sock, timeout=10):
    """Read all available data with long timeout, skip 6-byte zeros."""
    sock.settimeout(timeout)
    data = b''
    start = time.time()
    try:
        while time.time() - start < timeout:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            # If we got a 48-byte frame with matching magic, we're done
            if len(data) >= 0x30:
                m1 = struct.unpack_from('<I', data, 0)[0]
                m2 = struct.unpack_from('<I', data, 0x2C)[0]
                if m1 == M1 and m2 == M2:
                    break
    except socket.timeout:
        pass
    except:
        pass
    return data

def send_cmd(cmd, ch=0, pl=b'', timeout=12):
    """Connect, send command, wait for 48-byte response (may take 6+ seconds)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((CAM, PORT))
        s.sendall(bf(cmd, ch, pl))
        # Skip any 6-byte zero pre-responses, wait for 48-byte frame
        data = rcv_all(s, timeout=timeout)
        # Parse frames
        frames = []
        pos = 0
        while pos < len(data):
            if pos + 4 <= len(data) and data[pos:pos+4] == b'\x00\x00\x00\x00' and pos + 6 <= len(data) and data[pos:pos+6] == b'\x00\x00\x00\x00\x00\x00':
                pos += 6  # skip 6-byte zero marker
                continue
            if pos + 0x30 <= len(data):
                m1 = struct.unpack_from('<I', data, pos)[0]
                m2 = struct.unpack_from('<I', data, pos+0x2C)[0]
                if m1 == M1 and m2 == M2:
                    cmd_word = struct.unpack_from('<I', data, pos+0x1C)[0]
                    ch_val = struct.unpack_from('<I', data, pos+0x24)[0]
                    ps = struct.unpack_from('<I', data, pos+0x28)[0]
                    payload = data[pos+0x30:pos+0x30+ps] if ps > 0 else b''
                    frames.append((cmd_word, ch_val, ps, payload))
                    pos += 0x30 + ps
                    continue
            pos += 1
        return frames, data
    except Exception as e:
        return [], b''
    finally:
        s.close()

# ================================================================
# TEST 1: Scan all commands with 12s timeout each
# ================================================================
print("=" * 70)
print("TEST 1: Scan commands 1-219 with 12s timeout (camera has 3-6s delay)")
print("=" * 70)

interesting = []
for cmd in range(1, 220):
    frames, raw = send_cmd(cmd, timeout=12)
    if frames:
        for cmd_word, ch, ps, payload in frames:
            echo = cmd_word & 0xFF
            status = (cmd_word >> 8) & 0xFFFF
            if ps > 0:
                print("  cmd %3d(0x%02X): RESP cmd=0x%08X ps=%d payload=%s" % (
                    cmd, cmd, cmd_word, ps, payload[:64].hex()))
                interesting.append((cmd, cmd_word, ps, payload))
            elif cmd != echo:
                print("  cmd %3d(0x%02X): echo MISMATCH resp_echo=%d" % (cmd, cmd, echo))
            # else: normal echo, skip
    elif len(raw) > 0:
        print("  cmd %3d(0x%02X): raw %d bytes (no frame): %s" % (
            cmd, cmd, len(raw), raw[:32].hex()))
    else:
        print("  cmd %3d(0x%02X): NO RESPONSE" % (cmd, cmd))
    sys.stdout.flush()
    time.sleep(0.05)

print("\n--- INTERESTING: Commands with payloads ---")
for cmd, cmd_word, ps, payload in interesting:
    print("  cmd %3d(0x%02X): %d bytes payload: %s" % (cmd, cmd, ps, payload[:128].hex()))

# ================================================================
# TEST 2: Full login sequence on ONE connection with long waits
# ================================================================
print("\n" + "=" * 70)
print("TEST 2: Login sequence on ONE connection with long waits")
print("=" * 70)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected.")

    # Step 1: SERVERCHS
    s.sendall(bf(1, 0))
    print("Sent SERVERCHS. Waiting 10s...")
    r = rcv_all(s, timeout=10)
    print("Response: %d bytes" % len(r))
    if r and len(r) >= 0x30:
        cmd_word = struct.unpack_from('<I', r, 0x1C)[0]
        print("  cmd=0x%08X echo=%d" % (cmd_word, cmd_word & 0xFF))

    # Step 2: AFFIRMUSER with various payloads
    for name, payload in [
        ("empty", b''),
        ("admin\x00", b'admin\x00'),
        ("admin\x00admin\x00", b'admin\x00admin\x00'),
        ("int_21", struct.pack('<I', 21)),
    ]:
        s.sendall(bf(21, 0, payload))
        print("Sent AFFIRMUSER(%s). Waiting 10s..." % name)
        r = rcv_all(s, timeout=10)
        print("Response: %d bytes" % len(r))
        if r and len(r) >= 0x30:
            cmd_word = struct.unpack_from('<I', r, 0x1C)[0]
            ps = struct.unpack_from('<I', r, 0x28)[0]
            print("  cmd=0x%08X echo=%d ps=%d" % (cmd_word, cmd_word & 0xFF, ps))
            if ps > 0:
                print("  PAYLOAD: %s" % r[0x30:0x30+ps].hex())

    # Step 3: keepalive
    s.sendall(bf(5, 0))
    print("Sent keepalive. Waiting 10s...")
    r = rcv_all(s, timeout=10)
    print("Response: %d bytes" % len(r))

    # Step 4: GETCHANNELPARAM
    s.sendall(bf(8, 0))
    print("Sent GETCHANNELPARAM. Waiting 10s...")
    r = rcv_all(s, timeout=10)
    print("Response: %d bytes" % len(r))
    if r and len(r) >= 0x30:
        cmd_word = struct.unpack_from('<I', r, 0x1C)[0]
        ps = struct.unpack_from('<I', r, 0x28)[0]
        print("  cmd=0x%08X ps=%d" % (cmd_word, ps))
        if ps > 0:
            print("  PAYLOAD: %s" % r[0x30:0x30+ps].hex())

    # Step 5: Wait for any streaming data
    print("Waiting 15s for any streaming...")
    r = rcv_all(s, timeout=15)
    print("Stream data: %d bytes" % len(r))
    if r:
        print("  First 128 bytes: %s" % r[:128].hex())

except Exception as e:
    print("Error:", e)
finally:
    s.close()

# ================================================================
# TEST 3: Connect, send keepalive, then wait 30s for streaming push
# ================================================================
print("\n" + "=" * 70)
print("TEST 3: keepalive + 30s wait for streaming push")
print("=" * 70)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected.")
    s.sendall(bf(5, 0))
    r = rcv_all(s, timeout=5)
    print("KA response: %d bytes" % len(r))
    print("Waiting 30s for push data...")
    r = rcv_all(s, timeout=30)
    print("Push data: %d bytes" % len(r))
    if r:
        print("  First 128 bytes: %s" % r[:128].hex())
except Exception as e:
    print("Error:", e)
finally:
    s.close()

print("\n=== ALL DONE ===")
