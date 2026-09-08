"""TCP relay/MITM for the SuperCam camera protocol.

Listens on 127.0.0.1:{3000,3001}, forwards every connection to 192.168.2.32 on
the same port, and logs the hex of every direction in both directions, so we can
see EXACTLY how the vendor PCB_Client.exe frames its requests (esp. the GET/SET
commands for temperature, palette, MSX fusion, pixel-mapping).

Run:  python relay3000.py
Then point the vendor app (ConfigureFile.xml Url=127.0.0.1) at this relay.
Logs written to relay_3000.log / relay_3001.log (append).
"""
import socket, threading, time, datetime, os, sys

CAM = "192.168.2.32"
PORTS = [3000, 3001]
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()


def log(port, direction, conn_id, count, data):
    with LOCK:
        path = os.path.join(HERE, "relay_%d.log" % port)
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        head = "== %s conn#%d %s %dB  data %dB\n" % (ts, conn_id, direction, count, len(data))
        with open(path, "a") as f:
            f.write(head)
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                hexs = " ".join("%02x" % b for b in chunk)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                f.write("  %06x  %-47s  %s\n" % (i, hexs, asc))
            f.flush()


def pipe(src, dst, port, conn_id, direction, stats):
    while True:
        try:
            chunk = src.recv(65536)
        except Exception:
            break
        if not chunk:
            break
        stats[0] += len(chunk)
        log(port, direction, conn_id, len(chunk), chunk)
        try:
            dst.sendall(chunk)
        except Exception:
            break


def handle(client, port, conn_id):
    print("conn#%d to %s:%d (local relay)" % (conn_id, CAM, port))
    upstream = socket.socket()
    upstream.settimeout(10)
    try:
        upstream.connect((CAM, port))
    except Exception as e:
        print("  upstream connect failed: %r" % e)
        client.close()
        return
    stats = [0, 0]  # incoming bytes, outgoing bytes
    t1 = threading.Thread(target=pipe, args=(client, upstream, port, conn_id, "C->S", [stats[0]]), daemon=True)
    t2 = threading.Thread(target=pipe, args=(upstream, client, port, conn_id, "S->C", [stats[1]]), daemon=True)
    t1.start(); t2.start()
    t1.join(); t2.join()
    print("conn#%d closed (C->S %dB, S->C %dB)" % (conn_id, stats[0], stats[1]))
    for s in (client, upstream):
        try:
            s.close()
        except Exception:
            pass


def main():
    conn_id = [0]
    servers = []
    for port in PORTS:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(8)
        servers.append((port, srv))
        print("relay listening on 127.0.0.1:%d -> %s:%d" % (port, CAM, port))
    print("point vendor app at 127.0.0.1; logs -> relay_3000.log / relay_3001.log")
    while True:
        for port, srv in servers:
            srv.settimeout(0.5)
            try:
                client, _ = srv.accept()
            except socket.timeout:
                continue
            conn_id[0] += 1
            threading.Thread(target=handle, args=(client, port, conn_id[0]), daemon=True).start()


if __name__ == "__main__":
    main()