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

# Check valid headers and compute method ranges
methods = []
for i in range(len(md.MethodDef)):
    row = md.MethodDef[i]
    rva = row.Rva
    if rva == 0:
        continue
    off = rva_to_offset(rva)
    if off is None:
        continue
    data = pe.get_data(off, 16)
    flags16 = data[0] | (data[1] << 8)
    fmt = flags16 & 3
    
    codesize = 0
    header_size = 0
    if fmt == 2:  # tiny
        codesize = data[0] >> 2
        header_size = 1
    elif fmt == 3:  # fat
        hdr_size_dw = (flags16 >> 2) & 0x3F
        header_size = hdr_size_dw * 4
        if header_size < 12:
            header_size = 12
        codesize = data[4] | (data[5] << 8) | (data[6] << 16) | (data[7] << 24)
    
    methods.append({
        'idx': i,
        'rva': rva,
        'off': off,
        'fmt': fmt,
        'header_size': header_size,
        'codesize': codesize,
        'name': str(row.Name),
        'valid': fmt in (2, 3) and codesize > 0
    })

# Sort by RVA and print all methods in order
methods.sort(key=lambda m: m['rva'])
print('All methods sorted by RVA:')
for m in methods:
    end_rva = m['rva'] + m['header_size'] + m['codesize'] if m['valid'] else 0
    valid_marker = 'OK' if m['valid'] else '??'
    print(f'  [{m["idx"]:4d}] 0x{m["rva"]:05X}-0x{end_rva:05X} hdr={m["header_size"]:2d} code={m["codesize"]:4d} {valid_marker} {m["name"]}')
