#!/usr/bin/env python3
"""
extract_pinvoke.py - Parse raw ECMA-335 method signature blobs (.value) to get
exact P/Invoke parameter/return types + calling convention for the camera DLLs.
"""
import dnfile

path = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\PCB_Client.exe"
pe = dnfile.dnPE(path)
md = pe.net.mdtables

ET = {
    0x01:"bool",0x02:"char",0x03:"sbyte",0x04:"byte",0x05:"int16",0x06:"uint16",
    0x07:"int32",0x08:"uint32",0x09:"int64",0x0a:"uint64",0x0b:"float32",
    0x0c:"float64",0x0d:"string",0x0e:"ptr*",0x0f:"byref",0x10:"valtype",
    0x11:"class",0x12:"var",0x1c:"object",0x1d:"array",0x1f:"intptr",
    0x20:"uintptr",0x40:"void",0x24:"typedref",
}
CALLING_CONV = {
    0x00:"Default",0x01:"C",0x02:"StdCall",0x03:"ThisCall",0x04:"FastCall",
    0x05:"VarArg",0x06:"Field",0x07:"LocalSig",0x08:"Property",0x09:"Unmanaged",
    0x0a:"GenericInst",
}

def rd(data, idx):
    b0=data[idx]; idx+=1
    if b0&0x80==0: return b0,idx
    if b0&0xC0==0x80:
        return ((b0&0x3f)<<8)|data[idx], idx+1
    return ((b0&0x1f)<<24)|(data[idx]<<16)|(data[idx+1]<<8)|data[idx+2], idx+3

def parse_type(data, idx, tdefs):
    et=data[idx]; idx+=1
    if et in (0x10,0x11):
        tok,idx=rd(data,idx)
        return tdefs.get(tok,f"T{et:x}#{tok}"),idx
    if et==0x1d:
        e,idx=parse_type(data,idx,tdefs)
        # array shape
        return e+"[]",idx
    return ET.get(et,f"0x{et:x}"),idx

tdefs={}
if hasattr(md,"TypeDef"):
    for i,td in enumerate(md.TypeDef,start=1):
        nm=td.TypeName
        if td.TypeNamespace: nm=f"{td.TypeNamespace}.{nm}"
        tdefs[i]=nm

print("=== P/Invoke signatures (parsed) ===")
for im in md.ImplMap:
    impname=str(im.ImportName) if im.ImportName else "?"
    m=im.MemberForwarded.row if im.MemberForwarded is not None else None
    if m is None: continue
    try:
        data=bytes(m.Signature.value)
    except Exception:
        print(f"IMPORT={impname} NO-SIG"); continue
    # Find calling convention byte: for method sig it's first byte
    cc=data[0]; idx=1
    try:
        pcount,idx=rd(data,idx)
        ret,idx=parse_type(data,idx,tdefs)
        params=[]
        for _ in range(pcount):
            p,idx=parse_type(data,idx,tdefs); params.append(p)
    except Exception as e:
        print(f"IMPORT={impname} CC=0x{cc:x} RAW={data.hex()} PARSE-ERR={e}"); continue
    print(f"IMPORT={impname} CC=0x{cc:x} RET={ret} NARGS={pcount} ARGS={params}")
