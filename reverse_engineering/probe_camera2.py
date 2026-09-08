"""Deeper protocol probe: test all ports, look for 88-byte greeting, try login sequence."""
import socket, struct, time

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

def build_frame(cmd, channel=0, payload=b''):
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, len(payload))
    struct.pack_into('<I', frame, 0x2C, MAGIC2)
    return bytes(frame) + payload

def recv_available(sock, timeout=3):
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

def describe_response(data):
    if len(data) < 4:
        return "too short: %d bytes" % len(data)
    if len(data) >= 0x30:
        m1 = struct.unpack_from('<I', data, 0)[0]
        cmd = struct.unpack_from('<I', data, 0x1C)[0]
        ch = struct.unpack_from('<I', data, 0x24)[0]
        ps = struct.unpack_from('<I', data, 0x28)[0]
        m2 = struct.unpack_from('<I', data, 0x2C)[0]
        is_magic = (m1 == MAGIC1 and m2 == MAGIC2)
        status = (cmd >> 8) & 0xFF
        echo_cmd = cmd & 0xFF
        return "48B magic=%s cmd=0x%08X echo_cmd=%d(0x%02X) status=0x%02X ch=%d ps=%d" % (
            is_magic, cmd, echo_cmd, echo_cmd, status, ch, ps)
    # Check for NAL
    if data[:4] == b'\x00\x00\x00\x01':
        nal_type = data[4] & 0x1F if len(data) > 4 else -1
        return "H.264 NAL type=%d, %d bytes" % (nal_type, len(data))
    if data[:3] == b'\x00\x00\x01':
        return "H.264 start code, %d bytes" % len(data)
    return "unknown: %d bytes, first 16: %s" % (len(data), data[:16].hex())

# ================================================================
# TEST A: Port 3000 - connect, wait 10s for greeting
# ================================================================
print("\n=== A: Port 3000, long wait for greeting ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3000))
    print("  Connected. Waiting 10s for greeting...")
    resp = recv_available(s, timeout=10)
    print("  Result: %s" % describe_response(resp))
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST B: Port 3001 - connect, wait 10s for greeting
# ================================================================
print("\n=== B: Port 3001, long wait for greeting ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3001))
    print("  Connected. Waiting 10s for greeting...")
    resp = recv_available(s, timeout=10)
    print("  Result: %s" % describe_response(resp))
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST C: Port 3001 - send keepalive, then more commands
# ================================================================
print("\n=== C: Port 3001 - keepalive then commands ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3001))
    print("  Connected to 3001.")
    
    # Send keepalive
    s.sendall(build_frame(5, 0))
    resp = recv_available(s, timeout=2)
    print("  keepalive resp: %s" % describe_response(resp))
    
    # Send SERVERCHS
    s.sendall(build_frame(1, 0))
    resp = recv_available(s, timeout=2)
    print("  SERVERCHS resp: %s" % describe_response(resp))
    
    # Send AFFIRMUSER
    s.sendall(build_frame(21, 0))
    resp = recv_available(s, timeout=2)
    print("  AFFIRMUSER resp: %s" % describe_response(resp))
    
    # Send GETSYSUSER (cmd=22)
    s.sendall(build_frame(22, 0))
    resp = recv_available(s, timeout=2)
    print("  GETSYSUSER resp: %s" % describe_response(resp))
    
    # Wait for video
    print("  Waiting 5s for any stream data...")
    resp = recv_available(s, timeout=5)
    if resp:
        print("  Stream data: %s" % describe_response(resp))
    else:
        print("  No data")
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST D: Port 3000 - multi-command sequence
# ================================================================
print("\n=== D: Port 3000 - full command sequence ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3000))
    print("  Connected to 3000.")
    
    # Try: keepalive → wait → read
    s.sendall(build_frame(5, 0))
    resp = recv_available(s, timeout=1)
    print("  keepalive: %s" % describe_response(resp))
    
    # Try to get channel params
    s.sendall(build_frame(8, 0))  # GETCHANNELPARAM
    resp = recv_available(s, timeout=1)
    print("  GETCHANNELPARAM: %s" % describe_response(resp))
    
    # Try GETSUBCHANNELPARAM
    s.sendall(build_frame(34, 0))
    resp = recv_available(s, timeout=1)
    print("  GETSUBCHANNELPARAM: %s" % describe_response(resp))
    
    # Wait for data
    print("  Waiting 5s...")
    resp = recv_available(s, timeout=5)
    if resp:
        print("  Got: %s" % describe_response(resp))
    else:
        print("  No data")
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST E: Port 3001 - try SERVERCHS with channel=1, then AFFIRMUSER
# ================================================================
print("\n=== E: Port 3001 - SERVERCHS(ch=1) then AFFIRMUSER(ch=1) ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3001))
    print("  Connected to 3001.")
    
    # SERVERCHS with different channels
    for ch in [0, 1]:
        s.sendall(build_frame(1, ch))
        resp = recv_available(s, timeout=2)
        print("  SERVERCHS(ch=%d): %s" % (ch, describe_response(resp)))
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST F: Port 3000 - send ALL commands 1-50 quickly, see which get responses
# ================================================================
print("\n=== F: Port 3000 - scan commands 1-50 ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3000))
    print("  Connected to 3000.")
    for cmd in range(1, 51):
        s.sendall(build_frame(cmd, 0))
        resp = recv_available(s, timeout=0.3)
        if resp:
            r = describe_response(resp)
            if "48B" in r:
                # Extract status
                echo = struct.unpack_from('<I', resp, 0x1C)[0] & 0xFF
                status = (struct.unpack_from('<I', resp, 0x1C)[0] >> 8) & 0xFF
                print("  cmd %2d(0x%02X): status=0x%02X echo=%d" % (cmd, cmd, status, echo))
            else:
                print("  cmd %2d(0x%02X): %s" % (cmd, cmd, r))
        else:
            print("  cmd %2d(0x%02X): NO RESPONSE" % (cmd, cmd))
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# ================================================================
# TEST G: Port 3000 - send SERVERCHS first (to set state), then other commands
# ================================================================
print("\n=== G: Port 3000 - SERVERCHS first, then scan ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, 3000))
    print("  Connected to 3000.")
    
    # First: SERVERCHS
    s.sendall(build_frame(1, 0))
    resp = recv_available(s, timeout=2)
    print("  SERVERCHS: %s" % describe_response(resp))
    
    # Then: AFFIRMUSER with different payloads
    for payload_name, payload in [
        ("empty", b''),
        ("admin\\0", b'admin\x00'),
        ("admin\\0\\0", b'admin\x00\x00'),
        ("admin\\01234\\0", b'admin\x001234\x00'),
        ("\\x01\\x00\\x00\\x00", b'\x01\x00\x00\x00'),
        ("struct 48B", b'\x00'*44),
    ]:
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.settimeout(1)
        try:
            s2.connect((CAM, 3000))
            # Send SERVERCHS first
            s2.sendall(build_frame(1, 0))
            recv_available(s2, timeout=0.5)
            # Then AFFIRMUSER with payload
            s2.sendall(build_frame(21, 0, payload))
            resp = recv_available(s2, timeout=2)
            print("  AFFIRMUSER(%s): %s" % (payload_name, describe_response(resp)))
        except Exception as e:
            print("  AFFIRMUSER(%s): Error %s" % (payload_name, e))
        finally:
            s2.close()
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

print("\n=== ALL TESTS DONE ===")
