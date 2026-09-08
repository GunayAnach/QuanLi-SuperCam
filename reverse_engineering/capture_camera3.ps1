# capture_camera3.ps1 - 150s elevated pktmon capture for active streaming session.
$ErrorActionPreference = 'Stop'
$OUT = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\tools\capture3"
$ETL = "$OUT.etl"
$P1 = "$OUT.txt"
if (Test-Path $ETL) { Remove-Item $ETL -Force }

Write-Output "STARTING 150 SECOND CAPTURE"
try { pktmon filter remove 2>$null } catch {}
pktmon start --capture --file-name $ETL
Write-Output "CAPTURING NOW - DO THESE IN THE PCB TOOL:"
Write-Output "  1) connect to 192.168.2.32"
Write-Output "  2) open LIVE VIEW (both IR and visible mode)"
Write-Output "  3) take a TEMPERATURE reading on a hotspot"
Write-Output "  4) capture a JPEG/max temp if possible"
for ($i = 150; $i -ge 1; $i--) {
    Write-Host "  ${i}s left..." -NoNewline; Start-Sleep 1; Write-Host "`r" -NoNewline
}
try { pktmon stop } catch {}
if (Test-Path $ETL) { pktmon format $ETL -o $P1; Write-Output "Saved: $P1" } else { Write-Output "No ETL" }
Write-Output "DONE"