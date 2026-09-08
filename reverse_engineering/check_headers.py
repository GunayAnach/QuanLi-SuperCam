import pefile
import dnfile

EXE = r'D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\PCB_Client.exe'
d = dnfile.dnPE(EXE)
pe = pefile.PE(EXE)
md = d.net.mdtables

def rva_to_offset(rva):
    for s in pe.sections:
        start = s.VirtualAddress
        end = start + s.SizeOfRawData
        if start <= rva < end:
            return rva - start + s.PointerToRawData
    return None

valid = 0
invalid = 0
for i in range(len(md.MethodDef)):
    row = md.MethodDef[i]
    rva = row.Rva
    if rva == 0:
        continue
    off = rva_to_offset(rva)
    if off is None:
        continue
    data = pe.get_data(off, 4)
    flags16 = data[0] | (data[1] << 8)
    fmt = flags16 & 3
    aligned = (rva & 3) == 0
    if fmt == 2 or fmt == 3:
        valid += 1
    else:
        invalid += 1
        if invalid <= 30:
            bs = ' '.join(f'{b:02X}' for b in data)
            print(f'  [{i}] RVA=0x{rva:05X} align={aligned} bytes={bs} name={row.Name}')

print(f'\nValid: {valid}, Invalid: {invalid}, Total non-zero RVA: {valid+invalid}')
