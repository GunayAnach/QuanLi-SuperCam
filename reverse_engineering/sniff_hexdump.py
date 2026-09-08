"""Sniffer - 5 min timeout, writes full hex dumps."""
import time, struct
from scapy.all import AsyncSniffer, TCP, IP

CAM = "192.168.2.32"
IF = "Realtek PCIe GbE Family Controller"
M1 = 0x123AB678

captured = []

def pkt_handler(pkt):
    if pkt.haslayer(TCP) and pkt.haslayer(IP):
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if not payload:
            return
        ts = float(pkt.time)
        direction = "C2S" if ip.dst == CAM else "S2C"
        captured.append((ts, direction, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload), payload))
        t = ts - captured[0][0] if len(captured) > 1 else 0
        print("[%6.3f] %s %s:%d->%s:%d %dB" % (t, direction, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload)), flush=True)

sniffer = AsyncSniffer(
    prn=pkt_handler, store=False, timeout=300, iface=IF,
    filter="host %s and tcp" % CAM
)
sniffer.start()
print("Sniffer running 300s. Waiting...", flush=True)
time.sleep(300)
sniffer.stop()

print("\n=== %d packets ===" % len(captured), flush=True)

OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/login_hexdump.txt"
with open(OUT, 'w', encoding='utf-8') as f:
    for i, (ts, direction, src, sport, dst, dport, size, payload) in enumerate(captured):
        t = ts - captured[0][0]
        f.write("--- #%d [%.3f] %s %s:%d->%s:%d %dB ---\n" % (i, t, direction, src, sport, dst, dport, size))
        for offset in range(0, len(payload), 16):
            chunk = payload[offset:offset+16]
            hex_part = ' '.join('%02x' % b for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            f.write("  %04X: %-48s %s\n" % (offset, hex_part, ascii_part))
        f.write("\n")

print("Written", OUT, flush=True)
