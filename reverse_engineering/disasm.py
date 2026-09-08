#!/usr/bin/env python3
"""
disasm.py - disassemble a function/RVA region inside a PE DLL.
Usage: python disasm.py <path> <rva> <length>
"""
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

path = sys.argv[1]
try:
    rva = int(sys.argv[2], 16) if sys.argv[2].lower().startswith('0x') else int(sys.argv[2], 10)
except ValueError:
    rva = int(sys.argv[2], 16)
length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x200

pe = pefile.PE(path)
img = pe.OPTIONAL_HEADER.ImageBase
mmap = pe.get_memory_mapped_image()
raw = mmap[rva:rva + length]
md = Cs(CS_ARCH_X86, CS_MODE_32)
for insn in md.disasm(raw, img + rva):
    print(f'0x{insn.address:08x}: {insn.mnemonic} {insn.op_str}')