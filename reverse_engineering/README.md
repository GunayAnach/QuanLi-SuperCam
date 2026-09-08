# QuanLi "SuperCam" Infrared Camera — Reverse Engineering Notes

Reverse-engineered from the shipped Windows client binaries in this folder.

## What this device is

- OEM: **LangChi (朗驰/Lancheng)**, sold under the "QianLi / QuanLi / 潜力 & 朗驰" brand.
- It is a **Hikvision-architecture/LUA-style** IR (thermal) IPC module, not ONVIF/RTSP/open http.
- Product name `PCBQDIRCam`, device name `PCB速诊仪` (PCB fast-diagnosis instrument).
- The default camera IP stored by the client is **192.168.1.200**, protocol port **3000** (from
  `ConfigureFile/ConfigureFile.xml`).

## Important: this is NOT a normal IP camera

- The Windows client uses a low-level C++ SDK called **`NetClient.dll`** (project path in the PDB:
  `d:\document\vs2013project\svncheck\src\lump4net_ir` → module `LUMP4Net_IR`, `MP4NetLib.pdb`).
- It is built on an OpenCV 2.4.9 bundle.
- The thermal SDK is **`IrAnalysisSDK.dll`** (exports `IR_SDK_Read/Write/GetTemp/NewImage/Detory/DataOption`).
- The WPF GUI is **`PCB_Client.exe`** (a real .NET assembly), which P/Invokes
  `CamSearch.dll` for device discovery and `NetClient.dll` for the streaming/control connection.

## Command protocol (MESSAGE_CMD_* — Hikvision family)

`PCB_Client.exe` carries a very large table of `MESSAGE_CMD_*` constants. The thermal-relevant ones are:

```
MESSAGE_CMD_AFFIRMUSER               (login / user verify)
MESSAGE_CMD_GETSYSUSER / SETSYSUSER
MESSAGE_CMD_GET_GETTEMPVALUE         (temperature value)
MESSAGE_CMD_GET_GETTEMPDATA          (bulk temperature data)
MESSAGE_CMD_GET_REGIONTEMPINFOLIST   (region temperature info)
MESSAGE_CMD_GET_ISOTHERM / SET_ISOTHERM
MESSAGE_CMD_GET_TEMPPARAM / SET_TEMPPARAM
MESSAGE_CMD_GET_TEMPCALIBPARAM / SET_TEMPCALIBPARAM
MESSAGE_CMD_GET_COLORPALETTE / SET_COLORPALETTE
MESSAGE_CMD_GET_IMAGEFUSEPARAM / SET_IMAGEFUSEPARAM
MESSAGE_CMD_GET_IMAGEFUSEOFFSET / SET_IMAGEFUSEOFFSET
MESSAGE_CMD_GET_MSXENABLE / SET_MSXENABLE   (MSX image fusion)
MESSAGE_CMD_GET_MSXSTRENGTH / SET_MSXSTRENGTH
MESSAGE_CMD_GET_MSXDISTANCE / SET_MSXDISTANCE
MESSAGE_CMD_GET_PIXLECOORD / SET_PIXLECOORD
MESSAGE_CMD_GET_TAUGAINMODE / SET_TAUGAINMODE  (FLIR TAU thermal core!)
MESSAGE_CMD_GET_FFCCTRL / SET_FFCCTRL          (flat-field correction)
MESSAGE_CMD_GET_AGCPARAM / SET_AGCPARAM
MESSAGE_CMD_CAPTUREJPEG / ENCKEYFRAME / SETVIDEOINTYPE / SETVIDEOENCMAP / GETVIDEOOUTMODE
MESSAGE_CMD_SETRECORD...  etc.
```

The `GET_TAUGAINMODE` / `SET_FFCCTRL` strings reveal the sensor is (or behaves like) a
**FLIR TAU2-style thermal core** with MSX fusion — the same command vocabulary appears in
Hikvision's thermal SDK for TAU-based cameras.

LINKS:
- `LAUMSG_*` = link/transport message types (VIDEOLOST, VIDEOMOTION, ALARM, etc.)

## SDK entry points (NetClient.dll exports, `VSNET_*`)

The connection lifecycle:

```
VSNET_ClientStartup                 init
VSNET_ClientSetDevInfo              set IP/URL/port/user/password (device info)
VSNET_ClientMessageOpen             open the message/command channel  (MESSAGE_CMD_*)
VSNET_ClientMessageClose            close it
VSNET_ClientMessageOpt / ReadMessage
VSNET_ClientStart / StartView       start video
VSNET_ClientStop / StopView
VSNET_ClientSetTempData             send temp config
VSNET_ClientGetTempData             read temp config
VSNET_ClientSetTempSpan             temperature range (min/max)
VSNET_ClientRegTempCallBack         register temperature events
VSNET_ClientCapture / CapturePicture / JpegCapStart
VSNET_ClientSetPaletteMode / GetPaletteColor
VSNET_ClientSetFusionViewMode / FusionStrength / FusionOffsetHorz/Vert
VSNET_ClientSetImageShow / SetWnd / CleanVideoDisplayBuffer
VSNET_TempTableImport               upload radiometric "Radiometric JPEG" temp table
VSNET_FFF2Temp / FFF2Raw            convert FFF radiometric data -> temp / raw
VSNET_ClientCleanup
```

