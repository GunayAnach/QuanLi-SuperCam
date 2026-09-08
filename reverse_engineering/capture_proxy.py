#!/usr/bin/env python3
"""
capture_proxy.py - TCP proxy to capture the QuanLi/LangChi camera protocol.

Runs a listening socket on 127.0.0.1:3100 that forwards everything to
192.168.2.32:3000 (the camera). Any bytes in both directions are written to
ctos_capture.bin (client->camera) and stoc_capture.bin (camera->client).

Configure PCB_Client.exe to connect to 127.0.0.1:3100 instead of the camera IP,
then connect in the client. The raw protocol bytes are captured for analysis.
"""

import socket
import threading
import time
import sys
import os

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "3000"))
CAM_HOST = "192.168.2.32"
CAM_PORT = int(os.environ.get("CAM_PORT", "3000"))

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
CTOS_LOG = os.path.join(LOG_DIR, "ctos_capture.bin")
STOC_LOG = os.path.join(LOG_DIR, "stoc_capture.bin")


def pump(src, dst, direction, log_path):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
            print(f"[{direction}] {len(data)}B: {data.hex()[:240]}")
            with open(log_path, "ab") as f:
                f.write(data)
    except Exception as e:
        print(f"[{direction}] ended: {e}")
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def handle(client, caddr):
    print(f"[PROXY] CONNECT {caddr}")
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        upstream.connect((CAM_HOST, CAM_PORT))
        print(f"[PROXY] Upstream connected to {CAM_HOST}:{CAM_PORT}")
    except Exception as e:
        print(f"[PROXY] Upstream connect failed: {e}")
        client.close()
        return

    threading.Thread(target=pump, args=(client, upstream, "CTOS", CTOS_LOG), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client, "STOC", STOC_LOG), daemon=True).start()


def main():
    for p in (CTOS_LOG, STOC_LOG):
        if os.path.exists(p):
            os.remove(p)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(5)
    print(f"[PROXY] Listening on {LISTEN_HOST}:{LISTEN_PORT} -> {CAM_HOST}:{CAM_PORT}")
    print(f"[PROXY] Capturing to {CTOS_LOG} and {STOC_LOG}")
    print(f"[PROXY] Point PCB_Client.exe at {LISTEN_HOST}:{LISTEN_PORT}")

    while True:
        client, caddr = srv.accept()
        threading.Thread(target=handle, args=(client, caddr), daemon=True).start()


if __name__ == "__main__":
    main()
