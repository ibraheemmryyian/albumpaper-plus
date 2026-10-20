$WshShell = New-Object -ComObject WScript.Shell
$Startup = $WshShell.SpecialFolders("Startup")
$ShortcutPath = Join-Path $Startup "AlbumPaper-Plus.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $PSScriptRoot "AlbumPaper-Plus.bat"
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.Save()
Write-Host "Shortcut created at: $ShortcutPath"
Write-Host "AlbumPaper-Plus will now start automatically with Windows!"
