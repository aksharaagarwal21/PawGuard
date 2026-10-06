# PowerShell launcher for scripts/public_link.sh (runs it with Git Bash, not WSL).
#   .\scripts\public_link.ps1          # start a temporary public HTTPS link to the running demo
#   .\scripts\public_link.ps1 --stop   # stop it
$gitBash = @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe") |
  Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $gitBash) { Write-Error "Git Bash not found. Install Git for Windows."; exit 1 }
Push-Location (Split-Path $PSScriptRoot -Parent)
try { & $gitBash "scripts/public_link.sh" @args; exit $LASTEXITCODE } finally { Pop-Location }