Supporting classes seen in the mangled symbols:
`CClientAdmin`, `CMessageAdmin`, `CMsgBuffAdmin`, `CTransmitAdmin`, `CVStranChan`,
`CVSTranListen`, `CNFileDataQing`, `StreamPlayer`, `SignCert...` (magic/token structures).

## Device discovery (CamSearch.dll)  ← KEY for your network problem

`CamSearch.dll` is a 32-bit DLL using **Winsock (WS2_32)**. Exports:

```
CAMSEAR_Startup
CAMSEAR_Searchcam             (new discovery)
CAMSEAR_Searchcam_old         (old broadcast discovery)
CAMSEAR_SearchSeturl / _old   (set the target url for direct connect)
CAMSEAR_SearchReset / Restore
CAMSEAR_Cleanup
_CAMSEAR_CorssingSearchcam@12 (crossing/LAN-WAN search)
```

Reverse-engineered `CAMSEAR_Searchcam` (new):

| Item | Value |
|------|-------|
| transport | **UDP** (`socket(AF_INET, SOCK_DGRAM, 0)`) |
| local bind port | **10002** (`htons(0x2712)`) |
| destination port | **10001** (`htons(0x2711)`) — broadcast target |
| packet length | **54 bytes** (`0x36`) |
| packet magic | contains `0x123AB678` and `0x876CD321` |
| socket options | `SO_BROADCAST` etc. (`setsockopt`) |

So the camera is found by sending a **54-byte UDP datagram to UDP/10001** (broadcast
`255.255.255.255` or subnet directed-broadcast, or unicast to 192.168.1.200), carrying the
magic `12 3A B6 78` / `87 6C D3 21` signature; the camera replies to that socket.

The `_old` variant additionally sets `SO_BROADCAST` + `SO_REUSEADDR` and can use
`htonl(INADDR_BROADCAST)` (255.255.255.255) via `CAMSEAR_SearchSeturl`.

## Why you cannot discover it (most likely causes)

1. **Subnet / layer-2 mismatch.** The camera is statically set to `192.168.1.200`.
   UDP broadcast discovery only works when your PC is on the **same subnet/VLAN** as the
   camera (same L2 broadcast domain). If your PC is on e.g. `192.168.50.x`, broadcast still
   reaches the `192.168.1.200` camera only if both are on the same switch/VLAN without
   inter-VLAN filtering.
2. **Use the camera's default static IP directly.** Even without discovery you can try
   reaching `192.168.1.200` directly (set your NIC to `192.168.1.x/24` temporarily) and send
   the 54-byte search to that unicast address, or just probe TCP `192.168.1.200:3000`.
   (The shipped `ConfigureFile.xml` has `Url=192.168.1.200`, `Port=3000`, so that is the
   configured address of THIS unit.)
3. **Windows Firewall / broadcast filtering.** Allow UDP out on 10001/10002 (and the TCP
   control port) and inbound replies. Many managed switches block directed broadcasts.
4. **WSL2 in particular.** If you test from **WSL2**, the VM uses a NAT virtual NIC
   (e.g. `172.27.x.x`) that is **NOT on your physical LAN** — it cannot see the camera or
   its broadcast domain at all. Run the discovery from **native Windows** (or enable WSL2
   *mirrored* networking), or run the bundled `CamSearch.dll`/client on Windows.
5. **The sound / "port 3000 loads" clue** = the camera's embedded **HTTP-ish socket is alive**
   on TCP 3000 (it plays a boot/UI sound and the LAN LEDs blink) but the *discovery probe* and
   *video/command* channels are the proprietary ones above — HTTP browsing port 3000 won't
   enumerate as a normal camera.

## To talk to the camera yourself (plan)

1. **Discover**: replicate the 54-byte UDP probe to 10001 → parse the reply to get its IP.
   (See `camera_discover.py` in `tools/`.)
2. **Login**: open TCP to the control port (the client uses `VSNET_ClientSetDevInfo`
   with `Port=3000`, user/password via `MESSAGE_CMD_AFFIRMUSER`) and exchange the
   Hikvision-style message envelope carrying `MESSAGE_CMD_AFFIRMUSER`.
3. **Stream**: `VSNET_ClientStart/StartView` opens the main video channel
   (H.264 via bundled `hi_h264dec` library; `FrameFormat`, `MESSAGE_CMD_SETVIDEOINTYPE`).
