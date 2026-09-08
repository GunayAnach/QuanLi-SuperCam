"""Fresh-connection probe: tests 4-6 only (camera is free)."""
import socket, struct, time

CAM = "192.168.2.32"
PORT = 3000
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

def recv_timeout(sock, timeout=5):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk: break
            data += chunk
    except socket.timeout:
        pass
    except: pass
    return data

def dump_frame(data, label=""):
    if len(data) == 0:
        return "  [%s] EMPTY" % label
    if len(data) >= 0x30:
        cmd = struct.unpack_from('<I', data, 0x1C)[0]
        ps = struct.unpack_from('<I', data, 0x28)[0]
        echo = cmd & 0xFF
        lines = ["  [%s] %d bytes cmd=0x%08X echo=%d ps=%d" % (label, len(data), cmd, echo, ps)]
        if ps > 0 and len(data) > 0x30:
            lines.append("    payload(%d): %s" % (ps, data[0x30:0x30+min(ps,128)].hex()))
        if len(data) > 0x30 + ps:
            lines.append("    extra(%d): %s" % (len(data)-0x30-ps, data[0x30+ps:0x30+ps+64].hex()))
        return "\n".join(lines)
    lines = ["  [%s] %d bytes: %s" % (label, len(data), data[:128].hex())]
    return "\n".join(lines)

# TEST 4: SERVERCHS then AFFIRMUSER with various auth data
print("=" * 60)
print("TEST 4: SERVERCHS then AFFIRMUSER with auth payloads")
print("=" * 60)

auth_payloads = [
    ("empty", b''),
    ("admin_only", b'admin'),
    ("admin_null", b'admin\x00'),
    ("admin_pwd", b'admin\x00admin\x00'),
    ("admin_pwd123", b'admin\x0012345\x00'),
    ("int_1", struct.pack('<I', 1)),
    ("int_21", struct.pack('<I', 21)),
    ("48zeros", b'\x00'*48),
    ("ff_48", b'\xff'*48),
    ("admin_binary", b'admin\x00\x01\x00\x00\x00'),
]

for name, payload in auth_payloads:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((CAM, PORT))
        s.sendall(build_frame(1, 0))
        resp = recv_timeout(s, timeout=1)
        s.sendall(build_frame(21, 0, payload))
        resp = recv_timeout(s, timeout=2)
        print(dump_frame(resp, "AFFIRMUSER(%s, %dB)" % (name, len(payload))))
    except Exception as e:
        print("  [AFFIRMUSER(%s)] Error: %s" % (name, e))
    finally:
        s.close()
    time.sleep(0.2)

# TEST 5: Connect and wait 30s with no commands
print("\n" + "=" * 60)
print("TEST 5: Connect, no commands, wait 30s")
print("=" * 60)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected. Waiting 30s...")
    data = recv_timeout(s, timeout=30)
    print(dump_frame(data, "30s wait"))
except Exception as e:
    print("Error:", e)
finally:
    s.close()

time.sleep(1)

# TEST 6: Scan ALL commands 1-219
print("\n" + "=" * 60)
print("TEST 6: Scan ALL commands 1-219 (fresh conn each)")
print("=" * 60)

results = {}
for cmd in range(1, 220):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((CAM, PORT))
        s.sendall(build_frame(cmd, 0))
        resp = recv_timeout(s, timeout=1)
        if len(resp) >= 0x30:
            echo = struct.unpack_from('<I', resp, 0x1C)[0] & 0xFF
            ps = struct.unpack_from('<I', resp, 0x28)[0]
            results[cmd] = (len(resp), ps, echo)
            if ps > 0 or len(resp) != 48:
                print("  cmd %3d(0x%02X): %d bytes, ps=%d echo=%d" % (cmd, cmd, len(resp), ps, echo))
        elif len(resp) > 0:
            results[cmd] = (len(resp), 0, -1)
            print("  cmd %3d(0x%02X): %d bytes non-frame: %s" % (cmd, cmd, len(resp), resp[:32].hex()))
        else:
            results[cmd] = (0, 0, 0)
    except Exception as e:
        results[cmd] = (-1, 0, 0)
        print("  cmd %3d(0x%02X): ERROR %s" % (cmd, cmd, str(e)[:60]))
    finally:
        s.close()
    time.sleep(0.05)

# Interesting commands summary
print("\n--- INTERESTING RESULTS ---")
for cmd in sorted(results.keys()):
    total, ps, echo = results[cmd]
    if ps > 0 or total > 48 or total == 0 or total == -1:
        print("  cmd %3d(0x%02X): %d bytes, ps=%d" % (cmd, cmd, total, ps))

print("\n=== DONE ===")
