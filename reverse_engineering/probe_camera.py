"""Probe the camera with different command frames to find the login sequence."""
import socket, struct, time, sys

CAM = "192.168.2.32"
PORT = 3000
TIMEOUT = 5

MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

def build_frame(cmd, channel=0, payload=b''):
    """Build a 48-byte command frame with optional payload."""
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, len(payload))
    struct.pack_into('<I', frame, 0x2C, MAGIC2)
    return bytes(frame) + payload

def recv_all(sock, timeout=3):
    """Receive all available data with timeout."""
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
    except Exception as e:
        print("  recv error:", e)
    return data

def describe_frame(data):
    """Describe a received frame."""
    if len(data) < 48:
        return "short (%d bytes): %s" % (len(data), data.hex())
    m1 = struct.unpack_from('<I', data, 0)[0]
    m2 = struct.unpack_from('<I', data, 0x2C)[0] if len(data) >= 0x30 else 0
    cmd = struct.unpack_from('<I', data, 0x1C)[0] if len(data) >= 0x20 else 0
    ch = struct.unpack_from('<I', data, 0x24)[0] if len(data) >= 0x28 else 0
    ps = struct.unpack_from('<I', data, 0x28)[0] if len(data) >= 0x2C else 0
    return "48B: m1=%08X cmd=%08X ch=%d ps=%d m2=%08X | rest=%s" % (
        m1, cmd, ch, ps, m2, data[0x30:0x40].hex() if len(data) > 0x30 else "")

def probe(name, cmd, channel=0, payload=b''):
    """Connect, optionally read greeting, send command, read response."""
    print("\n=== %s (cmd=%d/0x%X, ch=%d, payload=%d bytes) ===" % (name, cmd, cmd, channel, len(payload)))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((CAM, PORT))
        print("  Connected.")
        
        # Check for greeting
        try:
            greeting = s.recv(4096)
            if greeting:
                print("  Greeting (%d bytes): %s" % (len(greeting), greeting[:64].hex()))
            else:
                print("  No greeting (empty)")
        except socket.timeout:
            print("  No greeting (timeout)")
        
        # Send command
        frame = build_frame(cmd, channel, payload)
        print("  Sending: %s" % frame.hex())
        s.sendall(frame)
        time.sleep(0.5)
        
        # Read response
        resp = recv_all(s, timeout=3)
        if resp:
            print("  Response (%d bytes): %s" % (len(resp), resp[:128].hex()))
            print("  Described: %s" % describe_frame(resp))
        else:
            print("  No response")
    except Exception as e:
        print("  Error:", e)
    finally:
        s.close()

# Test 1: Just keepalive (cmd=5)
probe("keepalive", 5)

# Test 2: SERVERCHS (cmd=1) 
probe("SERVERCHS", 1)

# Test 3: AFFIRMUSER (cmd=21) with no payload
probe("AFFIRMUSER no payload", 21)

# Test 4: AFFIRMUSER (cmd=21) with "admin" payload
probe("AFFIRMUSER admin", 21, payload=b'admin\x00')

# Test 5: AFFIRMUSER (cmd=21) with larger payload (maybe username+password)
probe("AFFIRMUSER admin/admin", 21, payload=b'admin\x00admin\x00')

# Test 6: CONNECTIP (cmd=3)
probe("CONNECTIP", 3)

# Test 7: Just connect, no command, read greeting
print("\n=== connect only ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect((CAM, PORT))
    print("  Connected. Waiting for greeting...")
    resp = recv_all(s, timeout=5)
    if resp:
        print("  Greeting (%d bytes): %s" % (len(resp), resp[:128].hex()))
    else:
        print("  No greeting (5s timeout)")
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# Test 8: Send keepalive THEN AFFIRMUSER
print("\n=== keepalive then AFFIRMUSER ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((CAM, PORT))
    print("  Connected.")
    
    # Read any greeting
    try:
        g = s.recv(4096)
        if g:
            print("  Greeting: %s" % g[:64].hex())
    except socket.timeout:
        pass
    
    # Send keepalive
    ka = build_frame(5, 0)
    s.sendall(ka)
    print("  Sent keepalive")
    time.sleep(0.3)
    
    # Read keepalive response
    resp = recv_all(s, timeout=1)
    if resp:
        print("  KA response (%d bytes): %s" % (len(resp), resp[:64].hex()))
    
    # Send AFFIRMUSER
    af = build_frame(21, 0)
    s.sendall(af)
    print("  Sent AFFIRMUSER")
    time.sleep(0.5)
    
    resp = recv_all(s, timeout=3)
    if resp:
        print("  AFFIRMUSER response (%d bytes): %s" % (len(resp), resp[:128].hex()))
    else:
        print("  No AFFIRMUSER response")
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

# Test 9: Try on port 3001 too
print("\n=== AFFIRMUSER on port 3001 ===")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((CAM, 3001))
    print("  Connected to 3001.")
    af = build_frame(21, 0)
    s.sendall(af)
    print("  Sent AFFIRMUSER")
    resp = recv_all(s, timeout=3)
    if resp:
        print("  Response (%d bytes): %s" % (len(resp), resp[:128].hex()))
    else:
        print("  No response")
except Exception as e:
    print("  Error:", e)
finally:
    s.close()

print("\n=== DONE ===")
