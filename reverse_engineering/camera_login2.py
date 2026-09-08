"""Full camera login - exact PCB tool sequence replication."""
import socket, struct, time

CAM = "192.168.2.32"
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321
PC_IP_OCTS = [int(x) for x in "192.168.2.43".split('.')]
PASSWORD = b'888888\x00' + b'\xcc' * 33  # 40 bytes

# PCB tool cmd_word for SERVERCHS: 0xA8C00001
# LE bytes: 01 00 C0 A8
# byte[0]=cmd=1, byte[2]=192(C0), byte[3]=168(A8)
SERVERCHS_CMD_WORD = (PC_IP_OCTS[1] << 24) | (PC_IP_OCTS[0] << 16) | 0x01
print("SERVERCHS cmd_word: 0x%08X (LE: %s)" % (SERVERCHS_CMD_WORD, SERVERCHS_CMD_WORD.to_bytes(4,'little').hex()))

def build_88frame(cmd_word, channel=0):
    frame = bytearray(0x58)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd_word)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, 0)
    struct.pack_into('<I', frame, 0x54, MAGIC2)
    return bytes(frame)

def build_48frame(cmd_word, channel=0, payload_size=0):
    frame = bytearray(0x30)
    struct.pack_into('<I', frame, 0x00, MAGIC1)
    struct.pack_into('<I', frame, 0x1C, cmd_word)
    struct.pack_into('<I', frame, 0x24, channel)
    struct.pack_into('<I', frame, 0x28, payload_size)
    struct.pack_into('<I', frame, 0x2C, MAGIC2)
    return bytes(frame)

def recv_full(sock, timeout=3):
    sock.settimeout(timeout)
    data = b''
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk: break
            data += chunk
            time.sleep(0.02)
    except socket.timeout: pass
    except: pass
    return data

def dump(data, label=""):
    if not data: return "  [%s] EMPTY" % label
    if len(data) >= 0x30:
        m1 = struct.unpack_from('<I', data, 0)[0]
        cmd = struct.unpack_from('<I', data, 0x1C)[0]
        ps = struct.unpack_from('<I', data, 0x28)[0]
        extra = data[0x30+ps:0x30+ps+64].hex() if len(data) > 0x30+ps else ""
        return "  [%s] %dB m1=0x%08X cmd=0x%08X ps=%d extra=%s" % (label, len(data), m1, cmd, ps, extra)
    return "  [%s] %dB: %s" % (label, len(data), data[:64].hex())

def do_port3001_handshake(num_channels=4):
    """Replicate the 4x port 3001 88-byte handshakes."""
    print("\n=== Phase 1: Port 3001 handshakes (4 channels) ===")
    conns = []
    for ch in range(num_channels):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            s.connect((CAM, 3001))
            frame = build_88frame(0x38383838, channel=ch)
            s.sendall(frame)
            resp = recv_full(s, timeout=2)
            print("  Ch%d: sent 88B, got %dB" % (ch, len(resp)))
            if len(resp) > 0:
                print(dump(resp, "ch%d" % ch))
            conns.append(s)
        except Exception as e:
            print("  Ch%d error: %s" % (ch, e))
            s.close()
        time.sleep(0.01)
    return conns

def do_port3001_config():
    """Send config commands on port 3001 (cmd=3, channel, value, port)."""
    print("\n=== Phase 2: Port 3001 config ===")
    # From capture: two config commands sent on separate connections
    configs = [
        (2, 0x36, 0xBB8),  # channel 2, val=54, port=3000
        (4, 0x35, 0xBB8),  # channel 4, val=53, port=3000
    ]
    for ch_cfg, val, port in configs:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            s.connect((CAM, 3001))
            # First handshake
            s.sendall(build_88frame(0x38383838, 0))
            recv_full(s, timeout=1)
            # Send config: 16 bytes
            cfg = struct.pack('<IIII', 3, ch_cfg, val, port)
            s.sendall(cfg)
            resp = recv_full(s, timeout=2)
            print("  cfg(ch=%d, val=%d, port=%d): got %dB" % (ch_cfg, val, port, len(resp)))
            if resp: print(dump(resp, "cfg"))
        except Exception as e:
            print("  cfg error: %s" % e)
        finally:
            s.close()
        time.sleep(0.01)

