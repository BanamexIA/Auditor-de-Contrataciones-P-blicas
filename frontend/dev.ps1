# Arranca el servidor de desarrollo usando el Node portátil de .node (no requiere Node instalado).
# Uso:  .\dev.ps1            -> npm run dev
#       .\dev.ps1 build      -> npm run build
#       .\dev.ps1 install    -> npm install
param([string]$Comando = 'dev')

$node = Get-ChildItem "$PSScriptRoot\.node" -Directory -Filter 'node-*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($node) { $env:Path = "$($node.FullName);$env:Path" }

Set-Location $PSScriptRoot
if ($Comando -eq 'install') { npm install } else { npm run $Comando }
