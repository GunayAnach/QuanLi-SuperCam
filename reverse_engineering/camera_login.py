"""Full camera login replicating exact PCB tool sequence."""
import socket, struct, time, sys

CAM = "192.168.2.32"
PORT = 3000
PORT_CMD = 3001
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321
PC_IP = "192.168.2.43"  # Our client IP

def get_ip_words(ip_str):
    parts = [int(x) for x in ip_str.split('.')]
    hi = (parts[0] << 8) | parts[1]  # C0 A8 = 192.168
    return hi

def build_48frame(cmd_word, channel=0, payload_size=0):
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd_word)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, payload_size)
    struct.pack_into('<I', frame, 0x2C, MAGIC2)
    return bytes(frame)

def build_88frame(cmd_word, channel=0, payload_size=0):
    frame = bytearray(0x58)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd_word)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, payload_size)
    struct.pack_into('<I', frame, 0x54, MAGIC2)
    return bytes(frame)

def recv_all(sock, timeout=3):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            time.sleep(0.05)
    except socket.timeout:
        pass
    except:
        pass
    return data

def dump(data, label=""):
    if not data:
        return "  [%s] EMPTY" % label
    lines = ["  [%s] %dB: %s" % (label, len(data), data[:64].hex())]
    if len(data) >= 0x30:
        m1 = struct.unpack_from('<I', data, 0)[0]
        cmd = struct.unpack_from('<I', data, 0x1C)[0] if len(data) >= 0x20 else 0
        ps = struct.unpack_from('<I', data, 0x28)[0] if len(data) >= 0x2C else 0
        lines.append("    m1=0x%08X cmd=0x%08X ps=%d" % (m1, cmd, ps))
    return "\n".join(lines)

ip_hi = get_ip_words(PC_IP)
print("Client IP high word: 0x%04X" % ip_hi)

# === STEP 1: Port 3001 command handshake ===
print("\n=== STEP 1: Port 3001 command handshake ===")
for ch in range(4):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((CAM, PORT_CMD))
        cmd_word = 0x38383838  # "8888" ASCII
        frame88 = build_88frame(cmd_word, channel=ch)
        print("\n  Channel %d: Sending 88B frame cmd=0x%08X" % (ch, cmd_word))
        s.sendall(frame88)
        resp = recv_all(s, timeout=3)
        print(dump(resp, "RESP channel %d" % ch))
        if len(resp) > 88:
            print("    payload: %s" % resp[88:].hex())
    except Exception as e:
        print("  Error: %s" % e)
    finally:
        s.close()
    time.sleep(0.1)

# === STEP 2: Port 3001 config commands ===
print("\n=== STEP 2: Port 3001 config ===")
for ch_cfg, chan_num, val in [(2, 2, 0x36), (4, 4, 0x35)]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((CAM, PORT_CMD))
        # Send 88B handshake first
        frame88 = build_88frame(0x38383838, channel=0)
        s.sendall(frame88)
        resp = recv_all(s, timeout=1)
        # Now send 16B config
        cfg = struct.pack('<IIII', 3, ch_cfg, val, 0xBB8)
        print("  Sending config: cmd=%d chan=%d val=%d port=%d" % (3, ch_cfg, val, 0xBB8))
        s.sendall(cfg)
        resp = recv_all(s, timeout=2)
        print(dump(resp, "CFG_RESP"))
    except Exception as e:
        print("  Error: %s" % e)
    finally:
        s.close()
    time.sleep(0.1)

# === STEP 3: Port 3000 login (per channel) ===
print("\n=== STEP 3: Port 3000 login ===")
password = b'888888\x00' + b'\xcc' * 33  # 40 bytes total

for ch in range(1):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((CAM, PORT))
        
        # Build SERVERCHS with client IP in cmd_word
        cmd_word_serverchs = (ip_hi << 16) | 0x01  # e.g., 0xA8C00001
        frame = build_48frame(cmd_word_serverchs, channel=0, payload_size=len(password))
        print("\n  Channel %d: Sending SERVERCHS cmd=0x%08X" % (ch, cmd_word_serverchs))
        s.sendall(frame)
        
        # Wait for 6B ACK
        time.sleep(0.05)
        
        # Send password
        print("  Sending %d-byte password" % len(password))
        s.sendall(password)
        
        # Read response
        resp = recv_all(s, timeout=3)
        print(dump(resp, "LOGIN_RESP"))
        
        if len(resp) >= 0x30:
            cmd = struct.unpack_from('<I', resp, 0x1C)[0]
            print("  Response cmd=0x%08X (echo=%d)" % (cmd, cmd & 0xFF))
            
            # If login worked, try sending CLEANALARM
            if True:
                # CLEANALARM (cmd=2)
                clean_frame = build_48frame(0xCCCC0002, channel=0, payload_size=8)
                s.sendall(clean_frame)
                clean_payload = struct.pack('<II', 0x35 + ch, 1)
                s.sendall(clean_payload)
                resp2 = recv_all(s, timeout=3)
                print(dump(resp2, "CLEANALARM_RESP"))
                
                # GETSERIALNO (cmd=20=0x14)
                serial_frame = build_48frame(0xCCCC0014, channel=0, payload_size=0)
                s.sendall(serial_frame)
                resp3 = recv_all(s, timeout=3)
                print(dump(resp3, "SERIAL_RESP"))
    except Exception as e:
        print("  Error: %s" % e)
    finally:
        s.close()
    time.sleep(0.1)

print("\n=== DONE ===")