4. **Temperature**: `MESSAGE_CMD_GET_REGIONTEMPINFOLIST` / `GET_GETTEMPTEMPDATA` give
   radiometric data; `VSNET_FFF2Temp`/`TempTableImport` convert radiometric JPEG to °C.

A full packet-level implementation requires either:
  - reverse-engineering the exact `VSTranSend.cpp` message framing + the login hash
    (Hikvision-style), or
  - cleanly calling the shipped `NetClient.dll` + `CamSearch.dll` from your own code
    (easiest and most reliable — they are self-contained C++ DLLs with a stable C ABI).

## Recommended approach (fastest path)

**Call the vendor DLLs directly** via a small wrapper (C, C#, or Python `ctypes`/`cffi`):
load `CamSearch.dll` for discovery and `NetClient.dll` for connect/stream/temperature.
That gives you full functionality without needing to re-derive the packet framing/login
hash, and is far less work than re-implementing the protocol from scratch.

-------------------------------------------------------------------------------
# ADDENDUM (2026-09-04 session)

## Live state
- Camera REACHABLE at **192.168.2.32:3000** (TCP open, user confirms PCB tool works).
- NOT RTSP/ONVIF/HTTP. Pure proprietary binary protocol on TCP/3000.
- A plain TCP connect to :3000 returns **no banner**; the camera waits for a framed
  command message. So the "test connection" in the client is not just a TCP open —
  it requires a valid protocol handshake, hence "device cannot be connected" on any
  bare/proxied connect.

## P/Invoke signatures extracted (from PCB_Client.exe .NET metadata, tools/extract_pinvoke.py)
Calling convention = **Winapi (=> __stdcall on 32-bit)**. All ret `uint32`.
- `CAMSEAR_Startup/Cleanup()` -> int
- `CAMSEAR_Searchcam(uint32, <var>, <0x14>)` -> int     (3 args)
- `CAMSEAR_SearchSeturl(int16[], <7 ptr>, int32, int32, int32, <ptr>)` (11 args)
- `CAMSEAR_SearchReset(int16[], <ptr>)` (2 args)
- `IR_SDK_Read(<ptr>, SDK_MEASURE)` -> uint32
- `IR_SDK_Write(<0x18>, <ptr>)`
- `IR_SDK_GetTemp(<0x18>, int64, float64[])` (3 args)
- `IR_SDK_NewImage(<0x18>, SDK_ENV_INFO)`
- `IR_SDK_DataOption(<0x18>, SDK_ENV_INFO, <0x70>)`
- `VSNET_ClientStartup(int64, <0x18>, <var>, <0x80>, <0xac>)` (5 args)  [0x18=pointer,0x80=hrawnd,0xac=hwnd]
- `VSNET_ClientWaitTime(uint32,uint32)`
- `VSNET_ClientCleanup()`
- `VSNET_ClientStart(<ptr>, SDK_ENV_INFO, <0x80>, <0x90>)` (4 args)
- `VSNET_ClientStop(uint32)`
- `VSNET_ClientSetDelayTime(uint32,uint32)`
- `VSNET_ClientStartView(uint32,uint32)` / `VSNET_ClientStopView(uint32)`
- `VSNET_ClientSetImageShow(uint32,char)` / `VSNET_ClientSetWnd(uint32,<0x18>)` / RefrenshWnd
- `VSNET_ClientGetVideoSize(uint32, SDK_SHAPE_TYPE, SDK_SHAPE_TYPE)`
- `VSNET_ClientCapturePicture(uint32,<ptr>)`
- `VSNET_ClientMessageOpen(<ptr>,<ptr>,<ptr>,<ptr>,int32)` (5 args)
- `VSNET_ClientMessageOpt(uint32,uint32,uint32,<0x18>,<0x18>,<0x18>)` (6 args)
- `VSNET_ClientMessageClose(uint32)`
- `VSNET_ClientSetTempSpan(uint32, SDK_ENV_INFO)`
- `VSNET_ClientSetPaletteMode(uint32, <callback>)`
- `VSNET_ClientRegTempCallBack(uint32,<var>,<0x80>)`
- `VSNET_ClientFuseStart/Stop`, `VSNET_ClientGetPaletteColor(uint32,int16[])`
- `VSNET_ClientSetFusionStrength(uint32,int16)`, OffsetHorz/Vert(uint32,uint32)
- `VSNET_ClientSetDevInfo(uint32, SDK_ENV_INFO)`  ← note: env struct reused by wrapper
- `VSNET_ClientSetFusionViewMode(uint32,<callback>)`
- `VSNET_ClientCapture(uint32,<callback>,<ptr>)`

## SDK struct layouts (tools/extract_structs.py)
- `SDK_ENV_INFO`: 10 x float64 => emissivity, winTrans, winTemp, winRefl, reflTemp,
  atmTrans, atmTemp, bkgTemp, distance, humidity  (size 80 bytes)
- `SDK_IR_IMG`: int32 usWidth, usHeight, usStride; ptr pusData
- `SDK_VIS_IMG`: enType(enum), uint32/uiLen, ptr pucData
- `SDK_AGC`: float64 mintemp, maxtemp; uint32 isAuto
- `DEV_TEMP_SPAN`: float64 fTempMin, fTempMax; uint32 bAuto  (already-known temp span)
- `SDK_PALETTE`: int16 bMode
- `SDK_SPOT`: usX,usY (int32); `SDK_BOX`: usX,usY,usWidth,usHeight (int32)
- `SDK_MEASURE`: int64 uiNum; ptr pstObject
- `VSNETRECT`: uint32 left,top,right,bottom
- `SDK_FUSION`: zoomFactor(double), xpan/ypan (u16), first/lastFusionX/Y (u16),
  colorMode,useBlending,fusionMode,Reserved1 (int16), rotateDeg(double),
  blend(double), bLevel(u16), reserve3(u16), iIROffsetX(u32), Reserved2(int16[])
- `SDK_SHAPE_TYPE`, `SDK_DATA`, `SDK_LABEL`(x,y int32 + char[16] name) etc.

## Protocol capture status
- GUI connect dialog only accepts an **IP** (fixed port **3000**); it did NOT accept the
  proxy address cleanly and returned "device cannot be connected". The client's connect
  path goes through discovery (CamSearch) + the VSTran handshake, not a bare TCP open,
  so a TCP-only proxy is insufficient (video/audio use separate UDP return channels the
  camera streams back to the client's bound ports).
- To capture the TRUE wire bytes without admin (pktmon/npcap need elevation):
  drive `NetClient.dll` + `CamSearch.dll` directly from **32-bit Python** (ctypes)
  pointed at the real camera; the DLLs open their own TCP+UDP channels on the LAN, so
  return routing works. Then sniff/record those bytes.

## Cross-platform plan (recommended path)
1. **Phase 1 (Windows, today):** 32-bit Python + ctypes wrapper -> live IR+visible video
   (OpenCV) + temperature callback. Proves end-to-end.
2. **Phase 2 (wire capture):** While Phase-1 DLL session is live, capture the exact
   bytes (raw socket bind on same ports / second NIC / admin pktmon) to recover the
   framing + login hash + temp opcodes.
3. **Phase 3 (cross-platform):** Reimplement the pure binary client in Python (socket)
   using Phase-2 captures; Visualise with OpenCV/CV2; temperature overlay from the
   radiometric payload. Works on Windows/macOS/Linux with no vendor DLLs.

## Tools added this session (tools/)
- `extract_pinvoke.py`  - dumps exact P/Invoke signatures from PCB_Client.exe metadata
- `extract_structs.py`  - dumps SDK_* struct field layouts
- `capture_proxy.py`    - TCP proxy (used to try GUI capture; GUI overriding port
                          makes it not directly usable - kept for reference)
- `monitor_capture.py`  - polls the capture files for activity
- `parse_dllimport.ps1` - 32-bit PS .NET reflection attempt (superseded by python)
- 32-bit Python installed at `C:\Users\G\AppData\Local\Temp\opencode\py32\python.exe`
  (needed because NetClient.dll/CamSearch.dll are x86).

## LIVE WIRE CAPTURE � CONFIRMED (2026-09-04, capture3/sniff_control)

Connected for real over Ethernet. PC NIC = 192.168.2.43 (Realtek, MAC 60-18-95-6E-DC-31);
camera = 192.168.2.32 (MAC 00-E8-01-06-65-24), TCP/3000. pktmon text lacks payload hex;
used scapy on iface name ^Realtek PCIe GbE Family Controller^ (NOT index) to get payloads
(tools/sniff_control.py, output tools/control_dump/packets.txt, 20407 small pkts).

Key facts:
- Client opens **4 simultaneous TCP/3000 connections** (src ports 5430..5433) for one live view
  (likely: IR video, visible video, control, aux). 3000 is the control/stream port; 3001 also
  used (CloseWait/Established seen) ? 3001 = second/alt stream or discovery-response port.
- Camera sends **NOTHING on connect** (silent; tested tools/probe_greeting.py). Client must
  send first.
- **The video/stream payload is ENCRYPTED** (high-entropy; 1460-byte TCP segments, no plaintext).
  A real crypto layer exists (RC4/AES-� keyed during login). This is the hard part to port.
- Client?camera C2S control frames are tiny 48-byte keep-alives, ~every 10 s:
    78 b6 3a 12 | cc cc � (6 dw) | 05 00 00 00 | cc cc cc cc | 00/01 00 00 00 | 00 00 00 00 | 21 d3 6c 87
  Word layout (LE): [0]=0x123AB678 (MAGIC1) pad 0xCC x6  [7]=0x00000005  [8]=0xCCCCCCCC
  [9]=0x00000000/1 (stream/channel selector)  [10]=0  [11]=0x876CD321 (MAGIC2).
  ? framing fingerprint = header magic 0x123AB678 � tail magic 0x876CD321 (same two magics as
  the UDP discovery probe). Camera answers keep-alive with 28 x 0x00 (len=28 S2C).
- Video stream dominates: ~19.5k x 1460-byte S2C segments + occasional smaller frame-enders
  (612..863 B) = one per IR frame.

? Porting a pure-socket viewer requires recovering the crypto key + decrypt routine from
NetClient.dll / IrAnalysisSDK.dll (or capturing a login to observe key exchange). Straightly
re-driving the 48-byte keep-alive got zero plaintext stream. High difficulty.

Captures kept: tools/capture3.etl/.txt (1.37M pkts, camera-3000 subset tools/cam3000.txt),
tools/control_dump/packets.txt, tools/sniff_login.py, tools/sniff_control.py, tools/probe_greeting.py.

### Addendum 2 (2026-09-04 continued)

**VIDEO IS NOT ENCRYPTED � IT'S STANDARD H.264 IN PLAINTEXT.**

Ports 5433 (and likely 5430/5432) push compressed video identified as H.264 Annex-B by start codes and NAL types:
- SPS (0x67) �18, PPS (0x68) �18, IDR (0x65) �18, non-IDR (0x61) �492
- MPEG-1 sequence header (0x000001B3) �667, MPEG picture start (0x000001E0) �143
- There are 2 parallel video streams (IR + visible), one H.264 and one MPEG-1/MPEG-like.

ffprobe on the extracted segment correctly identifies codec_name=h264.

**48-byte magic frame = core protocol ping/pong structure.**

Frame layout (LE):
`
[0] 0x123AB678  (MAGIC1 � same as UDP discovery probe)
[1]-[6] 0xCCCCCCCC (6 words, pad/don't-care � .NET P/Invoke artifact)
[7] command word (lower byte = cmd code, upper 3 bytes = status/version/flags)
[8] 0xCCCCCCCC (pad)
[9] channel/stream selector (0x00 = stream 0, 0x01 = stream 1)
[10] 0x00000000
[11] 0x876CD321 (MAGIC2 � same as UDP discovery probe)
`

Client sends  5 00 00 00 (command 0x05 = keepalive) on both channels.
Camera responds  5 00 94 ff (LE = 0xFF940005) = status/version response.

**Login command required** � fresh connection with only keepalive received no video. The login command (MESSAGE_CMD_AFFIRMUSER or similar) must be captured from a fresh client connection, as the sniffer only captured post-login steady-state.

Next step: sniff the first bytes of a fresh TCP connection (capture LOGIN sequence) by restarting PCB_Client while sniffer runs, then replicate the login to get video flowing on a raw socket.

Captured artifacts saved: tools/stream_raw.bin, tools/ir_stream.h264, tools/sample_ir.h264, tools/grab_stream.py

### Addendum 3 (2026-09-04 later) — VIDEO STREAMING SOLVED

**Full working sequence that produces live video on the visible channel:**

1. **3001 init req=0x65** — 2 connections (extra1=1, then extra1=0). Each gets 152B "Neptune" response.
2. **3001 init req=0x66** — 2 connections (extra1=0 → 116B `H264` 1920x1080; extra1=1 → 116B `RAW\0` 160x120).
   - extra1=0 selects VISIBLE H.264 stream (1920x1080).
   - extra1=1 selects IR RAW thermal stream (160x120).
3. **3000 login** — 2 connections (ch0 and ch1), each gets 56B cmd=0x00000001.
4. **CLEANALARM cmd=0xCCCC0002** — on separate 3000 connection(s). 48B header with channel field
   (ch0→channel=0, ch1→channel=1), get 6B ack, send 8B payload (ch0→`34000000 01000000`,
   ch1→`35000000 01000000`), get 48B cmd=0x00000002 response.
5. **Video flows** on the CLEANALARM connection (H.264 visible channel; RAW for IR).

**Working `mk3001()` 88-byte frame (headers at 0x1C/0x30 for "888888", command at 0x44, flag 0x48,
extra1 0x4C, psize 0x50).**

`tools/camera_viewer.py` — capture 29.5MB visible H.264 in 30s (640x480 or streams at higher res).
`tools/camera_exact.py` — first to get 20.5MB in 20s; verify H.264 via ffmpeg.
`tools/stream_visible.h264` — saved H.264; decodes to 1920x1080 via ffmpeg (confirmed with ffprobe).

**IR channel blocker**: CLEANALARM ch1 persistently returns cmd=0xFF9B0002 (channel not configured).
The camera appears to enter a degraded state after repeated aggressive probing — a fresh power
cycle restores both streams (per capture where both 62564 and 62565 stream simultaneously).
3001 config handshake (req=0x00010078) times out in degraded state but works in capture.
IR RAW stream is 160x120 radiometric (temperature) data — NOT H.264 — decode via thermometry.

## Temperature API (from MESSAGE_CMD_* - not yet probed live)
- MESSAGE_CMD_GET_GETTEMPVALUE (170) / GET_GETTEMPDATA (bulk) / GET_REGIONTEMPINFOLIST (187)
- These are sent on port 3000 login connections after streaming starts.
- IR RAW 160x120 payload → FLIR-TAU-style radiometric → °C via IrAnalysisSDK (IR_SDK_GetTemp / VSNET_FFF2Temp).

### Addendum 4 (2026-09-06) — SOURCE-ID MECHANISM for CLEANALARM (critical)
- **login (3000) response payload = `XX 00 00 00 ff ff ff ff` where XX is the CURRENT
  VIDEO-SOURCE-ID for that login's channel.** Healthy capture camera: ch0→0x34 (visible),
  ch1→0x35 (IR). This PCBQDIRCam unit currently reports ch0→0x33, ch1→0x34.
- **CLEANALARM (cmd=0xCCCC0002) payload MUST use the login-reported source id: `{srcid, 1}`.**
  Matching → cmd=0x00000002 ACCEPTED. Mismatch → cmd=0xFF9B0002 error.
- Source ids SHIFT across sessions/logins (0x33/0x34/0x35 all observed) — always read the
  login payload before building the CLEANALARM payload.
- Going too many sessions deep the camera stops producing data even with accepted CLEANALARM
  (CA 0x00000002 but 0 bytes after >15s) — needs power cycle to recover streaming.
- login psize field MUST be 40 (0x28=40) or login fails cmd=0xFF950001.
- 3001 req=0x00006051 (psize=96, payload [0,0x58,0..]) → 184B thermometry-stats response
  (works even when video wedged): header + {0, 0x58, count≈12, timestamp@0x64,
  doubles from 0x68, final double = 1.0 (emissivity)}. NOT pixel data.

### Addendum 5 (2026-09-06) — LIVE VISIBLE STREAMING REPRODUCIBLE (unit-specific mapping)
- Source-ID value = CONTENT TYPE (0x34=visible H.264, 0x35=IR RAW), assigned to login
  channels per-unit. **Channel INDEX is NOT fixed**: capture-camera → visible on ch0 (0x34),
  this PCBQDIRCam unit → ch0 gets id **0x33 (inert, 0 bytes always)**, ch1 gets **0x34
  (VISIBLE)**. Never chase the channel — always read login ids and follow the value.
- Working full sequence for THIS unit (reproduced 3x, live-verified): login ch0+ch1 → read
  ids → CA ch1 {0x34,1} + CA ch0 {0x33,1} (both 0x00000002) → config chan2/0x34 3001 (88B,
  = the visible config; chan4/0x35 IR config ALWAYS times out on this unit) → cmd 0x14 on
  logins → H.264 flows on the ch1 CA conn.
- Captures verified: stream_vis_20260906_104315.bin 7.56MB/25s, _104546.bin 9.06MB/30s;
  `ffmpeg -f h264` → 1920x1080 H.264 High ~25fps; frame signalstats YAVG=115, YMIN/MAX
  19/235 (real scene). camera_live.py ran 45s displaying frames.
- On this unit the IR video source (0x35) is NEVER assigned to a login; login channels 2..5
  are rejected (cmd=0xFF950001). IR pull-path unknowns remain (MESSAGE_CMD_GET_GETTEMPDATA on
  3000/3001).

## DEFINITIVE VISIBLE-STREAM PROCEDURE (worked, 30s→29.5MB, 8s→8.6MB, decoded to 1920x1080)
1. Power-cycle camera, WAIT for it to boot (~60s), then run IMMEDIATELY before probing.
2. 3000 login ch0 (mklogin(0) + PWD), read response → srcid.
3. 3000 login ch1 (mklogin(1) + PWD), read response → srcid.
4. CA ch1 first (payload = ch1 srcid, {srcid,1}) then CA ch0 (payload = ch0 srcid).
5. Read video on the CLEANALARM connections (visible = H.264 Annex-B w/ 00 00 01 b3
   LAUCHDIGITAL markers; IR = RAW 160x120 16-bit thermal frames).
   => tools/test_dynamic_id.py implements this dynamically.

### Addendum 6 (2026-09-06) — REAL VENDOR SESSION DECODED END-TO-END (relay MITM of PCB_Client.exe)
Collapsed the DISCOVERY path: ran the installed `QuanLi\PCB_Client.exe` through a local MITM relay
(`tools/relay3000.py`, 127.0.0.1:3000/3001 -> 192.168.2.32) by editing its
`ConfigureFile/ConfigureFile.xml` Url=192.168.1.200 -> 127.0.0.1 (backup `.relay_bak`).
Logs: tools/relay_3000.log (~4GB, 1h virtual: H.264 + RAW), tools/relay_3001.log (~11KB init).

**PORT 3001 frames** (all one-request-per-connection, same 88-byte header layout as below):
- req=0x65  -> 152B "Neptune" response (init). Sent 2x (extra1@0x4C = 0 then 1).
- req=0x66  -> 116B codec params. extra1=0 -> `H264 01 80 07 38 04 64 19 14 00...`
  (1920 x 1080 @ 0x14=20fps). extra1=1 -> `RAW 09 7b a0 78 14 00 00 00 01 10 40 1f...`
  (160 x 120 @ 20fps). THIS is the authoritative visible/IR negotiation.
- req=0x78 with WORD 0x00010078 @0x1C and psize=16, payload {3, chan, sid, dest-port=3000}:
  `{3, 2, sidVIS, 3000}` and `{3, 4, sidIR, 3000}` -> 88B ack. This is the CONFIG bind:
  channel 2 = visible H.264, channel 4 = IR RAW. (Matches our earlier 0x00010078 attempts;
  payload element [0]=3 is request type, [2]=our old "0x34/0x35" dst values were actually the
  SESSION sids.)
- req=0x6051 -> 96B request (payload[4]=0x58, count=1) -> 184B stats of doubles
  (timestamp@0x64, 0.5/@0x68 area, >12 doubles, final=1.0 = emissivity ratio) = thermometry noise/scale stats.
- req=0x90 -> 88B ack. req=0x65 repeated ~2s later (keepalive-ish re-init).

**PORT 3000 frames** (identically sized header; video rides ON the CLEANALARM conn):
- LOGIN 88B: MAGIC+`video server`+`00 cc*11`+`01 00 7f 00`+`00 01 b8 0b`(port 0x0BB8=3000)+
  channel(0/1)+psize=40+MAGIC2+40B PWD payload
  (`888888\0` + cc*13 + `888888\0` + cc*13 = 40B; EXACT bytes, verified verbatim).
  Response 56B: same header psize=8; payload = `{sid, 0xFFFFFFFF}`. sid = CURRENT source id.
- CLEANALARM 56B: MAGIC+cc+`02 00`+cc+`00 00 00 00`+psize=8+MAGIC2+payload `{sid, 1}` -> 48B ack.
  **The actual video BYTESTREAM then flows on THIS connection as bare chunks.**
- KEEPALIVE 48B: MAGIC+cc+`14 00`+cc+channel+psize=0+MAGIC2 -> 48B ack. Sent every ~10s.

**VENDOR SESSION ORDER (worked live, camera yielded BOTH streams):**
1. 3001 0x65 (extra1=0), 0x65 (extra1=1)         2. 3001 0x66 (extra1=0=VIS), 0x66 (extra1=1=IR)
3. 3000 login ch0 -> sidA (0x37 here)            4. 3001 0x78 {3,2,sidA,3000}  (VIS config)
5. 3000 CA {sidA,1}  -> H.264 starts IMMEDIATELY 6. 3000 login ch1 -> sidB (0x3a)
7. 3000 CA {sidB,1}  -> IR RAW starts            8. 3001 0x78 {3,4,sidB,3000}  (IR config)
9. 3001 0x6051 stats, 0x90, keepalives 0x14 every 10s both ports.
- Session sids are a GLOBAL counter: capture cam saw 0x34/0x35, this unit 0x33/0x34 earlier,
  vendor session 0x37/0x3a. ALWAYS read sid from login response; never hardcode.

**IR RAW STREAM** = per-frame EXACTLY 39448 bytes:
- [0] `00 00 01 b3` + 2B seq + `18 0c 00 00 21 00 00 00` + `00 00 00 00` +
  payload-size `c0 99 00 00`(=0x9? raw 39360) + `20 00` + `LAUNCHDIGITAL\0` + `00 00 01 00 00 00`
  + `RAW\0` + `09 00 7b 00 a0 00 78 00 14 00 00 00 01 00 10 00 40 1f 00 00` + zeros => 80-byte header.
- then 38400 bytes = 19200 x u16 LSB-LE 12-bit samples, reshape (120,160)
  (verified: renders real thermal scene, dead pixels = 0x0000).
- then ~960B tail (padded zeros; ~690B metadata blob, format TBD — candidate for mini edge/overlay data).
- frames fixed 39448B, ~20fps.

**VISIBLE STREAM** = bare Annex-B H.264 ES, 1920x1080 High ~25fps, periodically preceded by a
b3-style header block `00 00 01 b3 <4B> 18 0c 00 00 21 00 00 00 ... 20 00 LAUNCHDIGITAL\0
00 00 01 00 00 00 H264 1e 00 01 00 80 07 38 04 14 00 00 01 00 00 10 00 40 1f 00 00` then
`00 00 00 01 67`(SPS)+`00 00 00 01 68`(PPS). ffmpeg -f h264 decodes to 1920x1080 (verified
on the 3.2MB conn#6 sample; only the cut-point frame errors).

Tools: `tools/parse_relay.py` (bytes-fast hex-log parser), `tools/relay3000.py` (MITM),
relay logs, extracted IR at C:\Users\G\AppData\Local\Temp\opencode\ir_conn9.bin (374MB)
and vis_conn6_first.bin (3.2MB).

### Addendum 7 (2026-09-07) — BOTH STREAMS FROM OUR OWN CLIENT (config extra1 = codec flag)
The remaining blocker was RAW IR: our ch1-sid slot delivered a 640x480 H.264 "compressed IR view"
instead of the 39448B RAW thermal frames, even with correct CA-before-config and session sids.

A second MITM session of PCB_Client.exe (12:19 today) that got RAW revealed the missing bit —
the **0x78 CONFIG request `extra1` field is a codec selector**, not a padding flag:

- `{3, 2, sidVIS, 3000}` req=0x00010078 with **extra1=0** -> VISIBLE H.264 (1920x1080)
- `{3, 4, sidRAW, 3000}` req=0x00010078 with **extra1=1** -> IR RAW (160x120, 39448B frames)
  (NOTE: response echoes req=0x78; our earlier runs always sent extra1=0 -> chan4 was coerced to
   the 640x480 compressed view. extra1=1 on chan4 = RAW, verified live.)

**Correct per-slot open sequence (vendor 12:19 timestamps):**
1. 3001 0x65 (e1=0), 0x65 (e1=1), 0x0066 (e1=0 -> H264 1920), 0x10066 (e1=1 -> RAW 160x120)  [init]
2. 3000 login ch0 -> sidA (0x37, held as control/keepalive conn; no CA)
3. 3001 0x10066 RAW negotiation AGAIN **immediately before** the IR open (16ms gap in vendor)
4. 3000 login ch1 -> sidRAW (0x36); 3000 CA `{sidRAW,1}` with the ch byte@0x24 = **1** -> RAW starts
5. 3001 0x78 {3,4,sidRAW,3000} extra1=1
6. 3000 login ch0 again -> sidVIS (0x3b); 3000 CA `{sidVIS,1}` ch byte = 0 -> H.264 starts
7. 3001 0x78 {3,2,sidVIS,3000} extra1=0; then 0x6051/0x90/keepalives.

**CA channel byte @0x24 = 1 selects the IR engine, 0 = VIS engine** (RAW=1, VIS=0 in vendor CAs);
it is NOT redundant with the config's chan field.

**sid allocation is NOT a global counter** (supersedes Addendum 6). Observed sids per session are
rotating/resource-pool: 0x37/0x3a (11:15), 0x37/0x36/0x3b (12:19), and our own sessions cycle
0x33,0x35,0x37,0x39,0x3b,0x3d,0x3f,0x41,0x43 then 0xFFFFFFFF before channels exhaust.
Always read the sid from the login response; do NOT assume monotonicity.

**tools/pcb_client.py** (rev 5) now captures BOTH streams in ONE session (verified 124831):
- probe loop: login ch0 -> sidA (keepalive), ch1 -> sidB -> chan4/extra1=1 -> sniff; if RAW keep &
  pump; then visa chan2/extra1=0 on the next fresh sid. Each sid gets ONE probe (re-configuring a
  sid's channel wedges the camera — observed silently).
- pre-CA: re-negotiates 0x10066 (IR) / 0x0066 (VIS) immediately before the CA, mirroring the vendor.
- Content-routing: stream is classified by markers (`RAW\0`/`00 00 01 b3` = ir; SPS/H264 = vis;
  markerless 64KB = 640-view -> saved as ir640, never satisfies the 'ir' requirement).
- Result files: `ir1_<stamp>.bin` (196 x 39448B RAW frames, RAW\+LAUNCHDIGITAL headers verified,
  u16 12-bit data min 3323/max 3382 on a uniform scene) and `vis1_<stamp>.bin`
  (H.264 ES, trimmed-from-first-SPS -> ffprobe 1920x1080).

Remaining known-good-but-unexplained: the 640x480 H.264 "compressed IR view" that chan4 delivers
when the sid is the VIS engine (or under extra1=0). It appears absent from the vendor's own GUI
(no docking window), and may be the firmware's DIP/zoom IR preview.

