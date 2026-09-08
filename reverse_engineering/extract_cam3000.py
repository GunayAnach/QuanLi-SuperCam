import re
src="D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/capture3.txt"
hop="192.168.2.32.3000"
pat=re.compile(hop.encode())
out=[]
n=0
buf=b""
with open(src,"rb") as f:
    while True:
        chunk=f.read(1<<20)
        if not chunk: break
        buf+=chunk
        while True:
            nl=buf.find(b"\n")
            if nl<0: break
            line=buf[:nl+1]; buf=buf[nl+1:]
            txt=line.replace(b"\x00",b"")
            if b"192.168.2.32.3000" in txt:
                n+=1
                out.append(txt)
print("camera3000 lines:",n)
with open("D:/OneDrive/Development/QuanLi Thermal Camera - SuperCam/tools/cam3000.txt","wb") as g:
    g.writelines(out)
syn=sum(1 for l in out if b"S]," in l or b"S]" in l)
defmt=sum(1 for l in out if b"[" in l)
print("raw line types syn-like:",syn)