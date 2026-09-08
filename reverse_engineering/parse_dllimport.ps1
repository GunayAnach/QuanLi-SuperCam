$ErrorActionPreference = 'SilentlyContinue'
$base = "D:\OneDrive\Development\QuanLi Thermal Camera - SuperCam\QuanLi"
$asm = [System.Reflection.Assembly]::LoadFrom((Join-Path $base "PCB_Client.exe"))
Write-Output "=== Assembly: $($asm.FullName) ==="

foreach ($type in $asm.GetTypes()) {
    if ($null -eq $type) { continue }
    $found = @()
    try {
        $methods = $type.GetMethods([System.Reflection.BindingFlags]'Static,Public,NonPublic')
    } catch { continue }
    foreach ($method in $methods) {
        $dllImport = $method.GetCustomAttributes([System.Runtime.InteropServices.DllImportAttribute], $false)
        if ($dllImport.Count -gt 0) {
            $paramTypes = @()
            foreach ($p in $method.GetParameters()) { $paramTypes += $p.ParameterType.FullName + ":" + $p.Name }
            $found += ("M=" + $method.Name + " P=[" + ($paramTypes -join ",") + "] R=" + $method.ReturnType.FullName + " D=" + $dllImport[0].Value)
        }
    }
    if ($found.Count -gt 0) {
        Write-Output ("NS=" + $type.FullName)
        foreach ($fm in $found) { Write-Output ("  " + $fm) }
    }
}
Write-Output "=== DONE ==="