def do_login_and_commands():
    """Replicate the exact port 3000 login sequence for 2 channels."""
    print("\n=== Phase 3: Port 3000 login + commands ===")
    
    for stream_idx in range(2):
        print("\n--- Stream %d ---" % stream_idx)
        
        # Connection A: SERVERCHS + password (login)
        s_login = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_login.settimeout(5)
        s_login.connect((CAM, 3000))
        
        # Send SERVERCHS with correct IP cmd_word
        hdr = build_48frame(SERVERCHS_CMD_WORD, channel=0, payload_size=40)
        print("  Sending SERVERCHS cmd=0x%08X" % SERVERCHS_CMD_WORD)
        s_login.sendall(hdr)
        time.sleep(0.05)
        
        # Send password
        print("  Sending password %dB" % len(PASSWORD))
        s_login.sendall(PASSWORD)
        
        # Read response
        resp = recv_full(s_login, timeout=3)
        print(dump(resp, "LOGIN"))
        
        if len(resp) >= 0x30:
            cmd = struct.unpack_from('<I', resp, 0x1C)[0]
            print("  Login response: 0x%08X" % cmd)
            if cmd & 0xFF00 == 0:  # Successful: status byte is 0
                print("  *** LOGIN SUCCESS! ***")
        
        # Send GETSERIALNO (cmd=0x14) on same connection
        hdr2 = build_48frame(0xCCCC0014, channel=0, payload_size=0)
        s_login.sendall(hdr2)
        resp2 = recv_full(s_login, timeout=3)
        print(dump(resp2, "SERIALNO"))
        
        # Connection B: CLEANALARM (cmd=2) + start stream
        s_alarm = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_alarm.settimeout(5)
        s_alarm.connect((CAM, 3000))
        
        alarm_cmd_word = 0xCCCC0002
        alarm_payload = struct.pack('<II', 0x35 + stream_idx, 1)  # channel type + 1
        hdr3 = build_48frame(alarm_cmd_word, channel=0, payload_size=len(alarm_payload))
        print("  CLEANALARM: cmd=0x%08X, payload=%s" % (alarm_cmd_word, alarm_payload.hex()))
        s_alarm.sendall(hdr3)
        time.sleep(0.05)
        s_alarm.sendall(alarm_payload)
        
        resp3 = recv_full(s_alarm, timeout=3)
        print(dump(resp3, "CLEANALARM"))
        
        # Now try to read video data for a few seconds
        print("  Reading for video data (5s)...")
        s_alarm.settimeout(5)
        video_data = b''
        start = time.time()
        try:
            while time.time() - start < 5:
                chunk = s_alarm.recv(65536)
                if not chunk: break
                video_data += chunk
                if len(video_data) < 200:
                    print("    %dB: %s" % (len(chunk), chunk[:32].hex()))
        except: pass
        
        if video_data:
            print("  Got %d bytes of video data!" % len(video_data))
            # Check for H.264 start codes
            if b'\x00\x00\x01\xb3' in video_data:
                print("  Contains MPEG1 start code (000001B3)")
            if b'\x00\x00\x01\x00' in video_data:
                print("  Contains MPEG1 picture start (00000100)")
            if b'\x00\x00\x00\x01' in video_data:
                print("  Contains H.264 Annex-B start code")
            
            # Save first stream
            fname = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_%d.h264" % stream_idx
            with open(fname, 'wb') as f:
                f.write(video_data)
            print("  Saved to %s" % fname)
        else:
            print("  No video data received")
        
        s_login.close()
        s_alarm.close()
        time.sleep(0.1)

# === MAIN ===
try:
    conns = do_port3001_handshake(4)
    for c in conns:
        try: c.close()
        except: pass
except Exception as e:
    print("Phase 1 error: %s" % e)

do_port3001_config()
do_login_and_commands()

print("\n=== DONE ===")
