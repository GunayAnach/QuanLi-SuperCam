#!/usr/bin/env python3
"""extract_structs.py - Dump field layouts of SDK_* structs used in P/Invoke."""
import dnfile

path = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\PCB_Client.exe"
pe = dnfile.dnPE(path)
md = pe.net.mdtables

ET = {0x01:"bool",0x02:"char",0x03:"sbyte",0x04:"byte",0x05:"int16",0x06:"uint16",
      0x07:"int32",0x08:"uint32",0x09:"int64",0x0a:"uint64",0x0b:"float32",
      0x0c:"float64",0x0d:"string",0x0f:"byref",0x1d:"array",0x1f:"intptr",0x40:"void"}

tdefs_row = {}
short_to_row = {}
for i, td in enumerate(md.TypeDef, start=1):
    ns = str(td.TypeNamespace or "")
    nm = str(td.TypeName)
    tdefs_row[i] = f"{ns}.{nm}" if ns else nm
    short_to_row.setdefault(nm, i)

def rd(data, idx):
    b0=data[idx]; idx+=1
    if b0&0x80==0: return b0,idx
    if b0&0xC0==0x80: return ((b0&0x3f)<<8)|data[idx], idx+1
    return ((b0&0x1f)<<24)|(data[idx]<<16)|(data[idx+1]<<8)|data[idx+2], idx+3

def parse_field_type(data, idx):
    et=data[idx]; idx+=1
    if et in (0x10,0x11):
        tok,idx=rd(data,idx)
        return ("VT:" if et==0x10 else "CLS:")+tdefs_row.get(tok, f"#{tok}"), idx
    if et==0x1d:
        e,idx=parse_field_type(data,idx)
        return e+"[]",idx
    if et==0x0e:
        e,idx=parse_field_type(data,idx)
        return e+"*",idx
    return ET.get(et,f"0x{et:x}"),idx

def dump_type(typename, indent=0):
    row = short_to_row.get(typename)
    pad = "  "*indent
    if row is None:
        print(pad + f"[{typename}: NOT DEFINED in this assembly]")
        return
    td = md.TypeDef[row-1]
    print(pad + f"[struct {tdefs_row[row]}]")
    for fi in td.FieldList or []:
        frow = fi.row
        name = str(frow.Name)
        try:
            data = bytes(frow.Signature.value)
            ftype, _ = parse_field_type(data, 1)
        except Exception as e:
            ftype = f"<err {e}>"
        print(pad + f"  .{name} : {ftype}")

for name in ["SDK_ENV_INFO","SDK_MEASURE","SDK_SHAPE_TYPE","SDK_IR_IMG","SDK_VIS_IMG",
             "SDK_PSTOBJECT","SDK_SPOT","SDK_BOX","SDK_PALETTE","SDK_DATA",
             "SDK_FUSION","SDK_AGC","SDK_OTHERS","SDK_LABEL","SDK_SHAPE_UNION",
             "DEV_TEMP_SPAN","VSNETRECT"]:
    dump_type(name)
    print()
