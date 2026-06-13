$ErrorActionPreference = 'Stop'

$rootDir = Split-Path -Parent $PSScriptRoot
$venvDir = if ($env:MAHANAI_VENV) { $env:MAHANAI_VENV } else { Join-Path $rootDir '.mahanai-venv' }
$pythonVersion = if ($env:MAHANAI_PYTHON_VERSION) { $env:MAHANAI_PYTHON_VERSION } else { '3.12' }

function Write-Banner {
  Write-Host '========================================'
  Write-Host '        MahanAI Get Started'
  Write-Host '========================================'
}

function Write-Step {
  param(
    [string]$Label,
    [string]$Message
  )

  Write-Host ("[{0}] {1}" -f $Label, $Message) -ForegroundColor Cyan
}

Write-Banner
Write-Host ("Bootstrapping a local MahanAI environment in: {0}" -f $venvDir) -ForegroundColor DarkCyan

if (Get-Command uv -ErrorAction SilentlyContinue) {
  Write-Step '1/4' 'uv already installed'
} else {
  Write-Step '1/4' 'Installing uv'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  $localBin = Join-Path $HOME '.local/bin'
  if (Test-Path $localBin) {
    $env:Path = "$localBin;$env:Path"
  }
}

Write-Step '2/4' ("Installing Python {0} through uv" -f $pythonVersion)
& uv python install $pythonVersion

$venvBin = Join-Path $venvDir 'Scripts'
$venvPython = Join-Path $venvBin 'python.exe'
$venvExe = Join-Path $venvBin 'mahanai.exe'
if (Test-Path $venvPython) {
  Write-Step '3/4' 'Reusing the existing virtual environment and installing mahanai'
} else {
  Write-Step '3/4' 'Creating a fresh virtual environment and installing mahanai'
  & uv venv --python $pythonVersion $venvDir
}
& uv pip install --python $venvPython mahanai

Write-Step '4/4' 'Starting MahanAI'
Write-Host 'Ready. Launching MahanAI now.' -ForegroundColor Green
& $venvExe @args
