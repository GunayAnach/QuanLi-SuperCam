import socket,time,sys
# Connect to camera, send nothing, read whatever it sends first (banner/greeting).
s=socket.socket(); s.settimeout(3)
s.connect(('192.168.2.32',3000))
print("connected")
s.setblocking(False)
tot=b""
t0=time.time()
while time.time()-t0<6:
    try:
        d=s.recv(65536)
        if not d: break
        tot+=d
        print("recv %d bytes:"%len(d), d.hex())
    except BlockingIOError:
        time.sleep(0.05)
    except socket.timeout:
        pass
print("total received:",tot.hex())
s.close()