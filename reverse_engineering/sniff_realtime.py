"""Sniffer with REAL-TIME file writing."""
import time, struct, sys
from scapy.all import sniff, TCP, IP

CAM = "192.168.2.32"
IF = "Realtek PCIe GbE Family Controller"
M1 = 0x123AB678
OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/login_hexdump.txt"

f = open(OUT, 'w', encoding='utf-8')
count = [0]
start = [0]

def pkt_handler(pkt):
    if pkt.haslayer(TCP) and pkt.haslayer(IP):
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if not payload:
            return
        ts = float(pkt.time)
        if count[0] == 0:
            start[0] = ts
        count[0] += 1
        t = ts - start[0]
        direction = "C2S" if ip.dst == CAM else "S2C"
        
        # Write summary line
        f.write("--- #%d [%.3f] %s %s:%d->%s:%d %dB ---\n" % (
            count[0]-1, t, direction, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload)))
        # Write full hex dump
        for offset in range(0, len(payload), 16):
            chunk = payload[offset:offset+16]
            hex_part = ' '.join('%02x' % b for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            f.write("  %04X: %-48s %s\n" % (offset, hex_part, ascii_part))
        f.write("\n")
        f.flush()
        
        if count[0] <= 60 or (count[0] % 50 == 0):
            print("[%6.3f] %s %s:%d->%s:%d %dB (total=%d)" % (
                t, direction, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload), count[0]), flush=True)

print("Sniffer with real-time write. Waiting 180s...", flush=True)
sniff(prn=pkt_handler, store=False, timeout=180, iface=IF,
      filter="host %s and tcp" % CAM)

f.close()
print("\n=== DONE. %d packets written to %s ===" % (count[0], OUT), flush=True)
