# PowerShell launcher for scripts/demo_up.sh. In PowerShell, `bash` is WSL's Linux bash, which cannot use the
# Windows tools (uv, pnpm, Docker) this project uses — so run the script with Git Bash explicitly.
#   .\scripts\demo_up.ps1            # start / restart everything, keep demo data
#   .\scripts\demo_up.ps1 --reset    # also reset the demo organisations and prepare the photo lookup
$candidates = @(
  "$env:ProgramFiles\Git\bin\bash.exe",
  "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
  "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
)
$gitBash = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $gitBash) { Write-Error "Git Bash not found. Install Git for Windows, or open Git Bash and run: bash scripts/demo_up.sh"; exit 1 }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
  & $gitBash "scripts/demo_up.sh" @args
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
