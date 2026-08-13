# 三角占领 · 玩法测试运行器
# 由 运行测试.bat 调用（PowerShell 5.1，UTF-8 安全）
$ErrorActionPreference = "Stop"
try { $Host.UI.RawUI.WindowTitle = "三角占领 · 玩法测试" } catch { }

# 定位项目根目录（本脚本位于 app/main/ 下）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $scriptDir
$root = Split-Path -Parent $appRoot
Set-Location $root

Write-Host ""
Write-Host "============================================"
Write-Host "  三角占领 · 玩法测试（pytest）"
Write-Host "============================================"
Write-Host ""

# 检查 python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查 pytest（仅开发依赖），缺失则按 requirements-dev.txt 安装
python -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[提示] 未安装 pytest，正在安装开发依赖（requirements-dev.txt）..." -ForegroundColor Yellow
    python -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] 依赖安装失败，请检查网络" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
}

Write-Host ""
Write-Host "[运行] python -m pytest tests -q"
Write-Host ""
python -m pytest tests -q
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "[完成] 全部玩法测试通过" -ForegroundColor Green
} else {
    Write-Host "[失败] 玩法测试未通过（exit code: $code），请检查上方输出" -ForegroundColor Red
}
Read-Host "按回车退出"
exit $code
