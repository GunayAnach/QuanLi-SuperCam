"""
IL Decompiler for PCB_Client.exe - handles obfuscated .NET binaries.
Writes output to file to avoid console encoding issues.
"""
import pefile
import dnfile
import struct
import sys
import os

EXE = r'D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\PCB_Client.exe'
OUT = r'D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\il_output.txt'

# ============================================================
# CIL Opcode Table (ECMA-335)
# ============================================================
OPCODES = {
    0x00: ('nop', 0), 0x01: ('break', 0),
    0x02: ('ldarg.0', 0), 0x03: ('ldarg.1', 0), 0x04: ('ldarg.2', 0), 0x05: ('ldarg.3', 0),
    0x06: ('ldloc.0', 0), 0x07: ('ldloc.1', 0), 0x08: ('ldloc.2', 0), 0x09: ('ldloc.3', 0),
    0x0A: ('stloc.0', 0), 0x0B: ('stloc.1', 0), 0x0C: ('stloc.2', 0), 0x0D: ('stloc.3', 0),
    0x0E: ('ldarg.s', 1), 0x0F: ('ldarga.s', 1), 0x10: ('starg.s', 1),
    0x11: ('ldloc.s', 1), 0x12: ('ldloca.s', 1), 0x13: ('stloc.s', 1),
    0x14: ('ldnull', 0), 0x15: ('ldc.i4.m1', 0),
    0x16: ('ldc.i4.0', 0), 0x17: ('ldc.i4.1', 0), 0x18: ('ldc.i4.2', 0), 0x19: ('ldc.i4.3', 0),
    0x1A: ('ldc.i4.4', 0), 0x1B: ('ldc.i4.5', 0), 0x1C: ('ldc.i4.6', 0), 0x1D: ('ldc.i4.7', 0),
    0x1E: ('ldc.i4.8', 0), 0x1F: ('ldc.i4.s', 1), 0x20: ('ldc.i4', 4),
    0x21: ('ldarg', 2), 0x22: ('ldarga', 2), 0x23: ('starg', 2),
    0x24: ('ldloc', 2), 0x25: ('ldloca', 2), 0x26: ('stloc', 2),
    0x28: ('call', 4), 0x29: ('calli', 4), 0x2A: ('ret', 0),
    0x2B: ('br.s', 1), 0x2C: ('brfalse.s', 1), 0x2D: ('brtrue.s', 1),
    0x2E: ('beq.s', 1), 0x2F: ('bge.s', 1), 0x30: ('bgt.s', 1), 0x31: ('ble.s', 1),
    0x32: ('blt.s', 1), 0x33: ('bne.un.s', 1), 0x34: ('bge.un.s', 1), 0x35: ('bgt.un.s', 1),
    0x36: ('ble.un.s', 1), 0x37: ('blt.un.s', 1),
    0x38: ('br', 4), 0x39: ('brfalse', 4), 0x3A: ('brtrue', 4),
    0x3B: ('beq', 4), 0x3C: ('bge', 4), 0x3D: ('bgt', 4), 0x3E: ('ble', 4),
    0x3F: ('blt', 4), 0x40: ('bne.un', 4), 0x41: ('bge.un', 4), 0x42: ('bgt.un', 4),
    0x43: ('ble.un', 4), 0x44: ('blt.un', 4),
    0x45: ('switch', -1),
    0x46: ('ldind.i1', 0), 0x47: ('ldind.u1', 0), 0x48: ('ldind.i2', 0), 0x49: ('ldind.u2', 0),
    0x4A: ('ldind.i4', 0), 0x4B: ('ldind.u4', 0), 0x4C: ('ldind.i8', 0), 0x4D: ('ldind.u8', 0),
    0x4E: ('ldind.r4', 0), 0x4F: ('ldind.r8', 0), 0x50: ('ldind.ref', 0),
    0x51: ('stind.ref', 0), 0x52: ('stind.i1', 0), 0x53: ('stind.i2', 0),
    0x54: ('stind.i4', 0), 0x55: ('stind.i8', 0), 0x56: ('stind.r4', 0), 0x57: ('stind.r8', 0),
    0x58: ('add', 0), 0x59: ('sub', 0), 0x5A: ('mul', 0), 0x5B: ('div', 0),
    0x5C: ('div.un', 0), 0x5D: ('rem', 0), 0x5E: ('rem.un', 0),
    0x5F: ('and', 0), 0x60: ('or', 0), 0x61: ('xor', 0),
    0x62: ('shl', 0), 0x63: ('shr', 0), 0x64: ('shr.un', 0),
    0x65: ('neg', 0), 0x66: ('not', 0),
    0x67: ('conv.i1', 0), 0x68: ('conv.i2', 0), 0x69: ('conv.i4', 0), 0x6A: ('conv.i8', 0),
    0x6B: ('conv.r4', 0), 0x6C: ('conv.r8', 0), 0x6D: ('conv.u4', 0), 0x6E: ('conv.u8', 0),
    0x6F: ('callvirt', 4),
    0x70: ('cpobj', 4), 0x71: ('ldobj', 4), 0x72: ('ldstr', 4), 0x73: ('newobj', 4),
    0x74: ('castclass', 4), 0x75: ('isinst', 4), 0x76: ('conv.r.un', 0),
    0x7B: ('ldfld', 4), 0x7C: ('ldflda', 4), 0x7D: ('stfld', 4),
    0x7E: ('ldsfld', 4), 0x7F: ('ldsflda', 4), 0x80: ('stsfld', 4), 0x81: ('stsflda', 4),
    0x82: ('stobj', 4),
    0x83: ('conv.ovf.i1.un', 0), 0x84: ('conv.ovf.i2.un', 0), 0x85: ('conv.ovf.i4.un', 0),
    0x86: ('conv.ovf.i8.un', 0), 0x87: ('conv.ovf.u1.un', 0), 0x88: ('conv.ovf.u2.un', 0),
    0x89: ('conv.ovf.u4.un', 0), 0x8A: ('conv.ovf.u8.un', 0),
    0x8B: ('conv.ovf.i.un', 0), 0x8C: ('conv.ovf.u.un', 0),
    0x8D: ('box', 4), 0x8E: ('newarr', 4), 0x8F: ('ldlen', 0),
    0x90: ('ldelem', 4), 0x91: ('ldelem.i', 0), 0x92: ('ldelem.i1', 0), 0x93: ('ldelem.u1', 0),
    0x94: ('ldelem.i2', 0), 0x95: ('ldelem.u2', 0), 0x96: ('ldelem.i4', 0), 0x97: ('ldelem.u4', 0),
    0x98: ('ldelem.i8', 0), 0x99: ('ldelem.u8', 0), 0x9A: ('ldelem.r4', 0), 0x9B: ('ldelem.r8', 0),
    0x9C: ('ldelem.ref', 0),
    0x9D: ('stelem', 4), 0x9E: ('stelem.i', 0), 0x9F: ('stelem.i1', 0),
    0xA0: ('stelem.i2', 0), 0xA1: ('stelem.i4', 0), 0xA2: ('stelem.i8', 0),
    0xA3: ('stelem.r4', 0), 0xA4: ('stelem.r8', 0), 0xA5: ('stelem.ref', 0),
    0xA6: ('ldelema', 4),
    0xA7: ('conv.ovf.i1', 0), 0xA8: ('conv.ovf.u1', 0), 0xA9: ('conv.ovf.i2', 0),
    0xAA: ('conv.ovf.u2', 0), 0xAB: ('conv.ovf.i4', 0), 0xAC: ('conv.ovf.u4', 0),
    0xAD: ('conv.ovf.i8', 0), 0xAE: ('conv.ovf.u8', 0),
    0xB0: ('refanyval', 4), 0xB1: ('ckfinite', 0), 0xB2: ('mkrefany', 4),
    0xC2: ('ldtoken', 4), 0xC3: ('ldftn', 4), 0xC4: ('ldvirtftn', 4),
    0xC6: ('cpblk', 0), 0xC7: ('initblk', 0), 0xC9: ('endfinally', 0),
    0xD0: ('leave', 4), 0xD3: ('leave.s', 1), 0xD4: ('stind.i', 0), 0xD5: ('conv.u', 0),
    0xD6: ('rethrow', 0),
    0xFE: ('prefix', 0),
}

