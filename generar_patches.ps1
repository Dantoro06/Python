# generar_patches.ps1
# =========================================================
# Genera patches UTF-8 para compartir cambios (VS Code + Codex)
#
# Salidas (se guardan en la carpeta "Patch" del repo):
#  - cambios_core.patch              (core: unstaged + staged)
#  - cambios_gui.patch               (solo GUI: unstaged + staged)
#  - cambios_core_nuevos.patch       (untracked detectados automáticamente)
#  - cambios_total.patch             (todo repo: unstaged + staged)
#  - cambios_branch_vs_main.patch    (TODO lo que cambió en tu rama vs origin/main, incluye commits)
#  - cambios_resumen.txt             (status + stats)
# =========================================================

# 0) Validación: estar en un repo git
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] No estás dentro de un repositorio git." -ForegroundColor Red
  exit 1
}

$fecha  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$branch = (git branch --show-current 2>$null)
$head   = (git rev-parse --short HEAD 2>$null)

# 1) Repo root = carpeta donde está este script
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# 2) Carpeta destino de patches
$PatchDir = Join-Path $RepoRoot "Patch"
New-Item -ItemType Directory -Force -Path $PatchDir | Out-Null

function OutPath([string]$name) {
  return (Join-Path $PatchDir $name)
}

# 3) Archivos core (ajusta lista si lo deseas)
$coreFiles = @(
  "src/gui/app_hidding_bonus_tk.py",
  "src/motor/motor_aml_pipeline.py",
  "src/motor/motor_aml_pipeline_v0.py",
  "src/motor/motor_multi_cuenta.py",
  "src/motor/motor_hidding_bonus.py",
  "src/motor/motor_bonus_abuse.py",
  "src/motor/aml_utils_io.py",
  "src/utils/paths_dashboard.py",
  "src/utils/dashboard_riesgo.py",
  "dashboard_pro/dashboard.py",
  "dashboard_pro/pages/1_Historico.py",
  "dashboard_pro/pages/2_Ultima_Ejecucion.py",
  "dashboard_pro/pages/3_Abuso_Bonus.py",
  "dashboard_pro/pages/4_Usuarios.py",
  "dashboard_pro/pages/5_Eventos.py",
  "dashboard_pro/pages/6_Segmentacion.py"
)

# Filtrar solo existentes (por si algún archivo fue borrado)
$coreFiles = $coreFiles | Where-Object { Test-Path (Join-Path $RepoRoot $_) }

function Write-Diff([string]$outFile, [string[]]$paths) {
  "" | Out-File -Encoding utf8 $outFile
  if ($paths.Count -gt 0) {
    # Unstaged
    git diff --no-color -- $paths | Out-File -Encoding utf8 -Append $outFile
    # Staged
    git diff --no-color --cached -- $paths | Out-File -Encoding utf8 -Append $outFile
  }
}

# Moverse al repo root para que git diff use paths relativos correctos
Push-Location $RepoRoot

# 4) Patch core (unstaged + staged)
Write-Diff -outFile (OutPath "cambios_core.patch") -paths $coreFiles

# 5) Patch GUI (unstaged + staged)
if (Test-Path "src/gui/app_hidding_bonus_tk.py") {
  Write-Diff -outFile (OutPath "cambios_gui.patch") -paths @("src/gui/app_hidding_bonus_tk.py")
} else {
  "" | Out-File -Encoding utf8 (OutPath "cambios_gui.patch")
}

# 6) Patch de nuevos (auto-detecta untracked y los incluye sin commitear)
# Respeta .gitignore (exclude-standard)
$untracked = @(git ls-files --others --exclude-standard) | Where-Object { $_ -and $_.Trim() -ne "" }
if ($untracked.Count -gt 0) {
  git add -N -- $untracked *> $null
  Write-Diff -outFile (OutPath "cambios_core_nuevos.patch") -paths $untracked
  git reset -q -- $untracked *> $null
} else {
  "" | Out-File -Encoding utf8 (OutPath "cambios_core_nuevos.patch")
}

# 7) Patch total (todo repo: unstaged + staged)
"" | Out-File -Encoding utf8 (OutPath "cambios_total.patch")
git diff --no-color | Out-File -Encoding utf8 -Append (OutPath "cambios_total.patch")
git diff --no-color --cached | Out-File -Encoding utf8 -Append (OutPath "cambios_total.patch")

# 8) Patch rama vs main (incluye commits ya hechos)
$haveOrigin = $false
git remote get-url origin *> $null
if ($LASTEXITCODE -eq 0) { $haveOrigin = $true }

if ($haveOrigin) {
  git fetch origin *> $null
  "" | Out-File -Encoding utf8 (OutPath "cambios_branch_vs_main.patch")
  git diff --no-color origin/main...HEAD | Out-File -Encoding utf8 -Append (OutPath "cambios_branch_vs_main.patch")
} else {
  "" | Out-File -Encoding utf8 (OutPath "cambios_branch_vs_main.patch")
}

# 9) Resumen (status + stats)
"Fecha: $fecha" | Out-File -Encoding utf8 (OutPath "cambios_resumen.txt")
"Branch: $branch" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"HEAD: $head" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"== git status ==" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
git status | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"== git diff --stat (unstaged) ==" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
git diff --stat | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
"== git diff --stat (staged) ==" | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")
git diff --cached --stat | Out-File -Encoding utf8 -Append (OutPath "cambios_resumen.txt")

Pop-Location

# 10) Limpieza: mover cualquier patch viejo en la raíz del repo hacia Patch/
# (por si antes se generaban en la raíz)
Get-ChildItem -Path $RepoRoot -Filter "*.patch" -File -ErrorAction SilentlyContinue | ForEach-Object {
  Move-Item -Force $_.FullName -Destination $PatchDir
}
Get-ChildItem -Path $RepoRoot -Filter "cambios_resumen.txt" -File -ErrorAction SilentlyContinue | ForEach-Object {
  Move-Item -Force $_.FullName -Destination $PatchDir
}

# 11) Output
Write-Host "[OK] Patches generados en:" -ForegroundColor Green
Write-Host "  $PatchDir" -ForegroundColor Gray
Get-Item (OutPath "cambios_core.patch"), (OutPath "cambios_gui.patch"), (OutPath "cambios_core_nuevos.patch"), (OutPath "cambios_total.patch"), (OutPath "cambios_branch_vs_main.patch"), (OutPath "cambios_resumen.txt") | ForEach-Object {
  Write-Host (" - {0} ({1} KB)" -f $_.Name, [math]::Round($_.Length/1KB, 1))
}
