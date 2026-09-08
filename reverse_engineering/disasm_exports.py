"""Disassemble VSNET_ClientStart and related functions to find calling convention."""
import subprocess, re, sys

DLL = r"D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi\NetClient.dll"

# Use dumpbin to get exports
result = subprocess.run(
    ['dumpbin', '/exports', DLL],
    capture_output=True, text=True
)
print("=== EXPORTS ===")
for line in result.stdout.split('\n'):
    if 'VSNET' in line or 'Client' in line or 'Message' in line:
        print(line.strip())

# Get the RVA of VSNET_ClientStart
print("\n=== Looking for VSNET_ClientStart RVA ===")
exports = {}
for line in result.stdout.split('\n'):
    m = re.search(r'(\d+)\s+(\d+)\s+([0-9A-F]+)\s+(\w+)', line)
    if m:
        ordinal, hint, rva, name = m.groups()
        exports[name] = int(rva, 16)
        if 'ClientStart' in name:
            print("  %s: ordinal=%s hint=%s RVA=0x%s (%d)" % (name, ordinal, hint, rva, int(rva, 16)))

# Use objdump to disassemble the export
print("\n=== Disassembly of key exports ===")
for name in ['_VSNET_ClientStart@8', '_VSNET_ClientStart@16', '_VSNET_ClientStartup@0',
             '_VSNET_ClientSetDevInfo@4', '_VSNET_ClientMessageOpt@8',
             '_VSNET_ClientMessageOpen@4']:
    clean = name.lstrip('_')
    if clean in exports or name in exports:
        rva = exports.get(clean, exports.get(name, 0))
        print("\n--- %s (RVA=0x%X) ---" % (name, rva))
        # Disassemble around this RVA
        result2 = subprocess.run(
            ['dumpbin', '/disasm', '/range:%X,%X' % (rva, rva + 256), DLL],
            capture_output=True, text=True
        )
        for line in result2.stdout.split('\n'):
            if line.strip() and not line.startswith('Microsoft') and not line.startswith('Dump'):
                print(line)

# Also get section info to map RVAs
print("\n=== SECTIONS ===")
result3 = subprocess.run(['dumpbin', '/headers', DLL], capture_output=True, text=True)
in_sections = False
for line in result3.stdout.split('\n'):
    if 'section' in line.lower() and 'virtual' in line.lower():
        in_sections = True
    if in_sections:
        print(line)
    if 'Summary' in line:
        break
