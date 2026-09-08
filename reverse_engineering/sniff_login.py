"""Capture the login handshake: first bytes of a fresh TCP connection to the camera."""
import sys, time, os
from scapy.all import *

CAM = "192.168.2.32"
DPORT = 3000
OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/login_capture/"
os.makedirs(OUT, exist_ok=True)

conns = {}  # client_key=(pc_ip,client_port) -> {'c2s': bytes, 's2c': bytes, 'syn_time': float}
CAPLEN = 4096

def client_key_for(packet):
    """Given a packet, return the (client_ip, client_port) 4-tuple endpoint."""
    ip = packet[IP]; tcp = packet[TCP]
    if tcp.dport == DPORT:
        return (ip.src, tcp.sport)  # client is sending TO camera
    elif tcp.sport == DPORT:
        return (ip.dst, tcp.dport)  # camera responding to client
    return None

def handle(pkt):
    if not pkt.haslayer(TCP) or not pkt.haslayer(IP):
        return
    ip = pkt[IP]; tcp = pkt[TCP]
    key = client_key_for(pkt)
    if key is None:
        return
    
    is_syn = (tcp.flags & 0x02) and not (tcp.flags & 0x10)  # SYN only (not SYN-ACK)
    payload = bytes(tcp.payload)
    
    # SYN: register new connection
    if is_syn and tcp.dport == DPORT:
        conns[key] = {'c2s': b'', 's2c': b'', 'syn_time': float(pkt.time)}
        print("[+%.3f] NEW conn %s:%d -> %s:%d" % (0, ip.src, tcp.sport, ip.dst, tcp.dport), flush=True)
        return
    
    if key not in conns:
        return
    
    st = conns[key]
    trel = float(pkt.time) - st['syn_time']
    
    if tcp.sport == DPORT and payload:  # Camera -> Client
        if len(st['s2c']) < CAPLEN:
            st['s2c'] += payload[:CAPLEN - len(st['s2c'])]
            print("  [%.3f] S2C + %d (total %d)" % (trel, len(payload), len(st['s2c'])), flush=True)
    elif tcp.dport == DPORT and payload:  # Client -> Camera
        if len(st['c2s']) < CAPLEN:
            st['c2s'] += payload[:CAPLEN - len(st['c2s'])]
            print("  [%.3f] C2S + %d (total %d)" % (trel, len(payload), len(st['c2s'])), flush=True)
    
    # Save once we have both directions
    if len(st['c2s']) > 0 and len(st['s2c']) > 0:
        save_conn(key, st)

saved = []

def save_conn(key, st):
    if key in conns:
        del conns[key]
    t = int(time.time())
    fn = os.path.join(OUT, "login_%s_%s_%s" % (key[0], key[1], t))
    open(fn + "_c2s.bin", "wb").write(st['c2s'])
    open(fn + "_s2c.bin", "wb").write(st['s2c'])
    open(fn + "_c2s.hex", "w").write(st['c2s'].hex())
    open(fn + "_s2c.hex", "w").write(st['s2c'].hex())
    msg = "[saved] C2S=%d S2C=%d -> %s" % (len(st['c2s']), len(st['s2c']), fn)
    print(msg, flush=True)
    saved.append(msg)

IF = "Realtek PCIe GbE Family Controller"
print("=== LOGIN HANDSHAKE CAPTURE ===")
print("Watching for new connections to %s:%d" % (CAM, DPORT))
print(">> RESTART THE PCB CLIENT NOW (close and reopen) <<")
print("Waiting up to 120 seconds...")
sniff(prn=handle, store=False, timeout=120, iface=IF)
print("\nDone. Captured %d login(s)" % len(saved))
for l in saved:
    print(l)
