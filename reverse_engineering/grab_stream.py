import socket, time

CAM='192.168.2.32'; PORT=3000
KEEPALIVE=bytes.fromhex('78b63a12cccccccccccccccccccccccccccccccccccccccccccccccc05000000cccccccc010000000000000021d36c87')

s=socket.socket()
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
s.settimeout(8)
s.connect((CAM,PORT))
print('connected to %s:%d'%s.getsockname(),flush=True)

# send keep-alive
s.sendall(KEEPALIVE)
print('sent keep-alive',flush=True)

data=b''
t0=time.time()
while time.time()-t0<6:
    try:
        chunk=s.recv(65536)
        if not chunk: break
        data+=chunk
        print('\rrecv %dKB %ds'%(len(data)//1024,time.time()-t0),end='',flush=True)
    except socket.timeout:
        break
print()
s.close()
print('total:',len(data),'bytes')
open('D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/stream_raw.bin','wb').write(data)
print('saved stream_raw.bin')
