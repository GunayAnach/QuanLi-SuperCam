# SuperCam Session Continuation (do not delete)

Cut/paste this block into a fresh opencode/PowerShell session (run opencode on
**Windows** so it has LAN access) to continue where we left off.

-----------------------------------------------------------------------------
## Goal
Talk to the QuanLi/LangChi "SuperCam" IR camera (PCBQDIRCam) at 192.168.2.32:
login, stream visible+IR video, show temperature on hotspots.

## STATUS: CROSS-PLATFORM VIEWER RUNNING (2026-09-07)
`tools/supercam_viewer/` is a working Windows/macOS tkinter app: **LEFT = IR (160x120
raw thermal, inferno colormap), RIGHT = VIS (1920x1080 H.264 via PyAV)**, live from the camera.
- Verified: `cam_selftest.py 192.168.2.32` streams both (IR raw_avg ~3358, VIS 1080p ~1-2fps).
- Thermals (PCBtool-style): hotspot **crosshair** + live MAX degC on the IR panel; moving vertical
  **Y colorbar** (auto low/high tracks scene in auto mode); bottom **X set-point scale** (draggable
  Lo=blue/Hi=red handles = cutoffs; below-Lo blacked, above-Hi whited) + white needle. All editable
  in `settings.json` (`lo_deg/hi_deg/auto_deg`).
- TEMP MODEL IS A TUNED LINEAR PLACEHOLDER: `degC = (raw - t_offset) * t_gain` defaults
  offset=0, gain=0.01 (raw 3358 -> 33.6C). Still to derive the true 0x6051 calibration (todo 3).
- Layout: proto.py (byte-exact wires) / camera.py (session + RAW-hunt + keepalive + pumps) /
  decoders.py (IR framer + PyAV ChunkBuffer decoder) / render.py (panels/crosshair/colorbar) /
  gui.py (panels + TempSetpoints draggable scale) + settings.py. `run.py` launches; from source.
- Session history exported: `docs/session_logs/` (21 sessions, full-depth text+thinking+tools)
  via `tools/export_session.py` (reads ~/.local/share/opencode/opencode.db).

## STATUS: BOTH STREAMS CAPTURED FROM OUR OWN CLIENT (2026-09-07)
Complete! `tools/pcb_client.py` (rev 5) captured **simultaneous VISIBLE H.264 (1920x1080) AND IR
RAW thermal (39448B/frame) in one session** (18-22s, verified 124831 label). The final missing
bit was the **0x78 CONFIG `extra1` flag = codec selector**: chan4 config MUST use extra1=1
(RAW), chan2 uses extra1=0 (H264). Addendum 7 in reverse_engineering_NOTES.md has the exact
working sequence + per-slot CA channel byte (1=IR, 0=VIS) + pre-CA 0x10066/0x0066 re-negotiation.

## STATUS: VENDOR SESSION DECODED END-TO-END — BOTH STREAMS (2026-09-06)
- Ran the installed PCB_Client.exe through a local MITM relay (tools/relay3000.py,
  127.0.0.1:3000/3001 -> 192.168.2.32, via ConfigureFile.xml Url=127.0.0.1) and decoded the
  ENTIRE session from tools/relay_3000.log (~4GB) + relay_3001.log.
- PORT 3001: req 0x65 (extra1 0/1) -> 152B "Neptune"; req 0x66 (extra1 0 -> H264 1920x1080@20,
  extra1 1 -> RAW 160x120@20); CONFIG req word 0x00010078 psize=16 payload {3, chan2/4,
  SESSION-SID, 3000} -> 88B; req 0x6051 -> 184B thermometry doubles; req 0x90 -> 88B ack.
- PORT 3000: 88B LOGIN (channel field 0/1, psize=40, PWD payload) -> 56B resp payload {sid,
  0xFFFFFFFF}; 56B CLEANALARM {sid,1} -> 48B ack, then the VIDEO BYTESTREAM flows on that conn;
  48B KEEPALIVE req=0x14 every ~10s.
- VENDOR ORDER (camera yielded H.264 AND IR simultaneously):
  3001 0x65(0),0x65(1) -> 0x66(0),0x66(1) -> 3000 login ch0 -> sidA -> 3001 0x78 {3,2,sidA,3000}
  -> 3000 CA {sidA,1} (H.264 starts) -> login ch1 -> sidB -> CA {sidB,1} (IR starts)
  -> 3001 0x78 {3,4,sidB,3000} -> 0x6051 -> 0x90.
- SESSION SIDS ARE A GLOBAL COUNTER (0x34/0x35, 0x33/0x34, 0x37/0x3a seen): ALWAYS read from
  login response, never hardcode.
- IR RAW decoded: frames EXACTLY 39448B = 80B header (00 00 01 b3 ... LAUNCHDIGITAL RAW
  09 7b a0 78 14... = 160x120@20) + 38400B = 19200 x u16le 12-bit samples reshaped (120,160)
  (rendered -> real thermal scene) + ~960B tail. EXTRACTED at Temp\opencode\ir_conn9.bin (374MB).
- VISIBLE: bare Annex-B H.264 ES 1920x1080 High ~25fps with periodic b3+LAUNCHDIGITAL H264
  header + SPS/PPS; ffmpeg decodes (verified, vis_conn6_first.bin / vis_sample2.bin).

