# capture_camera2.ps1 - Elevated pktmon capture (longer, for active streaming).
# Run AS ADMIN. Captures for 60 seconds then auto-stops and formats.
$ErrorActionPreference = 'Stop'
$OUT = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\capture2"
$ETL = "$OUT.etl"
$P1 = "$OUT.txt"
if (Test-Path $ETL) { Remove-Item $ETL -Force }

Write-Output "=== START capture for 60 seconds ==="
try { pktmon filter remove 2>$null } catch {}
pktmon start --capture --pkt-size 0 --file-name $ETL
try { pktmon filter add -i 192.168.2.32 } catch {}

Write-Output "=== NOW CONNECT TO THE CAMERA IN THE PCB TOOL, VIEW LIVE, AND MEASURE TEMP ==="
for ($i = 60; $i -ge 1; $i--) {
    Write-Host "Capturing... ${i}s remaining" -NoNewline; Start-Sleep 1; Write-Host "`r" -NoNewline
}
pktmon stop
if (Test-Path $ETL) { pktmon format $ETL -o $P1; Write-Output "Capture: $P1" } else { Write-Output "No ETL" }
Write-Output "DONE"