"""TCP proxy to capture exact PCB tool login bytes."""
import socket, struct, time, threading, sys

LISTEN_PORT = 3000
LISTEN_PORT_CMD = 3001
CAM = "192.168.2.32"
CAM_PORT = 3000
CAM_PORT_CMD = 3001
LOG_FILE = "D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/proxy_log.txt"

logf = open(LOG_FILE, 'w', encoding='utf-8')
lock = threading.Lock()

def log(msg, raw=b''):
    with lock:
        ts = time.time()
        line = "[%f] %s" % (ts, msg)
        print(line, flush=True)
        logf.write(line + '\n')
        if raw:
            for off in range(0, len(raw), 16):
                chunk = raw[off:off+16]
                hex_part = ' '.join('%02x' % b for b in chunk)
                ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                logf.write("  %04X: %-48s %s\n" % (off, hex_part, ascii_part))
            logf.write('\n')
        logf.flush()

def proxy_pipe(src, dst, name, other_name):
    """Forward data from src to dst, logging it."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                log("%s->%s: CLOSED" % (name, other_name))
                break
            log("%s->%s %dB" % (name, other_name, len(data)), data)
            dst.sendall(data)
    except Exception as e:
        log("%s pipe error: %s" % name, str(e))
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle_pair(client_sock, cam_host, cam_port, client_id):
    """Handle a proxied connection."""
    cam_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cam_sock.settimeout(30)
    try:
        cam_sock.connect((cam_host, cam_port))
        log("Proxy %d: connected to camera %s:%d" % (client_id, cam_host, cam_port))
    except Exception as e:
        log("Proxy %d: camera connect failed: %s" % (client_id, str(e)))
        client_sock.close()
        return

    t1 = threading.Thread(target=proxy_pipe, args=(client_sock, cam_sock, "C%d" % client_id, "S%d" % client_id))
    t2 = threading.Thread(target=proxy_pipe, args=(cam_sock, client_sock, "S%d" % client_id, "C%d" % client_id))
    t1.daemon = True
    t2.daemon = True
    t1.start()
    t2.start()

def run_proxy(listen_port, cam_port, label):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', listen_port))
    srv.listen(10)
    log("Listening on port %d (proxying to %s:%d)" % (listen_port, CAM, cam_port))
    
    counter = [0]
    while True:
        client, addr = svr.accept() if False else srv.accept()
        counter[0] += 1
        log("Connection #%d from %s:%d on port %d" % (counter[0], addr[0], addr[1], listen_port))
        t = threading.Thread(target=handle_pair, args=(client, CAM, cam_port, counter[0]))
        t.daemon = True
        t.start()

print("=" * 60)
print("TCP PROXY - Close PCB tool NOW, then reopen and connect")
print("The tool should connect through this proxy")
print("=" * 60)
print()

# Run both proxies
threads = []
for port, cam_port, label in [(3000, 3000, "video"), (3001, 3001, "command")]:
    t = threading.Thread(target=run_proxy, args=(port, cam_port, label))
    t.daemon = True
    t.start()
    threads.append(t)

print("Proxies running on ports 3000 and 3001.")
print("Redirect camera traffic to 127.0.0.1 using hosts file or netsh.")
print("Or use: netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=%s" % CAM)
print("Waiting 300 seconds...")
time.sleep(300)
logf.close()
