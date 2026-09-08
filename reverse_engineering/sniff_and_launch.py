"""Long-running sniffer - waits for user to manually configure PCB tool."""
import time, struct, sys, os
from scapy.all import sniff, TCP, IP, Raw, AsyncSniffer

CAM = "192.168.2.32"
IF = "Realtek PCIe GbE Family Controller"
OUT = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/login_packets.txt"
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
        # Print in real time
        t = ts - captured[0][0] if len(captured) > 1 else 0
        if len(payload) >= 4:
            first4 = struct.unpack_from('<I', payload, 0)[0]
            if first4 == M1 and len(payload) >= 0x20:
                cmd = struct.unpack_from('<I', payload, 0x1C)[0]
                print("[%.3f] %s:%d->%s:%d %dB cmd=0x%08X echo=%d" % (
                    t, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload), cmd, cmd&0xFF), flush=True)
            else:
                print("[%.3f] %s:%d->%s:%d %dB %s" % (
                    t, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload), payload[:16].hex()), flush=True)
        else:
            print("[%.3f] %s:%d->%s:%d %dB %s" % (
                t, ip.src, tcp.sport, ip.dst, tcp.dport, len(payload), payload.hex()), flush=True)

print("SNIFFER RUNNING. Now go configure the PCB tool:", flush=True)
print("  1. Open PCB Client", flush=True)
print("  2. System Configure -> Add IP 192.168.2.32", flush=True)
print("  3. Connect to the camera", flush=True)
print("Waiting up to 300 seconds (5 min)...", flush=True)
print(flush=True)

sniffer = AsyncSniffer(
    prn=pkt_handler, store=False, timeout=300, iface=IF,
    filter="host %s and tcp" % CAM
)
sniffer.start()
time.sleep(300)
sniffer.stop()

print("\n=== Capture done. %d packets. ===" % len(captured), flush=True)

# Write detailed log
with open(OUT, 'w') as f:
    for ts, direction, src, sport, dst, dport, size, payload in captured:
        t = ts - captured[0][0] if captured else 0
        if len(payload) >= 0x30:
            m1 = struct.unpack_from('<I', payload, 0)[0]
            if m1 == M1:
                cmd = struct.unpack_from('<I', payload, 0x1C)[0]
                ps = struct.unpack_from('<I', payload, 0x28)[0]
                f.write("[%.3f] %s %s:%d->%s:%d %dB cmd=0x%08X echo=%d ps=%d hdr=%s" % (
                    t, direction, src, sport, dst, dport, size, cmd, cmd&0xFF, ps, payload[:0x30].hex()))
                if ps > 0 and len(payload) > 0x30:
                    f.write(" payload=%s" % payload[0x30:0x30+min(ps,512)].hex())
                f.write("\n")
                continue
        f.write("[%.3f] %s %s:%d->%s:%d %dB %s\n" % (
            t, direction, src, sport, dst, dport, size, payload[:128].hex()))

# Print summary
print("Written to", OUT)
magic = [p for p in captured if len(p[7])>=0x30 and struct.unpack_from('<I',p[7],0)[0]==M1]
non_magic = [p for p in captured if len(p[7])<0x30 or struct.unpack_from('<I',p[7],0)[0]!=M1]
print("Magic frames: %d, Other: %d" % (len(magic), len(non_magic)))

print("\n--- ALL MAGIC FRAMES ---")
for ts, direction, src, sport, dst, dport, size, payload in magic:
    t = ts - captured[0][0]
    cmd = struct.unpack_from('<I', payload, 0x1C)[0]
    ps = struct.unpack_from('<I', payload, 0x28)[0]
    print("[%.3f] %s %s:%d->%s:%d cmd=0x%08X ps=%d hdr=%s" % (
        t, direction, src, sport, dst, dport, cmd, ps, payload[:0x30].hex()))

print("\n--- FIRST 50 NON-MAGIC PACKETS ---")
for ts, direction, src, sport, dst, dport, size, payload in non_magic[:50]:
    t = ts - captured[0][0]
    print("[%.3f] %s %s:%d->%s:%d %dB %s" % (
        t, direction, src, sport, dst, dport, size, payload[:64].hex()))
