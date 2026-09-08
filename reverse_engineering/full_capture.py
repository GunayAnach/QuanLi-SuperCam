"""Full fidelity capture of a complete PCB login with raw hex - using scapy to file immediately."""
from scapy.all import sniff, TCP, IP
import os, time

OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/full_login_cap.txt"
IF = "Realtek PCIe GbE Family Controller"
CAM = "192.168.2.32"
f = open(OUT, 'w', encoding='utf-8')
n = [0]

def h(pkt):
    if pkt.haslayer(TCP) and pkt.haslayer(IP):
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if not payload:
            return
        n[0] += 1
        d = "C2S" if ip.dst == CAM else "S2C"
        f.write("--- #%d %s %s:%d->%s:%d %dB ---\n" % (
            n[0], d, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload)))
        for off in range(0, len(payload), 16):
            chunk = payload[off:off+16]
            hx = ' '.join('%02x' % b for b in chunk)
            a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            f.write("  %04X: %-48s %s\n" % (off, hx, a))
        f.write("\n")
        f.flush()

print("Listening for 180s...")
sniff(prn=h, store=False, timeout=180, iface=IF, filter="host %s and tcp" % CAM)
f.close()
print("Done. %d packets -> %s" % (n[0], OUT))
