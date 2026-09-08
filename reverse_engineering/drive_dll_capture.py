"""Drive DLL + capture wire in parallel."""
import ctypes, struct, time, socket, sys, os, threading

DLL_PATH = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\NetClient.dll"
CAM = "192.168.2.32"

# ============ Wire capture setup ============
from scapy.all import sniff, TCP, IP, Raw, conf, AsyncSniffer

captured = []
CAMERA_MAC = None

def pkt_handler(pkt):
    if pkt.haslayer(TCP) and pkt.haslayer(IP):
        ip = pkt[IP]
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if payload:
            global CAMERA_MAC
            if pkt.haslayer('Ether'):
                if ip.src == CAM:
                    CAMERA_MAC = pkt['Ether'].src
            direction = "C2S" if ip.dst == CAM else "S2C"
            captured.append((time.time(), direction, len(payload), payload[:128].hex()))

IF = "Realtek PCIe GbE Family Controller"
sniffer = AsyncSniffer(
    prn=pkt_handler, store=False, timeout=60, iface=IF,
    filter="host %s" % CAM
)
sniffer.start()
time.sleep(1)
print("Wire sniffer started.")

# ============ DLL driving ============
dll = ctypes.WinDLL(DLL_PATH)

Startup = dll.VSNET_ClientStartup
Startup.restype = ctypes.c_int
Startup.argtypes = []
r = Startup()
print("Startup() = %d" % r)

# SetDevInfo - try various buffer layouts
SetDevInfo = dll.VSNET_ClientSetDevInfo
SetDevInfo.restype = ctypes.c_int
SetDevInfo.argtypes = [ctypes.c_void_p, ctypes.c_int]

# Layout 1: Just IP string
for size in [64, 128, 256]:
    env = ctypes.create_string_buffer(size)
    env.raw = CAM.encode('ascii') + b'\x00'
    r = SetDevInfo(ctypes.addressof(env), size)
    print("SetDevInfo('%s', %d) = %d" % (CAM, size, r))

# Layout 2: IP + port as struct
for size in [64, 128]:
    env = ctypes.create_string_buffer(size)
    # Write IP string at offset 0, port at offset maybe 64
    env.raw = CAM.encode('ascii') + b'\x00'
    # Write port 3000 as ushort at various offsets
    for off in [32, 48, 60, 62]:
        if off + 2 <= size:
            struct.pack_into('<H', env, off, 3000)
    r = SetDevInfo(ctypes.addressof(env), size)
    print("SetDevInfo(IP+port, %d) = %d" % (size, r))

# Try ClientStart with 2 args, different combos
Start = dll.VSNET_ClientStart
Start.restype = ctypes.c_int
Start.argtypes = [ctypes.c_int, ctypes.c_int]

IP_INT = struct.unpack('<I', socket.inet_aton(CAM))[0]

print("\nClientStart variations:")
for a1 in [0, 1, 2, 3, 4, 5]:
    for a2 in [0, 3000, 3001, IP_INT]:
        try:
            r = Start(a1, a2)
            print("  Start(%d, %d) = %d" % (a1, a2, r))
            time.sleep(0.3)
        except:
            pass

# Also try Start with 4 args where port is passed as int (not ushort)
Start.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
print("\nClientStart 4-arg variations:")
for a1 in [0, 1]:
    for a2 in [3000, 3001]:
        for a3 in [0, 1]:
            for a4 in [0, IP_INT]:
                try:
                    r = Start(a1, a2, a3, a4)
                    if r != 0 and r != -1:
                        print("  Start(%d,%d,%d,%d) = %d <<<" % (a1,a2,a3,a4,r))
                    elif r == 0:
                        print("  Start(%d,%d,%d,%d) = 0 !!!" % (a1,a2,a3,a4))
                except:
                    pass

# Try MessageOpen
MessageOpen = dll.VSNET_ClientMessageOpen
MessageOpen.restype = ctypes.c_int
MessageOpen.argtypes = []
r = MessageOpen()
print("\nMessageOpen() = %d" % r)

# Try MessageOpt  
MessageOpt = dll.VSNET_ClientMessageOpt
MessageOpt.restype = ctypes.c_int
MessageOpt.argtypes = [ctypes.c_int, ctypes.c_int]

for cmd in [1, 5, 21]:
    r = MessageOpt(cmd, 0)
    print("MessageOpt(%d, 0) = %d" % (cmd, r))
    time.sleep(2)

# Wait for wire traffic
time.sleep(3)

# Stop sniffer
sniffer.stop()

print("\n=== WIRE CAPTURE ===")
print("Captured %d packets" % len(captured))
if CAMERA_MAC:
    print("Camera MAC:", CAMERA_MAC)
for ts, direction, size, hexdata in captured:
    print("  %s %d bytes: %s" % (direction, size, hexdata[:80]))

print("\n=== DONE ===")
