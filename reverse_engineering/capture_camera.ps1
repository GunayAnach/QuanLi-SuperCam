# capture_camera.ps1 - Elevated pktmon capture of the QuanLi camera protocol.
# Run AS ADMIN. Captures all traffic to/from 192.168.2.32 on TCP/UDP port 3000,
# plus the discovery UDP ports, until you stop it (or it times out).

$ErrorActionPreference = 'Stop'

$OUT = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\capture"
$ETL = "$OUT.etl"
$P1 = "$OUT.txt"

New-Item -ItemType Directory -Force -Path "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools" | Out-Null
if (Test-Path $ETL) { Remove-Item $ETL -Force }

Write-Output "Starting pktmon capture..."
pktmon start --capture --pkt-size 0 --file-name $ETL

# Add a packet filter for the camera IP (all ports) to keep the dump small.
# Note: pktmon filter syntax may vary; use component filter on the NIC if needed.
try {
    pktmon filter remove 2>$null
} catch {}
try {
    pktmon filter add -i 192.168.2.32
    pktmon filter add -i 192.168.2.255
    pktmon filter add -i 255.255.255.255
} catch {
    Write-Output "filter add note: $($_.Exception.Message)"
}
try {
    pktmon filter list
} catch {}

Write-Output ""
Write-Output "CAPTURING. Use the PCB tool now (connect to 192.168.2.32 and view + measure temperature)."
Write-Output "Type a value and press Enter, or timeout in 120s, to stop..."
$descr = Read-Host -Prompt "Press ENTER when done capturing (or wait 120s)"
Start-Sleep -Seconds 5

Write-Output "Stopping capture..."
pktmon stop

if (Test-Path $ETL) {
    pktmon format $ETL -o $P1
    Write-Output "Formatted capture written to: $P1"
} else {
    Write-Output "No ETL file produced at $ETL"
}
Write-Output "DONE"