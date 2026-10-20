$ProjectDir = $PSScriptRoot

# Add to User PATH if not already there
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$ProjectDir*") {
    $NewPath = "$UserPath;$ProjectDir"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Host "Project directory added to User PATH." -ForegroundColor Green
} else {
    Write-Host "Project directory already in User PATH." -ForegroundColor Cyan
}

# Create a PowerShell alias for the current session
New-Alias -Name albumpaper -Value (Join-Path $ProjectDir "AlbumPaper.bat") -Force

Write-Host "`nGlobal command 'AlbumPaper' (or 'albumpaper') is now set up!" -ForegroundColor Green
Write-Host "You may need to restart your terminal for the PATH changes to take full effect." -ForegroundColor Yellow
Write-Host "Try typing: albumpaper"