FE_OPCODES = {
    0x00: ('ceq', 0), 0x01: ('cgt', 0), 0x02: ('ceq.un', 0),
    0x03: ('clt', 0), 0x04: ('clt.un', 0),
    0x05: ('ldftn', 4), 0x06: ('ldvirtftn', 4),
    0x07: ('ldarg', 2), 0x08: ('ldarga', 2), 0x09: ('starg', 2),
    0x0A: ('ldloc', 2), 0x0B: ('ldloca', 2), 0x0C: ('stloc', 2),
    0x0D: ('localloc', 0), 0x0E: ('endfilter', 0),
    0x0F: ('unaligned.', 1), 0x10: ('volatile.', 0), 0x11: ('tail.', 0),
    0x12: ('initobj', 4), 0x13: ('cpblk', 0), 0x14: ('initblk', 0),
    0x15: ('cpobj', 4), 0x16: ('newobj', 4), 0x17: ('rethrow', 0),
    0x19: ('sizeof', 4), 0x1A: ('ceq', 0), 0x1B: ('mkrefany', 4),
    0x1C: ('constrained.', 4), 0x1F: ('endfinally', 0),
    0x20: ('stind.i', 0), 0x21: ('conv.u', 0),
}

def rva_to_offset(pe, rva):
    for s in pe.sections:
        start = s.VirtualAddress
        end = start + s.SizeOfRawData
        if start <= rva < end:
            return rva - start + s.PointerToRawData
    return None

