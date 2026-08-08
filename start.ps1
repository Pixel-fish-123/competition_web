# start.ps1 - 一键启动 萌新杯音游比赛网站（后端 + 前端）
#
# 可选参数:
#   -Seed 额外执行幂等演示数据脚本；默认跳过，避免污染已有数据库。
#
# 用法:
#   方式一: 双击根目录的 启动服务.bat
#   方式二: powershell -ExecutionPolicy Bypass -File start.ps1
#
# 首次运行会自动: 创建 Python 虚拟环境 / 安装后端依赖 / 安装前端依赖。
# 需要演示数据时显式传入 -Seed。
# 之后运行直接启动两个服务窗口（后端 :8000 + 前端 :5173），关闭窗口即停止。

param(
    [switch]$Seed
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  萌新杯音游比赛网站 - 一键启动' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan

# ---------- 1. 后端虚拟环境 ----------
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host '[1/4] 首次运行, 创建 Python 虚拟环境...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'backend')
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host '创建虚拟环境失败, 请确认已安装 Python 3.12+' -ForegroundColor Red
        exit 1
    }
    Pop-Location
} else {
    Write-Host '[1/4] Python 虚拟环境已存在, 跳过' -ForegroundColor Green
}

# ---------- 2. 后端依赖 ----------
Write-Host '[2/4] 检查后端依赖...' -ForegroundColor Yellow
& $venvPython -c "import fastapi, uvicorn, sqlalchemy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '      安装后端依赖 (首次约 1-2 分钟)...' -ForegroundColor Yellow
    & $venvPython -m pip install -r (Join-Path $root 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        Write-Host '后端依赖安装失败, 请检查网络后重试' -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host '      后端依赖已就绪' -ForegroundColor Green
}

# ---------- 3. 前端依赖 ----------
Write-Host '[3/4] 检查前端依赖...' -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Write-Host '      安装前端依赖 (首次约 1-2 分钟)...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'frontend')
    npm install
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host '前端依赖安装失败, 请检查网络后重试' -ForegroundColor Red
        exit 1
    }
    Pop-Location
} else {
    Write-Host '      前端依赖已就绪' -ForegroundColor Green
}

# ---------- 4. 可选演示数据 (幂等, 可安全重复运行) ----------
if ($Seed) {
    Write-Host '[4/4] 初始化演示数据...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'backend')
    & $venvPython seed.py
    Pop-Location
} else {
    Write-Host '[4/4] 跳过演示数据初始化（需要时使用 -Seed）' -ForegroundColor Green
}

# ---------- 5. 端口占用检测（issue 2：防止出现两个前端/后端进程） ----------
function Test-PortInUse([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $conn)
}

function Test-BackendHealthy([int]$Port) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        return ($response.status -eq 'ok')
    } catch {
        return $false
    }
}

$backendPort = 8000
$frontendPort = 5173

if (Test-PortInUse $backendPort) {
    if (Test-BackendHealthy $backendPort) {
        Write-Host "[warn] 端口 $backendPort 已被本项目后端占用，跳过后端启动" -ForegroundColor Yellow
        $startBackend = $false
    } else {
        Write-Host "[error] 端口 $backendPort 被其他进程占用，且不是本项目后端。请先释放端口后重试。" -ForegroundColor Red
        exit 1
    }
} else {
    $startBackend = $true
}

if (Test-PortInUse $frontendPort) {
    Write-Host "[warn] 端口 $frontendPort 已被占用，跳过前端启动（可能已有实例在运行）" -ForegroundColor Yellow
    $startFrontend = $false
} else {
    $startFrontend = $true
}

if (-not $startBackend -and -not $startFrontend) {
    Write-Host '两个服务端口均被占用，无需重复启动。' -ForegroundColor Cyan
}

if ($startBackend) {
    Start-Process powershell -WorkingDirectory (Join-Path $root 'backend') `
        -ArgumentList '-NoExit', '-Command', '.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000' `
        -WindowStyle Normal
}

if ($startFrontend) {
    Start-Process powershell -WorkingDirectory (Join-Path $root 'frontend') `
        -ArgumentList '-NoExit', '-Command', 'npm run dev' `
        -WindowStyle Normal
}

Start-Sleep -Seconds 8
Start-Process 'http://localhost:5173'

Write-Host ''
Write-Host '已在浏览器打开 http://localhost:5173, 默认账号 admin / admin123' -ForegroundColor Green
