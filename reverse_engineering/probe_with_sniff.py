"""Sniff and probe simultaneously: capture all wire traffic during probing."""
import socket, struct, time, threading, os, sys

try:
    from scapy.all import sniff, TCP, IP, Raw, conf
except ImportError:
    print("ERROR: scapy not installed")
    sys.exit(1)

CAM = "192.168.2.32"
PORT = 3000
M1 = 0x123AB678
M2 = 0x876CD321
IF = "Realtek PCIe GbE Family Controller"
OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/fresh_capture/"
os.makedirs(OUT, exist_ok=True)

packets_captured = []

def pkt_handler(pkt):
    if pkt.haslayer(TCP) and pkt.haslayer(IP):
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if payload:
            direction = "C2S" if tcp.dport == PORT else "S2C"
            ts = float(pkt.time)
            packets_captured.append((ts, direction, ip.src, tcp.sport, ip.dst, tcp.dport, payload))

def bf(cmd, ch=0, pl=b''):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0, M1)
    struct.pack_into('<I', f, 0x1C, cmd)
    struct.pack_into('<I', f, 0x24, ch)
    struct.pack_into('<I', f, 0x28, len(pl))
    struct.pack_into('<I', f, 0x2C, M2)
    return bytes(f) + pl

def rcv(s, t=3):
    s.settimeout(t); d = b''
    try:
        while True:
            c = s.recv(65536)
            if not c: break
            d += c
    except: pass
    return d

def dump_hex(data, maxlen=128):
    return data[:maxlen].hex()

# Start sniffer in background thread
sniffer_thread = threading.Thread(target=lambda: sniff(
    prn=pkt_handler, store=False, timeout=60, iface=IF,
    filter="host %s and tcp" % CAM
), daemon=True)
sniffer_thread.start()
time.sleep(1)  # Let sniffer start

print("=== SNiffer started. Running probes. ===")

# PROBE 1: connect only, wait
print("\n--- P1: connect only, wait 5s ---")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected")
    r = rcv(s, 5)
    print("Got %d bytes" % len(r))
except Exception as e:
    print("Error:", e)
finally:
    s.close()
time.sleep(1)

# PROBE 2: SERVERCHS, wait 10s
print("\n--- P2: SERVERCHS, wait 10s ---")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected")
    s.sendall(bf(1, 0))
    r = rcv(s, 2)
    print("After SERVERCHS: %d bytes" % len(r))
    if r: print("  hex:", dump_hex(r))
    r2 = rcv(s, 10)
    print("After 10s wait: %d bytes" % len(r2))
    if r2: print("  hex:", dump_hex(r2))
except Exception as e:
    print("Error:", e)
finally:
    s.close()
time.sleep(1)

# PROBE 3: keepalive, wait 10s
print("\n--- P3: keepalive, wait 10s ---")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected")
    s.sendall(bf(5, 0))
    r = rcv(s, 2)
    print("After keepalive: %d bytes" % len(r))
    r2 = rcv(s, 10)
    print("After 10s wait: %d bytes" % len(r2))
except Exception as e:
    print("Error:", e)
finally:
    s.close()
time.sleep(1)

# PROBE 4: Keepalive ch=0 + ch=1 on same connection
print("\n--- P4: keepalive ch=0 then ch=1 ---")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
try:
    s.connect((CAM, PORT))
    print("Connected")
    s.sendall(bf(5, 0))
    r = rcv(s, 1)
    print("KA ch=0: %d bytes" % len(r))
    s.sendall(bf(5, 1))
    r = rcv(s, 1)
    print("KA ch=1: %d bytes" % len(r))
except Exception as e:
    print("Error:", e)
finally:
    s.close()
time.sleep(1)

# PROBE 5: Full sequence: KA -> SERVERCHS -> AFFIRMUSER -> GETCHANNELPARAM on 4 separate connections
print("\n--- P5: 4 connections (KA, SERVERCHS, AFFIRMUSER, GETCH) ---")
conns = []
for i, (cmd, name, ch) in enumerate([(5,"KA",0), (1,"SERVERCHS",0), (21,"AFFIRMUSER",0), (8,"GETCHPARAM",0)]):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
    try:
        s.connect((CAM, PORT))
        s.sendall(bf(cmd, ch))
        r = rcv(s, 1)
        print("  %s: %d bytes" % (name, len(r)))
        if r and len(r) >= 0x30:
            cw = struct.unpack_from('<I', r, 0x1C)[0]
            print("    cmd=0x%08X echo=%d" % (cw, cw & 0xFF))
        conns.append(s)
    except Exception as e:
        print("  %s: Error %s" % (name, e))
        s.close()

# Wait with all connections open
print("Waiting 10s with all connections open...")
time.sleep(10)
for i, s in enumerate(conns):
    try:
        r = rcv(s, 1)
        print("  conn%d got %d bytes" % (i, len(r)))
    except:
        pass
    s.close()

# Wait for sniffer
sniffer_thread.join(timeout=5)

# Dump captured packets
print("\n=== CAPTURED %d PACKETS ===" % len(packets_captured))
for ts, direction, src, sport, dst, dport, payload in packets_captured:
    t = ts - packets_captured[0][0] if packets_captured else 0
    if len(payload) >= 4 and payload[:4] == struct.pack('<I', M1):
        cmd = struct.unpack_from('<I', payload, 0x1C)[0] if len(payload) >= 0x20 else 0
        print("[%.3f] %s %s:%d->%s:%d %d bytes cmd=0x%08X echo=%d" % (
            t, direction, src, sport, dst, dport, len(payload), cmd, cmd & 0xFF))
    elif len(payload) > 4 and payload[:3] == b'\x00\x00\x01':
        print("[%.3f] %s %s:%d->%s:%d %d bytes [H.264 start]" % (
            t, direction, src, sport, dst, dport, len(payload)))
    else:
        print("[%.3f] %s %s:%d->%s:%d %d bytes %s" % (
            t, direction, src, sport, dst, dport, len(payload), payload[:32].hex()))

print("\n=== DONE ===")