def resolve_token(dn, token):
    if token == 0:
        return 'null'
    table = (token >> 24) & 0xFF
    row = token & 0x00FFFFFF
    md = dn.net.mdtables
    try:
        if table == 0x01 and row > 0 and row <= len(md.TypeRef):
            tr = md.TypeRef[row - 1]
            ns = str(tr.TypeNamespace) if tr.TypeNamespace else ''
            nm = str(tr.TypeName) if tr.TypeName else '?'
            return f'{ns}.{nm}' if ns else nm
        elif table == 0x02 and row > 0 and row <= len(md.TypeDef):
            td = md.TypeDef[row - 1]
            ns = str(td.TypeNamespace) if td.TypeNamespace else ''
            nm = str(td.TypeName) if td.TypeName else '?'
            return f'{ns}.{nm}' if ns else nm
        elif table == 0x06 and row > 0 and row <= len(md.MethodDef):
            return str(md.MethodDef[row - 1].Name)
        elif table == 0x04 and row > 0 and row <= len(md.Field):
            return str(md.Field[row - 1].Name)
        elif table == 0x0A and row > 0 and row <= len(md.MemberRef):
            mcr = md.MemberRef[row - 1]
            name = str(mcr.Name)
            return name
        elif table == 0x08 and row > 0:
            return f'TypeSpec#{row}'
        elif table == 0x1B and row > 0:
            return f'TypeSpec#{row}'
        elif table == 0x11 and row > 0:
            return f'Sig#{row}'
        elif table == 0x1C and row > 0 and hasattr(md, 'MethodSpec') and md.MethodSpec:
            if row <= len(md.MethodSpec):
                return f'MethodSpec#{row}'
            return f'MethodSpec#{row}'
        elif table == 0x26:
            return f'FieldRef#{row}'
    except:
        pass
    return f'Token(0x{token:08X})'

def resolve_member_ref_detail(dn, token):
    """Try to resolve a MemberRef to class::method."""
    table = (token >> 24) & 0xFF
    row = token & 0x00FFFFFF
    md = dn.net.mdtables
    try:
        if table == 0x0A and row > 0 and row <= len(md.MemberRef):
            mcr = md.MemberRef[row - 1]
            name = str(mcr.Name)
            class_tok = mcr.Class
            if hasattr(class_tok, 'row'):
                class_idx = class_tok.row
                class_table = class_tok.table
                if class_table and hasattr(class_table, 'table'):
                    tn = class_table.table
                    if tn == 0x01 and class_idx <= len(md.TypeRef):
                        tr = md.TypeRef[class_idx - 1]
                        ns = str(tr.TypeNamespace) if tr.TypeNamespace else ''
                        nm = str(tr.TypeName) if tr.TypeName else '?'
                        cname = f'{ns}.{nm}' if ns else nm
                    elif tn == 0x02 and class_idx <= len(md.TypeDef):
                        td = md.TypeDef[class_idx - 1]
                        ns = str(td.TypeNamespace) if td.TypeNamespace else ''
                        nm = str(td.TypeName) if td.TypeName else '?'
                        cname = f'{ns}.{nm}' if ns else nm
                    elif tn == 0x1B:
                        cname = f'TypeSpec#{class_idx}'
                    else:
                        cname = f'Table0x{tn:02X}#{class_idx}'
                else:
                    cname = str(class_tok)
            elif isinstance(class_tok, int):
                cname = resolve_token(dn, class_tok)
            else:
                cname = str(class_tok)
            return f'{cname}::{name}'
    except:
        pass
    return resolve_token(dn, token)

