"""Drive DLL with 32-bit Python, signal start/stop with files."""
import ctypes, struct, time, socket, os

DLL_PATH = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\NetClient.dll"
CAM = "192.168.2.32"
SIGNAL = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\dll_signal.txt"

# Signal sniffer to start
open(SIGNAL, 'w').write('start')

dll = ctypes.WinDLL(DLL_PATH)

Startup = dll.VSNET_ClientStartup
Startup.restype = ctypes.c_int
Startup.argtypes = []
print("Startup:", Startup())

# SetDevInfo
SetDevInfo = dll.VSNET_ClientSetDevInfo
SetDevInfo.restype = ctypes.c_int
SetDevInfo.argtypes = [ctypes.c_void_p, ctypes.c_int]

# Try the exact SDK_ENV_INFO layout from extract_structs.py
# The struct was: 64-byte env buffer. But let's try larger.
env = ctypes.create_string_buffer(256)
env.raw = b'192.168.2.32\x00' + b'\x00' * 243
print("SetDevInfo(256):", SetDevInfo(ctypes.addressof(env), 256))

# Now try calling Start with the C# calling convention
# The export wrapper pushes ecx=CClientAdmin, then calls StartInner
# But the export is __stdcall, so the C# marshaller passes args differently
# Let me try: Start(handle, port) where handle is some ID

Start = dll.VSNET_ClientStart
Start.restype = ctypes.c_int

# Key insight: the crash at 0xBBC (3000) means the function reads memory at that address
# So port=3000 was passed as a POINTER. The 2-arg signature that worked:
# Start(0, 0) = -1, Start(1, 0) = -1
# Maybe the first arg is a connection handle/index, and there's no second arg

# Let me try ALL combinations of small ints
print("\nTrying Start with various small int combos:")
for a1 in range(10):
    for a2 in range(10):
        try:
            Start.argtypes = [ctypes.c_int, ctypes.c_int]
            r = Start(a1, a2)
            if r != -1:
                print("  Start(%d,%d) = %d !!!" % (a1, a2, r))
        except:
            pass

# Try Start with pointer args
print("\nTrying Start with pointer args:")
for a1 in [0, 1]:
    # Pass camera IP as a string pointer
    ip_str = ctypes.create_string_buffer(CAM.encode('ascii') + b'\x00')
    for a2 in [ctypes.addressof(ip_str), 0]:
        try:
            Start.argtypes = [ctypes.c_int, ctypes.c_void_p]
            r = Start(a1, a2)
            print("  Start(%d, ptr=%d) = %d" % (a1, a2, r))
        except:
            pass

# Try passing a struct
print("\nTrying Start with struct args:")
class DevInfo(ctypes.Structure):
    _fields_ = [
        ('ip', ctypes.c_char * 64),
        ('port', ctypes.c_ushort),
        ('channel', ctypes.c_ushort),
    ]

di = DevInfo()
di.ip = CAM.encode('ascii')
di.port = 3000
di.channel = 0

for a1 in [0, 1]:
    try:
        Start.argtypes = [ctypes.c_int, ctypes.c_void_p]
        r = Start(a1, ctypes.byref(di))
        print("  Start(%d, struct) = %d" % (a1, r))
    except Exception as e:
        print("  Start(%d, struct) error: %s" % (a1, str(e)[:60]))

# Now try MessageOpt with various signatures
MessageOpt = dll.VSNET_ClientMessageOpt
MessageOpt.restype = ctypes.c_int

print("\nTrying MessageOpt signatures:")
for sig in [
    [ctypes.c_int, ctypes.c_int],
    [ctypes.c_int, ctypes.c_void_p],
    [ctypes.c_int, ctypes.c_int, ctypes.c_int],
]:
    MessageOpt.argtypes = sig
    for cmd in [1, 5, 21]:
        try:
            if len(sig) == 2:
                r = MessageOpt(cmd, 0)
            else:
                r = MessageOpt(cmd, 0, 0)
            print("  MessageOpt(%d, 0) [%d args] = %d" % (cmd, len(sig), r))
        except:
            pass

time.sleep(2)

# Signal sniffer to stop
open(SIGNAL, 'w').write('stop')
print("\n=== DONE ===")
