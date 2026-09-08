"""Parse the captured login packets in detail."""
import struct, sys, os

M1 = 0x123AB678
M2 = 0x876CD321

# Read the stdout log to get raw packet data
# Actually, the sniffer only printed summaries. Let me write a better parser.
# For now, let me reconstruct from what we know.

# The sniffer logged packet summaries. Let me parse the raw data from the real capture.
# We need to re-capture with full hex dump. But first, let me analyze what we know.

print("=" * 70)
print("LOGIN SEQUENCE ANALYSIS")
print("=" * 70)

print("""
PORT 3001 (Command Channel - uses 88-byte frames):
===================================================
The DLL connects to port 3001 FIRST with 88-byte frames.
cmd_word = 0x38383838 = ASCII "8888" repeated

C2S 88B frames:  cmd_word = 0x38383838 ("8888" in ASCII)
S2C 6B frames:   zeros (ACK)
S2C 152B/116B/88B: response frames with cmd_word = 0x38383838

After initial handshake, sends config commands:
  C2S 16B: 03000000 02000000 36000000 b80b0000
           uint32: cmd=3, channel=2, ???=54, port=3000 (0xBB8)
  C2S 16B: 03000000 04000000 35000000 b80b0000
           uint32: cmd=3, channel=4, ???=53, port=3000 (0xBB8)

PORT 3000 (Video Channel - uses 48-byte frames):
=================================================
C2S 48B: SERVERCHS (cmd_word=0xA8C00001)
  cmd_byte = 0x01 (SERVERCHS)
  Upper bytes contain PC IP: 0xA8C0 = 192.168 (reversed C0.A8)

C2S 40B: RAW PASSWORD: 38 38 38 38 38 38 00 CC CC CC CC CC CC CC CC CC CC
  "888888\\0" + 0xCC padding (same pattern as DLL debug fill!)
  
S2C 6B: zeros (ACK)
S2C 56B: cmd_word=0x00000001 (server accepted)

Then on port 3000:
  C2S 48B: CLEANALARM (cmd_word=0xCCCC0002, cmd=2)
  C2S 8B:  35000000 01000000 (payload for CLEANALARM)
  S2C 48B: response cmd=0x00000002

  C2S 48B: SERVERCHS on new connection (cmd_word=0xA8C00001)
  C2S 40B: "888888\\0" + padding
  S2C 48B: cmd=0x00000001

  C2S 48B: CLEANALARM (cmd_word=0xCCCC0002)  
  C2S 8B:  36000000 01000000 (payload)
  S2C 48B: cmd=0x00000002

  C2S 48B: GETSERIALNO (cmd_word=0xCCCC0014, cmd=20)
  S2C 48B: response cmd=0x00000014 (with payload data)

Then H.264 video starts flowing on port 3000 at t=0.233s

KEY INSIGHTS:
1. Password "888888" is sent as RAW 40 bytes, NOT in a 48-byte frame
2. Each video channel gets its own TCP connection
3. The cmd_word byte layout: [cmd_code] [0x00] [IP_hi] [IP_lo]
   - For SERVERCHS: IP bytes are the CLIENT IP (192.168.x.x)
   - For other cmds: upper bytes are 0xCCCC (debug fill)
4. The SERVERCHS response (56B) is larger than usual (48B) = has 8B payload
""")

print("=" * 70)
print("EXACT LOGIN REPLICATION PLAN:")
print("=" * 70)

print("""
Step 1: Connect to PORT 3001 (command channel)
Step 2: Send 88-byte frame with cmd_word=0x38383838
Step 3: Receive 6B zeros (ACK) + 88B/152B response
Step 4: Send config commands on port 3001
Step 5: Connect to PORT 3000 (video channel)  
Step 6: Send 48-byte SERVERCHS frame with cmd_word encoding client IP
Step 7: Send 40 bytes raw: "888888\\0" + CC padding
Step 8: Receive 56-byte response (authentication success)
Step 9: Send subsequent commands (CLEANALARM, GETSERIALNO, etc.)
Step 10: Receive H.264 video stream
""")