def try_header_detection(data):
    """Try to detect if data starts with a tiny or fat method header.
    Returns (has_header, code_start_offset, code_size)"""
    if len(data) < 2:
        return False, 0, 0
    b0 = data[0]
    fmt = b0 & 3
    if fmt == 2:  # tiny
        cs = b0 >> 2
        if cs > 0 and cs < len(data):
            return True, 1, cs
    elif fmt == 3:  # fat
        if len(data) >= 12:
            flags16 = data[0] | (data[1] << 8)
            hdr_dw = (flags16 >> 12) & 0xF
            cs = data[4] | (data[5] << 8) | (data[6] << 16) | (data[7] << 24)
            hdr_bytes = max(hdr_dw * 4, 12)
            if cs > 0 and hdr_dw >= 3 and cs < 0x100000 and hdr_bytes + cs <= len(data):
                return True, hdr_bytes, cs
    return False, 0, 0

def decompile_raw_il(data, dn, max_bytes=512, base_rva=0):
    """Decode raw IL bytes (no header)."""
    lines = []
    pos = 0
    count = 0
    while pos < min(len(data), max_bytes) and count < 200:
        offset = pos
        op = data[pos]
        pos += 1
        if op == 0xFE:
            if pos >= len(data):
                break
            fe_op = data[pos]
            pos += 1
            info = FE_OPCODES.get(fe_op)
            if info is None:
                lines.append(f'  +0x{offset:04X}: FE {fe_op:02X}    ; <unknown>')
                continue
            mnemonic, opsz = info
        else:
            info = OPCODES.get(op)
            if info is None:
                lines.append(f'  +0x{offset:04X}: {op:02X}        ; <unknown opcode>')
                continue
            mnemonic, opsz = info

        if mnemonic == 'prefix':
            lines.append(f'  +0x{offset:04X}: FE {fe_op:02X}    ; <prefix>')
            continue

        operand = ''
        if opsz == 4 and pos + 4 <= len(data):
            tok = struct.unpack_from('<I', data, pos)[0]
            pos += 4
            name = resolve_member_ref_detail(dn, tok)
            operand = f'{name}    [0x{tok:08X}]'
            if 'VSNET' in name or 'Client' in name.split('::')[-1] if '::' in name else False:
                operand += '  <<<< IMPORTANT'
        elif opsz == 2 and pos + 2 <= len(data):
            val = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            operand = str(val)
        elif opsz == 1 and pos + 1 <= len(data):
            val = data[pos]
            pos += 1
            operand = str(val)

        if mnemonic == 'ret':
            lines.append(f'  +0x{offset:04X}: ret')
            break
        lines.append(f'  +0x{offset:04X}: {mnemonic} {operand}')
        count += 1
    return lines

