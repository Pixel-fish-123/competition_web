# 三角占领 · 赛时控制器 - 服务启动器
# 由 启动服务.bat 调用（PowerShell 5.1，UTF-8 安全）
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "三角占领 · 赛时控制器"

# 定位项目根目录（本脚本位于 app/main/ 下）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $scriptDir
$root = Split-Path -Parent $appRoot

Set-Location $root

Write-Host ""
Write-Host "============================================"
Write-Host "  三角占领 · 赛时控制器"
Write-Host "  正在启动服务，请稍候..."
Write-Host "============================================"
Write-Host ""

# 检查 python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查依赖
Write-Host "[检查] 依赖 (fastapi/uvicorn)..."
python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[提示] 首次运行，正在安装依赖..." -ForegroundColor Yellow
    python -m pip install -r app\main\requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] 依赖安装失败，请检查网络" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
}

# 端口候选，与 main/main.py 的 select_port 保持一致（8000 预留给比赛网站）
$ports = @(8001, 8002, 8003)
$finalPort = $null

# 检查是否已有本服务在运行（可能已有实例）
foreach ($port in $ports) {
    try {
        $probe = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/state" -TimeoutSec 1 -UseBasicParsing
        if ($probe.StatusCode -eq 200 -and $probe.Content -match '"board"') {
            $finalPort = $port
            Write-Host "[提示] 检测到 $port 端口已有服务在运行，直接打开浏览器" -ForegroundColor Yellow
            break
        }
    } catch {
        # 未运行，继续检查下一个端口
    }
}

# 若没有已有实例，则启动服务
if (-not $finalPort) {
    Write-Host "[启动] 正在后台启动 FastAPI 服务..."
    $proc = Start-Process -FilePath "python" -ArgumentList "app/main/main.py" -WorkingDirectory $root -WindowStyle Hidden -PassThru

    # 等待端口就绪（最多 20 秒）
    $ready = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Milliseconds 1000
        foreach ($port in $ports) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/state" -TimeoutSec 1 -UseBasicParsing
                if ($r.StatusCode -eq 200 -and $r.Content -match '"board"') {
                    $ready = $true
                    $finalPort = $port
                    break
                }
            } catch {
                # 未就绪，继续等
            }
        }
        if ($ready) { break }
    }

    if (-not $ready) {
        Write-Host "[警告] 服务启动超时，请检查 app/main/main.py 是否报错（可手动运行 python app\main\main.py 查看）" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
}

Write-Host "[完成] 服务已启动：http://127.0.0.1:$finalPort" -ForegroundColor Green
Write-Host "[打开] 正在打开浏览器..."
Start-Process "http://127.0.0.1:$finalPort"

Write-Host ""
Write-Host "--------------------------------------------------"
Write-Host "  使用说明："
Write-Host "  - 服务在后台运行，关闭本窗口不会停止服务"
Write-Host "  - 停止服务：在本窗口按 [Q] 或任务管理器结束 python"
Write-Host "--------------------------------------------------"
Write-Host ""

# 等待用户按 Q 退出（同时保持窗口，方便查看状态）
while ($true) {
    $key = Read-Host "输入 Q 停止服务并退出（直接回车保持运行）"
    if ($key -match '^[qQ]$') {
        # 仅当是本脚本启动的服务才停止；若是已有服务则不动
        if ($proc) {
            Write-Host "[停止] 正在停止服务..."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "[完成] 服务已停止" -ForegroundColor Green
        } else {
            Write-Host "[提示] 该服务不是本脚本启动的，未停止。如需停止请在任务管理器结束 python 进程。"
        }
        break
    }
    Write-Host "（保持运行中... 输入 Q 停止）"
}
