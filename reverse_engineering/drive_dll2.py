"""Drive NetClient.dll - fix arg types."""
import ctypes, struct, time, socket

DLL_PATH = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\NetClient.dll"
dll = ctypes.WinDLL(DLL_PATH)

Startup = dll.VSNET_ClientStartup
Startup.restype = ctypes.c_int
Startup.argtypes = []

result = Startup()
print("Startup() = %d" % result)

# SetDevInfo
env_buf = ctypes.create_string_buffer(256)
env_buf.raw = b'192.168.2.32\x00' + b'\x00' * (256 - 13)
SetDevInfo = dll.VSNET_ClientSetDevInfo
SetDevInfo.restype = ctypes.c_int
SetDevInfo.argtypes = [ctypes.c_void_p, ctypes.c_int]
result = SetDevInfo(ctypes.addressof(env_buf), 256)
print("SetDevInfo() = %d" % result)

# ClientStart - try different signatures
# The crash at 0xBBC=3000 means port was treated as pointer
# Maybe: Start(int, void* struct, void* struct, int)
# Or: Start(int mode, int port_as_int, int channel, int ip_as_int)

Start = dll.VSNET_ClientStart
Start.restype = ctypes.c_int

# Try signature: (int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
Start.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
IP_INT = struct.unpack('<I', socket.inet_aton('192.168.2.32'))[0]

print("\nTrying Start(int,int,int,int)...")
for a1 in [0, 1]:
    for a2 in [3000, 3001, IP_INT]:
        for a3 in [0, 1]:
            for a4 in [0, IP_INT, 3000]:
                try:
                    result = Start(a1, a2, a3, a4)
                    print("  Start(%d,%d,%d,%d) = %d" % (a1,a2,a3,a4,result))
                except:
                    pass
                time.sleep(0.1)

# Try with just 1 arg
print("\nTrying Start(int)...")
for a1 in [0, 1, 2, 3000]:
    try:
        result = Start(a1)
        print("  Start(%d) = %d" % (a1, result))
    except:
        pass

# Try with 0 args
print("\nTrying Start()...")
try:
    Start.argtypes = []
    result = Start()
    print("  Start() = %d" % result)
except Exception as e:
    print("  Start() error:", e)

# Try with 2 args
print("\nTrying Start(int, int)...")
for a1 in [0, 1]:
    for a2 in [0, 3000, IP_INT]:
        try:
            Start.argtypes = [ctypes.c_int, ctypes.c_int]
            result = Start(a1, a2)
            print("  Start(%d,%d) = %d" % (a1,a2,result))
        except:
            pass

print("\n=== DONE ===")