def main():
    out = open(OUT, 'w', encoding='utf-8')
    def p(s=''):
        out.write(s + '\n')

    p(f'Loading {os.path.basename(EXE)}...')
    dn = dnfile.dnPE(EXE)
    pe = pefile.PE(EXE)
    md = dn.net.mdtables

    # ============================================================
    # Section info
    # ============================================================
    p('\n' + '=' * 80)
    p('PE SECTION MAPPING')
    p('=' * 80)
    for s in pe.sections:
        name = s.Name.decode().strip('\x00')
        p(f'  {name:10s} VA=0x{s.VirtualAddress:08X} Size=0x{s.SizeOfRawData:08X} Raw=0x{s.PointerToRawData:08X}')

    # ============================================================
    # CLI Header
    # ============================================================
    p('\n' + '=' * 80)
    p('.NET METADATA INFO')
    p('=' * 80)
    try:
        off = pe.get_offset_rva(pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress)
        data = pe.get_data(off, 72)
        major, minor = struct.unpack_from('<HH', data, 4)
        meta_rva, meta_size = struct.unpack_from('<II', data, 8)
        flags = struct.unpack_from('<I', data, 16)[0]
        entry_token = struct.unpack_from('<I', data, 20)[0]
        p(f'  CLR Version: {major}.{minor}')
        p(f'  Flags: 0x{flags:X}')
        p(f'  EntryPointToken: 0x{entry_token:08X}')
        if (entry_token >> 24) == 0x06:
            entry_row = entry_token & 0xFFFFFF
            if entry_row <= len(md.MethodDef):
                em = md.MethodDef[entry_row - 1]
                p(f'  EntryPoint: MethodDef[{entry_row}] = {em.Name} RVA=0x{em.Rva:04X}')
    except Exception as e:
        p(f'  Error reading CLI header: {e}')

    p(f'  MethodDef count: {len(md.MethodDef)}')
    p(f'  MemberRef count: {len(md.MemberRef)}')
    p(f'  TypeRef count: {len(md.TypeRef)}')
    p(f'  TypeDef count: {len(md.TypeDef)}')

    # ============================================================
    # Find all VSNET_Client* references in MemberRef table
    # ============================================================
    p('\n' + '=' * 80)
    p('ALL MemberRef ENTRIES (VSNET_ and important native/P/Invoke)')
    p('=' * 80)
    if md.MemberRef:
        for i in range(len(md.MemberRef)):
            try:
                mcr = md.MemberRef[i]
                name = str(mcr.Name)
                if any(x in name for x in ['VSNET', 'VSNet', 'vsnet', 'ClientStartup', 'ClientStart',
                                             'ClientSetDevInfo', 'ClientMessage', 'ClientJpeg',
                                             'RegTemp', 'StartView', 'Native', 'DllImport',
                                             'PInvoke', 'kernel32', 'user32', 'WSA', 'socket',
                                             'connect', 'send', 'recv']):
                    class_tok = mcr.Class
                    cname = str(class_tok)
                    if hasattr(class_tok, 'row'):
                        ct = class_tok.table
                        cr = class_tok.row
                        if ct and hasattr(ct, 'table'):
                            tnum = ct.table
                            if tnum == 0x01 and cr <= len(md.TypeRef):
                                tr = md.TypeRef[cr - 1]
                                ns = str(tr.TypeNamespace) if tr.TypeNamespace else ''
                                nm = str(tr.TypeName) if tr.TypeName else '?'
                                cname = f'{ns}.{nm}' if ns else nm
                            elif tnum == 0x02 and cr <= len(md.TypeDef):
                                td = md.TypeDef[cr - 1]
                                ns = str(td.TypeNamespace) if td.TypeNamespace else ''
                                nm = str(td.TypeName) if td.TypeName else '?'
                                cname = f'{ns}.{nm}' if ns else nm
                            elif tnum == 0x1B:
                                cname = f'TypeSpec#{cr}'
                            else:
                                cname = f'Table0x{tnum:02X}#{cr}'
                    p(f'  MemberRef[{i+1}] = {cname}::{name}')
            except:
                pass

    # ============================================================
    # List ALL MethodDef entries with their names and RVAs
    # ============================================================
    p('\n' + '=' * 80)
    p('ALL MethodDef ENTRIES (sorted by RVA)')
    p('=' * 80)
    methods_by_rva = []
    for i in range(len(md.MethodDef)):
        row = md.MethodDef[i]
        methods_by_rva.append((row.Rva, i, str(row.Name)))
    methods_by_rva.sort()

    for rva, idx, name in methods_by_rva:
        if rva == 0:
            continue
        off = rva_to_offset(pe, rva)
        if off is None:
            continue
        data = pe.get_data(off, 4)
        b0 = data[0]
        fmt = b0 & 3
        fmt_str = 'tiny' if fmt == 2 else 'fat' if fmt == 3 else '???'
        aligned = rva % 4 == 0
        p(f'  [{idx:4d}] RVA=0x{rva:05X} {"OK" if aligned else "!!"} hdr={fmt_str:4s} b0=0x{b0:02X} {name}')

    # ============================================================
    # Decompile target methods
    # ============================================================
    targets = [
        (0x9FD0, 'ClientMessageOpen'),
        (0x9E98, 'StartHdVideo'),
        (0x9F10, 'StartIrVideo'),
        (0xA3F5, 'StartClientMessage'),
        (0x9E76, 'StartVideoServer'),
        (0xA10D, 'ClientJpegCapStart'),
        (0x6B10, 'Start (method 349)'),
        (0xA2F8, 'StartHdVID'),
        (0xA380, 'StartIrVID'),
        (0x9DCF, 'OnRestartDeviceEvent'),
        (0x8068, 'StartPlanThread'),
    ]

    for rva, name in targets:
        p('\n' + '=' * 80)
        p(f'METHOD: {name}  RVA=0x{rva:04X}')
        p('=' * 80)
        off = rva_to_offset(pe, rva)
        if off is None:
            p('  ERROR: RVA not found in any section')
            continue

        data = pe.get_data(off, 1024)

        # Show raw hex
        p('  RAW HEX:')
        for row in range(0, min(64, len(data)), 16):
            hexs = ' '.join(f'{b:02X}' for b in data[row:row+16])
            p(f'    +0x{row:04X}: {hexs}')

        # Try header detection
        has_hdr, code_off, code_sz = try_header_detection(data)
        if has_hdr:
            p(f'\n  HEADER DETECTED at offset 0: code_size={code_sz}, code starts at +0x{code_off:X}')
            code_data = data[code_off:code_off+code_sz]
        else:
            p(f'\n  NO VALID HEADER at RVA. Trying to decode raw IL from offset 0...')
            code_data = data

        # Decode IL
        p('  DECODED IL:')
        lines = decompile_raw_il(code_data, dn, max_bytes=800, base_rva=rva)
        for line in lines:
            p(line)

        # Also try to find nearby methods by scanning for ret (0x2A) boundaries
        p(f'\n  NOTE: If this RVA is inside another method, the above may be misaligned.')
        p(f'  Checking for "ret" (0x2A) boundaries within first 256 bytes:')
        ret_positions = []
        for i in range(min(256, len(data))):
            if data[i] == 0x2A:
                ret_positions.append(i)
        p(f'    ret found at byte offsets: {ret_positions[:20]}')

    # ============================================================
    # Search for VSNET strings in user strings heap
    # ============================================================
    p('\n' + '=' * 80)
    p('SEARCHING FOR VSNET / CLIENT STRINGS IN USER STRINGS HEAP')
    p('=' * 80)
    try:
        us = dn.net.user_strings
        if us:
            raw = us.__data__ if hasattr(us, '__data__') else bytes(us)
            # Search for ASCII patterns
            search_terms = [b'VSNET', b'vsnet', b'Client', b'client', b'21', b'AFFIRM',
                          b'message', b'MESSAGE', b'start', b'Start', b'Connect',
                          b'tcp://', b'http://', b'udp://', b'://', b'192.168',
                          b'10.0', b'172.16']
            for term in search_terms:
                idx = 0
                while True:
                    pos = raw.find(term, idx)
                    if pos < 0:
                        break
                    # Try to extract surrounding UTF-16LE string
                    start = max(0, pos - 20)
                    end = min(len(raw), pos + len(term) + 40)
                    snippet = raw[start:end]
                    try:
                        decoded = snippet.decode('utf-16-le', errors='replace')
                        p(f'  Found "{term.decode()}" at US offset 0x{pos:X}: ...{decoded!r}...')
                    except:
                        p(f'  Found "{term.decode()}" at US offset 0x{pos:X} (binary)')
                    idx = pos + 1
    except Exception as e:
        p(f'  Error searching user strings: {e}')

    # Also search the #Strings heap
    p('\n' + '=' * 80)
    p('SEARCHING FOR VSNET / CLIENT STRINGS IN #Strings HEAP')
    p('=' * 80)
    try:
        strings_heap = dn.net.Strings
        if strings_heap:
            for i in range(len(strings_heap)):
                try:
                    s = str(strings_heap[i])
                    if any(x in s for x in ['VSNET', 'vsnet', 'ClientStartup', 'ClientStart',
                                              'ClientSetDevInfo', 'ClientMessageOpen',
                                              'ClientMessageOpt', 'ClientStartView',
                                              'ClientRegTemp', 'ClientJpeg', 'MESSAGE_CMD',
                                              'AFFIRMUSER', 'AFFIRM']):
                        p(f'  Strings[{i}] = {s}')
                except:
                    pass
    except Exception as e:
        p(f'  Error: {e}')

    # ============================================================
    # Search for method defs that reference VSNET in their names
    # ============================================================
    p('\n' + '=' * 80)
    p('MethodDef entries containing VSNET/Client in name')
    p('=' * 80)
    for i in range(len(md.MethodDef)):
        row = md.MethodDef[i]
        name = str(row.Name)
        if any(x in name for x in ['VSNET', 'vsnet', 'Client', 'client', 'Message', 'Video',
                                     'Start', 'Stop', 'Connect', 'Login']):
            p(f'  [{i}] RVA=0x{row.Rva:05X} {name}')

    out.close()
    print(f'Output written to: {OUT}')

if __name__ == '__main__':
    main()
