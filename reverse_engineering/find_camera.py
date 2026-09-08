#!/usr/bin/env python3
"""
find_camera.py - locate a QuanLi/LangChi "SuperCam" thermal camera and test
the TCP/3000 control connection.

Two jobs:
  1. Send the reverse-engineered 54-byte UDP discovery probe to UDP/10001
     (local bind UDP/10002, magic 0x123AB678 / 0x876CD321) to several
     candidate addresses (broadcast + likely statics). Any reply is printed
     RAW so you can read the camera's true advertised IP from the bytes.
  2. Probe TCP/3000 on candidate addresses to see which one accepts a
     connection (the one that "boots/sounds" should open 3000).

RUN FROM NATIVE WINDOWS (python.exe), NOT WSL:
    python find_camera.py
    python find_camera.py 192.168.1.200 192.168.2.199 192.168.2.32 192.168.2.2

The camera is likely statically set to 192.168.1.200 (per ConfigureFile.xml),
so if you want a connect, put your NIC on 192.168.1.x first.
"""

import socket
import struct
import sys
import time

SEARCH_PORT = 10001      # discovery probe destination
BIND_PORT = 10002        # local UDP socket (where replies arrive)
TCP_PORT = 3000          # command/control port
PROBE = bytearray(54)
struct.pack_into("<I", PROBE, 0, 0x123AB678)
struct.pack_into("<I", PROBE, 50, 0x876CD321)


def default_targets():
    return [
        "255.255.255.255",
        "192.168.1.255", "192.168.2.255",
        "192.168.1.200", "192.168.1.199",
        "192.168.2.32", "192.168.2.199",
        "192.168.2.2", "192.168.1.2",
    ]


def udp_discover(targets):
    print(f"\n== UDP discovery probe -> {SEARCH_PORT}, listen {BIND_PORT} ==")
    print(f"packet({len(PROBE)}B): {PROBE.hex()}")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:
        pass
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except OSError:
        pass
    s.bind(("0.0.0.0", BIND_PORT))
    s.settimeout(4)

    for tgt in targets:
        try:
            s.sendto(PROBE, (tgt, SEARCH_PORT))
            print(f"  sent -> {tgt}:{SEARCH_PORT}")
        except OSError as e:
            print(f"  send {tgt} failed: {e}")

    replies = 0
    end = time.time() + 4
    while time.time() < end:
        try:
            s.settimeout(max(0.3, end - time.time()))
            data, addr = s.recvfrom(4096)
            replies += 1
            print(f"\n  [REPLY] from {addr[0]}:{addr[1]}  len={len(data)}")
            print(f"  hex: {data.hex()}")
            # try to extract a dotted-quad IP if present anywhere in the reply
            txt = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
            for tok in data.split(b"\x00"):
                if b"." in tok and all(
                    c.isdigit() or c == 46 for c in tok
                ):
                    print(f"  possible IP in reply: {tok.decode()}")
        except socket.timeout:
            break
        except OSError:
            break
    s.close()
    if replies == 0:
        print("  no UDP replies. (Camera may be on a different subnet than all listed.)")
    return replies


def tcp_probe(hosts):
    print(f"\n== TCP/{TCP_PORT} connect probe + banner ==")
    for h in hosts:
        try:
            t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            t.settimeout(2.5)
            t.connect((h, TCP_PORT))
            state = "OPEN"
            try:
                t.settimeout(2.0)
                t.sendall(b"")  # some cameras send a banner on connect
            except Exception:
                pass
            try:
                banner = t.recv(256)
            except Exception:
                banner = b""
            print(f"  {h}:{TCP_PORT} -> OPEN  banner={banner!r}")
            t.close()
        except Exception as e:
            print(f"  {h}:{TCP_PORT} -> closed/filtered ({type(e).__name__})")


def scan_subnet(subnet, ports=(3000,)):
    """Sweep a /24 for hosts with any of the given TCP ports open."""
    print(f"\n== Scanning {subnet}.0/24 for open TCP ports {list(ports)} ==")
    found = {}  # ip -> [open ports]
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        o = []
        for p in ports:
            try:
                t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                t.settimeout(0.35)
                t.connect((ip, p))
                o.append(p)
                t.close()
            except Exception:
                continue
        if o:
            print(f"  {ip}: {o}")
            found[ip] = o
    if not found:
        print(f"  no open ports in {subnet}.0/24")
    else:
        print(f"  hosts with open ports: {found}")
    return found


def get_local_subnet():
    """Return local IPv4 /24 prefix (e.g. '192.168.2')."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # doesn't send, just picks route
        ip = s.getsockname()[0]
        s.close()
        return ip.rsplit(".", 1)[0]
    except Exception:
        return None


SECONDARY_PORTS = [3000, 2000, 4000, 6000, 9000, 10000, 5555, 8000, 8500, 5000]


def tcp_multi_port(host):
    """Probe many candidate control/stream ports on one host."""
    print(f"\n== Port scan {host} (control + likely stream ports) ==")
    open_ports = []
    for p in SECONDARY_PORTS:
        try:
            t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            t.settimeout(0.6)
            t.connect((host, p))
            print(f"  {host}:{p} -> OPEN")
            open_ports.append(p)
            t.close()
        except Exception:
            pass
    print(f"  open: {open_ports}")
    return open_ports


def main():
    print(__file__)
    args = [a for a in sys.argv[1:] if "." in a]
    hosts = args or default_targets()
    hosts = list(dict.fromkeys(hosts))  # dedupe, keep order

    udp_discover(hosts)

    # For explicitly-listed real IPs (not broadcast pseudo-IPs), do a full
    # control+stream port scan so we find where the video actually flows.
    real = [h for h in hosts if "." in h and not h.endswith(".255") and h != "255.255.255.255"]
    for h in real:
        tcp_multi_port(h)

    tcp_probe(hosts)

    if "--scan" in sys.argv:
        subnet = get_local_subnet()
        if subnet:
            # probe common camera + stream ports, not just 3000
            scan_subnet(subnet, ports=(3000, 2000, 4000, 6000, 9000, 10000, 8000))
        else:
            print("\nCould not determine local subnet; skipping /24 scan.")

    if "--scan1" in sys.argv:
        scan_subnet("192.168.1", ports=(3000, 2000, 4000, 6000, 9000, 10000, 8000))
    if "--scan2" in sys.argv:
        scan_subnet("192.168.2", ports=(3000, 2000, 4000, 6000, 9000, 10000, 8000))

    print("\nDone. Likely causes if still not found:")
    print(" - camera not on your physical LAN (cable/VLAN/switch port), or")
    print(" - camera IP changed to something outside the scanned range, or")
    print(" - camera needs USB-RNDIS (install Driver/rndis6.inf, use USB link).")


if __name__ == "__main__":
    main()
