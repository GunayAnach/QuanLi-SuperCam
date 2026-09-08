import pefile
import dnfile
import struct

EXE = r'D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\PCB_Client.exe'
d = dnfile.dnPE(EXE)
pe = pefile.PE(EXE)

# Check the CLI header
off = pe.get_offset_rva(pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress)
data = pe.get_data(off, 72)
cb = struct.unpack_from('<I', data, 0)[0]
major = struct.unpack_from('<H', data, 4)[0]
minor = struct.unpack_from('<H', data, 6)[0]
meta_rva = struct.unpack_from('<I', data, 8)[0]
meta_size = struct.unpack_from('<I', data, 12)[0]
flags = struct.unpack_from('<I', data, 16)[0]
entry_token = struct.unpack_from('<I', data, 20)[0]
print(f'CLR Header: v{major}.{minor}, Flags=0x{flags:X}, EntryToken=0x{entry_token:X}')
print(f'Metadata: RVA=0x{meta_rva:X} Size={meta_size}')

md = d.net.mdtables
print(f'MethodDef={len(md.MethodDef)}, MemberRef={len(md.MemberRef)}, TypeRef={len(md.TypeRef)}, TypeDef={len(md.TypeDef)}')

def rva_to_offset(rva):
    for s in pe.sections:
        start = s.VirtualAddress
        end = start + s.SizeOfRawData
        if start <= rva < end:
            return rva - start + s.PointerToRawData
    return None

targets = [
    (0x9FD0, 'ClientMessageOpen'),
    (0x9E98, 'StartHdVideo'),
    (0x9F10, 'StartIrVideo'),
    (0xA3F5, 'StartClientMessage'),
    (0x9E76, 'StartVideoServer'),
    (0xA10D, 'ClientJpegCapStart'),
    (0x6B10, 'Start (349)'),
    (0xA2F8, 'StartHdVID'),
    (0xA380, 'StartIrVID'),
    (0x9DCF, 'OnRestartDeviceEvent'),
    (0x8068, 'StartPlanThread'),
]

print('\n=== Target Methods ===')
for rva, name in targets:
    off = rva_to_offset(rva)
    if off is None:
        print(f'{name}: RVA=0x{rva:04X} NOT IN SECTION')
        continue
    data = pe.get_data(off, 48)
    print(f'\n{name}: RVA=0x{rva:04X} (aligned={rva%4==0})')
    bs = ' '.join(f'{b:02X}' for b in data[:32])
    print(f'  First 32 bytes: {bs}')