## REMAINING BLOCKERS
- NONE for streaming: own-client dual capture works. Sid allocation rotates per session/pool
  (0x33..0x43 then 0xFFFFFFFF), so the client hunts chan4 on fresh sids until RAW; do not hardcode.
- Camera wedges if a sid is RE-configured (second probe on the same sid's socket); one-probe-per-sid
  avoids it. Power-cycle when silent.

## WORKING PROTOCOL SEQUENCE (all magic little-endian)
Constants: MAGIC1=0x123AB678, MAGIC2=0x876CD321, user="video server", pwd="888888"

Frame layouts (THE reference is the vendor capture, NOT our old mk* builders — see
reverse_engineering_NOTES.md Addendum 6 for the exact 88B/56B/48B frames):
- PORT 3001 header (88B): magic@0x00, "video server"@0x04, 00+cc*11@0x10, req@0x1C,
  flag@0x20, extra1@0x24, psize@0x28, MAGIC2@0x2C, payload@0x30.
- PORT 3000 login (88B): magic@0x00, "video server"@0x04, 00+cc*11@0x10, 01007f00@0x1C,
  0001b80b(port3000)@0x20, channel@0x24, psize=40@0x28, MAGIC2@0x2C,
  PWD 40B @0x30 = "888888\0"+cc*11+"888888\0"+cc*8.
- CLEANALARM (56B): magic@0x00, cc@0x04..0x1B, 0200@0x1C, cc@0x1E.., 00..00@0x24, psize=8@0x28,
  MAGIC2@0x2C, payload {sid,1}@0x30.
- KEEPALIVE (48B): magic@0x00, cc@0x04.., 1400@0x1C, cc, channel@0x24, psize=0@0x28, MAGIC2@0x2C.
- 3001 CONFIG: req=0x00010078 (LE bytes 78 00 01 00), psize=16, payload
  {3, chan:2=VIS/4=IR, sid, 3000}.

Order (mirror vendor exactly):
1. 3001 0x65 extra1=0, extra1=1        (two conns) -> 152B "Neptune" each
2. 3001 0x66 extra1=0 (H264 VIS), extra1=1 (RAW IR)  -> 116B each (codec negotiation)
3. 3000 login ch0 -> read sidA          4. 3001 0x78 {3,2,sidA,3000}
5. 3000 CA {sidA,1} -> VISIBLE H.264     6. 3000 login ch1 -> read sidB
7. 3000 CA {sidB,1} -> IR RAW            8. 3001 0x78 {3,4,sidB,3000}
9. keepalives 0x14 every ~10s on 3000; 0x6051/0x90 on 3001 as wanted.

## NEXT STEPS
1. [DONE] pcb_client.py dual capture (vis1_* + ir1_*, verified ffprobe 1920x1080 + RAW structure).
1a [DONE] supercam_viewer cross-OS live viewer (IR|VIS side-by-side GUI) — launch `python run.py [IP]`.
2. Decode the ~960B IR-frame tail blob (candidate: visible-edge/MSX mini data for the CAM
   edge-overlay over IR — the user's desired feature). NOTE: tail contains wide metadata;
   also re-verify the exact sample window (38400B window min=0/max=8000 vs nominal 12-bit).
3. Temperature: 0x6051 stats + IR RAW counts -> °C (extract the calibration formula /
   GainFactor*... from IrAnalysisSDK.dll / vendor IRParamFile.xml Emissivity=0.95).
4. MSX edge overlay: pull GET_IMAGEFUSEPARAM/OFFSET/MSXENABLE/STRENGTH/PIXLECOORD (cmd codes
   171/173/189/191/193/195 in tools/message_cmd_table.json) on 3000/3001 to read fusion params;
   fuse visible edges onto IR in the client.
5. Temperature readout in the viewer status bar (raw_avg -> °C once formula known); optional
   PyInstaller single-file builds per OS.
5a. [DONE] Thermal features: hotspot crosshair + MAX degC, moving Y colorbar, draggable X
   Lo/Hi set-point cutoffs (below-Lo blacked / above-Hi whited). Temp model is a tunable
   linear placeholder (t_gain/t_offset in settings) until the true calibration is derived.

## Tools (D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\)
- pcb_client.py     - DEFINITIVE mirror-client: byte-exact frames, CA-before-config, RAW-hunt
                      (chan4+extra1=1 on fresh sids until RAW; chan2+extra1=0 for VIS), content-
                      routed files ir1_*/vis1_*/ir6401_*; captures BOTH streams in ONE session
- supercam_viewer/  - cross-platform viewer app (run.py + supercam/ package) + cam_selftest.py
- export_session.py - dumps opencode session history (full depth) to ../docs/session_logs/
- relay3000.py       - MITM 127.0.0.1:3000/3001 -> camera, logs hex (the discovery tool)
- parse_relay.py     - bytes-fast parser for relay_*.log (frames + streams)
- message_cmd_table.json - 176 MESSAGE_CMD_* numeric codes extracted from PCB_Client.exe .NET
- camera_capture.py  - dynamic src-ids + config + capture (pre-vendor-order; superseded by client)

## Environment
- Camera: 192.168.2.32, PC: 192.168.2.43, iface "Realtek PCIe GbE Family Controller"
- 32-bit Python: C:\Users\G\AppData\Local\Temp\opencode\py32\python.exe
- System Python (64-bit 3.12.10) has OpenCV 5.0.0 + ffmpeg available
- Camera is sensitive: wait 30-60s between probes; reboots when probed aggressively
