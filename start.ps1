# start.ps1 - 一键启动 萌新杯音游比赛网站（后端 + 前端）
#
# 用法:
#   方式一: 双击根目录的 启动服务.bat
#   方式二: powershell -ExecutionPolicy Bypass -File start.ps1
#
# 首次运行会自动: 创建 Python 虚拟环境 / 安装后端依赖 / 安装前端依赖 / 生成演示数据。
# 之后运行直接启动两个服务窗口（后端 :8000 + 前端 :5173），关闭窗口即停止。

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

# ---------- 4. 演示数据 (幂等, 可安全重复运行) ----------
Write-Host '[4/4] 初始化演示数据...' -ForegroundColor Yellow
Push-Location (Join-Path $root 'backend')
& $venvPython seed.py
Pop-Location

Write-Host ''
Write-Host '启动后端 (http://localhost:8000) 与前端 (http://localhost:5173)...' -ForegroundColor Cyan
Write-Host '将打开两个服务窗口, 关闭窗口即停止对应服务。' -ForegroundColor DarkGray

Start-Process powershell -WorkingDirectory (Join-Path $root 'backend') `
    -ArgumentList '-NoExit', '-Command', '.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000' `
    -WindowStyle Normal

Start-Process powershell -WorkingDirectory (Join-Path $root 'frontend') `
    -ArgumentList '-NoExit', '-Command', 'npm run dev' `
    -WindowStyle Normal

# 等服务起来后自动打开浏览器
Start-Sleep -Seconds 8
Start-Process 'http://localhost:5173'

Write-Host ''
Write-Host '已在浏览器打开 http://localhost:5173, 默认账号 admin / admin123' -ForegroundColor Green
