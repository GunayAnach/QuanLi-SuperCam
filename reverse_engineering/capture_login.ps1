# Elevated pktmon capture - run with Start-Process -Verb RunAs
$captureFile = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\login_capture.etl"

# Clean up any existing capture
pktmon stop 2>$null
pktmon filter remove 2>$null

# Add filter for camera IP
pktmon filter add CameraFilter -p 192.168.2.32
pktmon filter list

# Start capture (500MB max, compaction mode 2)
pktmon start --capture --compaction -m real-time -f $captureFile -s 500000000

Write-Output "PKTMON CAPTURE RUNNING. Waiting 120 seconds..."
Write-Output ">>> RESTART PCB TOOL NOW <<<"

# Wait 120 seconds for user to restart
Start-Sleep -Seconds 120

# Stop capture
pktmon stop
Write-Output "Capture stopped."

# Convert to pcapng for analysis
$pcapFile = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\login_capture.pcapng"
pktmon pcap convert $captureFile -o $pcapFile
Write-Output "Converted to pcapng: $pcapFile"

# Show file info
Get-Item $pcapFile | Select-Object Name, Length, LastWriteTime
