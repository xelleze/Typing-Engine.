$ErrorActionPreference = 'Stop'
$typingProject = $PSScriptRoot
$typingPython = Join-Path $typingProject '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $typingPython)) {
    throw 'Virtual environment missing. See README.md for installation instructions.'
}
Start-Process -FilePath $typingPython -ArgumentList '-m', 'app.main' -WorkingDirectory $typingProject -WindowStyle Hidden
