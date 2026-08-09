# 三角占领 · 测试歌曲生成器
# 由 抽取歌曲.bat 调用（PowerShell 5.1，UTF-8 安全）
$Host.UI.RawUI.WindowTitle = "三角占领 · 生成测试歌曲库"

# 定位项目根目录（本脚本位于 app/main/ 下）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $scriptDir
$root = Split-Path -Parent $appRoot
Set-Location $root

Write-Host ""
Write-Host "============================================"
Write-Host "  三角占领 · 测试歌曲生成器"
Write-Host "============================================"
Write-Host ""
Write-Host "  选项："
Write-Host "  [1] 生成 50 首（默认，覆盖全部难度档）"
Write-Host "  [2] 生成 100 首"
Write-Host "  [3] 自定义数量"
Write-Host "  [0] 退出"
Write-Host ""

$choice = Read-Host "请输入选项 [1/2/3/0]"
$count = $null

switch ($choice) {
    "1" { $count = 50 }
    "2" { $count = 100 }
    "3" {
        $input = Read-Host "请输入歌曲数量（至少 23）"
        if ($input -match '^\d+$') { $count = [int]$input } else {
            Write-Host "[错误] 数量无效" -ForegroundColor Red
            Read-Host "按回车退出"
            exit 1
        }
    }
    "0" { exit 0 }
    default {
        Write-Host "[错误] 无效选项" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
}

# 数量下限校验
if ($count -lt 23) {
    Write-Host "[错误] 歌曲数量不能少于 23（开局流水线需要抽取 23 首不重复）" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查 python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
Write-Host "正在生成 ${count} 首测试歌曲..."
python app\tools\gen_test_songs.py --count $count --output test_songs.json
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[错误] 生成失败，请检查 Python 环境" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
Write-Host "[完成] 已生成 ${count} 首测试歌曲 -> test_songs.json" -ForegroundColor Green
Write-Host ""
Write-Host "下一步：双击「启动服务.bat」，然后在页面点「导入歌曲库」粘贴本文件内容"
Write-Host ""
Read-Host "按回车退出"
