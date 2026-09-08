"""Drive NetClient.dll with 32-bit Python, capture wire traffic."""
import ctypes, struct, time, sys, threading, os, socket

# Load DLL with __stdcall convention
DLL_PATH = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\NetClient.dll"
dll = ctypes.WinDLL(DLL_PATH)

# Get function addresses with correct signatures
# __stdcall: all args on stack, callee cleans
# VSNET_ClientStartup() -> int
Startup = dll.VSNET_ClientStartup
Startup.restype = ctypes.c_int
Startup.argtypes = []

# VSNET_ClientStart() -> int  (no args? or takes params?)
Start = dll.VSNET_ClientStart
Start.restype = ctypes.c_int
Start.argtypes = [ctypes.c_int, ctypes.c_ushort, ctypes.c_ushort, ctypes.c_int]

# VSNET_ClientSetDevInfo(env_info*, int) -> int
SetDevInfo = dll.VSNET_ClientSetDevInfo
SetDevInfo.restype = ctypes.c_int
SetDevInfo.argtypes = [ctypes.c_void_p, ctypes.c_int]

# VSNET_ClientMessageOpen() -> int
MessageOpen = dll.VSNET_ClientMessageOpen
MessageOpen.restype = ctypes.c_int
MessageOpen.argtypes = []

# VSNET_ClientMessageOpt(cmd, something) -> int
MessageOpt = dll.VSNET_ClientMessageOpt
MessageOpt.restype = ctypes.c_int
MessageOpt.argtypes = [ctypes.c_int, ctypes.c_int]

# VSNET_ClientStartView() -> int
StartView = dll.VSNET_ClientStartView
StartView.restype = ctypes.c_int
StartView.argtypes = []

print("DLL loaded (WinDLL, __stdcall).")

# Step 1: ClientStartup
result = Startup()
print("ClientStartup() = %d (0x%X)" % (result, result))

# Step 2: Try SetDevInfo with various env_info contents
# Build SDK_ENV_INFO: 64-byte buffer with IP/port info
env_buf = ctypes.create_string_buffer(256)
# Try setting just the IP string
env_buf.raw = b'192.168.2.32\x00' + b'\x00' * (256 - 13)
result = SetDevInfo(ctypes.addressof(env_buf), 256)
print("SetDevInfo(192.168.2.32, 256) = %d" % result)

# Also try a shorter buffer
env_buf2 = ctypes.create_string_buffer(64)
env_buf2.raw = b'192.168.2.32\x00' + b'\x00' * 51
result = SetDevInfo(ctypes.addressof(env_buf2), 64)
print("SetDevInfo(192.168.2.32, 64) = %d" % result)

# Step 3: Try ClientStart with various args
# The __stdcall export wraps a __thiscall, so the export function takes the args
# without 'this' (it's hardcoded to global)
IP_INT = struct.unpack('<I', socket.inet_aton('192.168.2.32'))[0]

print("\nTrying ClientStart variations...")
for a1 in [0, 1, 2, 3]:
    for a2 in [3000, 3001]:
        for a4 in [IP_INT, 0, 0xFFFFFFFF]:
            result = Start(a1, a2, 0, a4)
            if result != 0:
                print("  Start(%d, %d, 0, 0x%08X) = %d" % (a1, a2, a4, result))
            time.sleep(0.3)

# Step 4: Try no-arg Start (maybe it takes no args?)
print("\nTrying Start() with no args...")
try:
    Start_noarg = dll.VSNET_ClientStart
    Start_noarg.restype = ctypes.c_int
    Start_noarg.argtypes = []
    result = Start_noarg()
    print("Start() = %d" % result)
except Exception as e:
    print("Start() error:", e)

# Step 5: Try MessageOpen and MessageOpt
print("\nTrying MessageOpen...")
result = MessageOpen()
print("MessageOpen() = %d" % result)

time.sleep(1)

print("\nTrying MessageOpt with commands...")
for cmd in [1, 5, 21]:
    result = MessageOpt(cmd, 0)
    print("MessageOpt(%d, 0) = %d" % (cmd, result))
    time.sleep(1)

# Step 6: Try StartView
print("\nTrying StartView...")
result = StartView()
print("StartView() = %d" % result)

time.sleep(2)

print("\n=== DONE ===")
