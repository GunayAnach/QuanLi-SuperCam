import sys,time,os,json
from scapy.all import *
CAM="192.168.2.32"; DPORT=3000
OUT="D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/control_dump/"
os.makedirs(OUT,exist_ok=True)
MAXPLEN=1500   # only capture IPv4 total length < this (exclude 1514 MTU video), keep control msgs
seen=[]
t0=time.time()

def handle(pkt):
    if not pkt.haslayer(TCP): return
    ip=pkt[IP]; tcp=pkt[TCP]
    if ip.dst==CAM and tcp.dport==DPORT: tag='C2S'; peer=ip.src; tport=tcp.sport
    elif ip.src==CAM and tcp.sport==DPORT: tag='S2C'; peer=ip.dst; tport=tcp.dport
    else: return
    pl=bytes(tcp.payload)
    if not pl: return
    if len(pl)>=MAXPLEN: return   # skip video frames
    # keep small S2C too (len 28 ack + any small temp responses)
    # record
    rec={'t':round(time.time()-t0,3),'dir':tag,'peerport':tport,'len':len(pl),'hex':pl.hex()}
    seen.append(rec)
    for _try in range(5):
        try:
            with open(os.path.join(OUT,"packets.txt"),"a") as f:
                f.write("[%7.3f %s p%d len=%d] %s\n"%(rec['t'],tag,tport,len(pl),pl.hex()))
            break
        except PermissionError:
            time.sleep(0.2)

def main():
    print("Sniffing CONTROL packets to/from %s:%d for 30s. Keep live view open + keep refreshing temp."%(CAM,DPORT),flush=True)
    IF="7"; 
    import sys as _s
    if len(_s.argv)>1: IF=_s.argv[1]
    sniff(prn=handle,store=False,timeout=100,iface=IF)
    print("captured",len(seen),"small packets")

main()