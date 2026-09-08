import os, time, sys

ctos = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ctos_capture.bin")
stoc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stoc_capture.bin")

last_c = 0
last_s = 0
idle = 0
for i in range(120):
    c = os.path.getsize(ctos) if os.path.exists(ctos) else 0
    s = os.path.getsize(stoc) if os.path.exists(stoc) else 0
    print(f"[{time.strftime('%H:%M:%S')}] CTOS={c}B (+{c-last_c})  STOC={s}B (+{s-last_s})")
    if c > 0 or s > 0:
        idle = 0
    else:
        idle += 1
    last_c = c
    last_s = s
    if idle >= 15 and i > 20:
        print("No traffic yet - connect PCB_Client to 127.0.0.1 (port defaults to 3000) ...")
        idle = 0
    time.sleep(5)
