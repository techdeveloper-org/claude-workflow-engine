# Create Startup Shortcut for Claude Workflow Engine

$StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = "$StartupFolder\Claude Workflow Engine Server.lnk"
$TargetPath = "$PSScriptRoot\start-claude-workflow-engine.bat"
$WorkingDir = Split-Path $PSScriptRoot

Write-Host ""
Write-Host "Creating startup shortcut..."
Write-Host "Target: $TargetPath"
Write-Host "Location: $ShortcutPath"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $WorkingDir
$Shortcut.WindowStyle = 7  # Minimized
$Shortcut.Description = "Start Claude Workflow Engine Server on Login"
$Shortcut.Save()

Write-Host ""
Write-Host "[OK] Shortcut created successfully!"
Write-Host "[OK] Claude Workflow Engine will start on next login"
Write-Host ""
