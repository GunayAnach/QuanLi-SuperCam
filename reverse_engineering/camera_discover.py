#!/usr/bin/env python3
"""
camera_discover.py — discover a QuanLi/LangChi "SuperCam" thermal camera.

Two strategies:

A) NATIVE (recommended, Windows only)
   Loads the vendor's CamSearch.dll and drives its real discovery routine
   (CAMSEAR_Searchcam). This is exactly what the shipped client does, so it
   produces the true camera reply structures.

B) RAW UDP (portable, same broadcast domain required)
   Best-effort replica of the 54-byte UDP probe sent to UDP/10001 (local bind
   UDP/10002, magic 0x123AB678 + 0x876CD321). Because the exact preamble bytes
   are reconstructed from disassembly and may not be byte-exact, Strategy A is
   authoritative. If B gets no reply, capture live traffic from the vendor
   client (Wireshark on 10001/10002) to refine the packet.

CRITICAL: broadcast discovery only works from a host on the SAME L2 network as
the camera (your real Windows LAN adapter). It will NOT work from WSL2's NAT
virtual NIC. Run this from Windows (python.exe on the host), not from WSL.
"""

import os
import socket
import struct
import sys
import time

# ---------------------------------------------------------------------------
# Strategy A: call the real CamSearch.dll (Windows)
# ---------------------------------------------------------------------------
SEARCH_LEN = 54
MAGIC1 = 0x123AB678
MAGIC2 = 0x876CD321


def discover_native(camsearch_path):
    """Drive vendor CamSearch.dll. camsearch_path = full path to CamSearch.dll."""
    import ctypes
    from ctypes import wintypes

    dll = ctypes.WinDLL(camsearch_path)

    # CAMSEAR_Searchcam callback signature (from client usage)
    #   typedef int (__stdcall *CALLBACK)(void *ctx, char *buf, int len);
    CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p,
                                  ctypes.c_int)

    RESULT_BUFS = []  # keep replies referenced
    found = []

    # THUNK: we don't know the exact struct, so we call SearchReset first then
    # Searchcam and capture raw result buffers via a global callback.
    @CALLBACK
    def on_result(ctx, buf, length):
        if buf and length > 0:
            chunk = ctypes.string_at(buf, length)
            RESULT_BUFS.append(chunk)
            found.append(chunk)
        return 0

    # exported prototypes
    dll.CAMSEAR_Startup.argtypes = []
    dll.CAMSEAR_Startup.restype = ctypes.c_int
    dll.CAMSEAR_Cleanup.argtypes = []
    dll.CAMSEAR_SearchReset.argtypes = []
    dll.CAMSEAR_SearchReset.restype = ctypes.c_int

    # CAMSEAR_Searchcam signature (Delphi/stdcall) unknown exactly; try
    # (callback, ctx) as in the .NET P/Invoke usage.
    # The client invokes CAMSEAR_Searchcam(callback). We bind loosely.
    # Fallback: raw UDP below is authoritative if this ABI guess fails.
    dll.CAMSEAR_Searchcam.argtypes = [CALLBACK]
    dll.CAMSEAR_Searchcam.restype = ctypes.c_int

    print(f"[native] loading {camsearch_path}")
    dll.CAMSEAR_Startup()
    dll.CAMSEAR_SearchReset()
    t0 = time.time()
    try:
        dll.CAMSEAR_Searchcam(on_result)
    except Exception as e:
        print(f"[native] Searchcam call error (ABI guess): {e!r}")
    time.sleep(3)
    dll.CAMSEAR_Cleanup()

    for i, b in enumerate(found):
        print(f"[native] reply #{i}: {len(b)} bytes: {b.hex()}")
    return found


# ---------------------------------------------------------------------------
# Strategy B: raw UDP replication of the discovery probe
# ---------------------------------------------------------------------------
def build_search_packet():
    """Build the 54-byte discovery datagram."""
    pkt = bytearray(SEARCH_LEN)
    struct.pack_into("<I", pkt, 0, MAGIC1)      # 12 3A B6 78
    struct.pack_into("<I", pkt, 52 - 4, MAGIC2)  # 87 6C D3 21 end marker
    return bytes(pkt)


def discover_raw(targets, bind_port=10002, dest_port=10001, timeout=3.0):
    """Send 54-byte probes to UDP dest_port (broadcast + provided targets)."""
    pkt = build_search_packet()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("0.0.0.0", bind_port))
    s.settimeout(timeout)

    print(f"[raw] packet ({SEARCH_LEN} B): {pkt.hex()}")
    print(f"[raw] listening on UDP/{bind_port}, probing UDP/{dest_port} ...")

    destinations = set()
    for t in targets:
        destinations.add((t, dest_port))
    # directed subnet broadcast guesses on common ranges
    for sub in ("255.255.255.255", "192.168.1.255", "192.168.0.255",
                "192.168.1.200", "192.168.1.1"):
        destinations.add((sub, dest_port))

    got = []
    for dest, port in sorted(destinations):
        try:
            s.sendto(pkt, (dest, port))
            print(f"[raw] sent probe -> {dest}:{port}")
        except OSError as e:
            print(f"[raw] send to {dest} failed: {e}")
    time.sleep(0.2)

    end = time.time() + timeout
    while time.time() < end:
        try:
            s.settimeout(max(0.2, end - time.time()))
            data, addr = s.recvfrom(65535)
            print(f"[raw] REPLY from {addr[0]}:{addr[1]} :: {len(data)} B :: {data.hex()}")
            got.append((addr, data))
        except socket.timeout:
            break
        except OSError:
            break
    s.close()
    if not got:
        print("[raw] no replies. Check subnet / firewall / run on native Windows LAN.")
    return got


# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    print(__doc__)

    args = [a for a in sys.argv[1:]]
    targets = [a for a in args if "." in a]

    # Locate CamSearch.dll relative to this file (it sits in ../QuanLi)
    cand = os.path.join(os.path.dirname(here), "QuanLi", "CamSearch.dll")

    if os.name == "nt" and os.path.exists(cand):
        print("\n== Strategy A: native CamSearch.dll ==")
        try:
            discover_native(cand)
        except Exception as e:
            print(f"[native] failed: {e!r}")
        print("== /Strategy A ==")

    print("\n== Strategy B: raw UDP probe ==")
    tg = targets or ["255.255.255.255", "192.168.1.200"]
    discover_raw(tg)
    print("== /Strategy B ==")


if __name__ == "__main__":
    main()
