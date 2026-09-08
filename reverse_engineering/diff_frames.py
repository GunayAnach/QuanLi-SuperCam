"""Byte-by-byte diff of working (PCB) vs our SERVERCHS frame."""
import struct

MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321

# Working frame from capture #17:
# 0000: 78 b6 3a 12 76 69 64 65 6f 20 73 65 72 76 65 72   (16 bytes)
# 0010: 00 cc cc cc cc cc cc cc cc cc cc cc 01 00 c0 a8   (16 bytes)
# 0020: 02 20 b8 0b 00 00 00 00 28 00 00 00 21 d3 6c 87   (16 bytes)
# 0030: (end - total 48)
working_bytes = bytes.fromhex(
    "78b63a12766964656f2073657276657200"
    "cccccccccccc0100c0a8"
    "0220b80b000000002800000021d36c87"
)
# Count: 78b63a12(4) 766964656f20736572766572(13="video server") 00(1) 
#        cccccccccccc(12) 0100c0a8(4) 0220b80b(4) 00000000(4) 28000000(4) 21d36c87(4)
# = 4+13+1+12+4+4+4+4+4 = 50. That's too many. 

# Let me recount from the hex dump lines.
# Row 0000: 78 b6 3a 12 | 76 69 64 65 6f 20 73 65 72 76 65 72 (bytes 0-15)
#   byte 0-3:  78 b6 3a 12  = MAGIC1
#   byte 4-15: 76 69 64 65 6f 20 73 65 72 76 65 72  = "video server" (12 chars!)
#     wait "video server" = v-i-d-e-o-space-s-e-r-v-e-r = 12 chars
# Row 0010: 00 cc cc cc cc cc cc cc cc cc cc cc | 01 00 c0 a8 (bytes 16-31)
#   byte 16:    00  (null terminator)
#   byte 17-27: cc cc cc cc cc cc cc cc cc cc cc  = 11 CC
#   byte 28-31: 01 00 c0 a8  = cmd_word 0xA8C00001
# Row 0020: 02 20 b8 0b | 00 00 00 00 | 28 00 00 00 | 21 d3 6c 87 (bytes 32-47)
#   byte 32-35: 02 20 b8 0b  = 0x0BB82002
#   byte 36-39: 00 00 00 00  = channel 0
#   byte 40-43: 28 00 00 00  = ps 40
#   byte 44-47: 21 d3 6c 87  = MAGIC2
# TOTAL = 48 bytes ✓

working = (
    bytes.fromhex("78b63a12")
    + b"video server"      # 12 bytes
    + b"\x00"              # 1 byte
    + b"\xcc" * 11         # 11 bytes
    + bytes.fromhex("0100c0a8")   # cmd_word
    + bytes.fromhex("0220b80b")   # unknown
    + bytes.fromhex("00000000")   # channel 0
    + bytes.fromhex("28000000")   # ps 40
    + bytes.fromhex("21d36c87")   # MAGIC2
)
print("working len:", len(working))
print("working    :", working.hex())

# Our frame (from camera_login4.py), same structure:
def our_frame(channel, ps, unknown):
    f = bytearray(0x30)
    struct.pack_into('<I', f, 0x00, MAGIC1)
    f[0x04:0x11] = b"video server\x00"    # 13 bytes (includes null)
    f[0x11:0x1C] = b"\xcc" * 11          # 11 CC
    struct.pack_into('<I', f, 0x1C, 0xA8C00001)
    struct.pack_into('<I', f, 0x20, unknown)
    struct.pack_into('<I', f, 0x24, channel)
    struct.pack_into('<I', f, 0x28, ps)
    struct.pack_into('<I', f, 0x2C, MAGIC2)
    return bytes(f)

ours = our_frame(0, 40, 0x0BB82002)
print("ours     :", ours.hex())
print()
print("MATCH:", working == ours)
if working != ours:
    for i in range(48):
        if working[i] != ours[i]:
            print("  diff at offset 0x%02X: working=0x%02X ours=0x%02X" % (i, working[i], ours[i]))
