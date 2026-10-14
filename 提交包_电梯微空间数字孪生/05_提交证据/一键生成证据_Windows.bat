@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  生成提交证据图（真实运行输出 -^> PNG 截图 + UTF-8 日志）
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.9+ 并勾选 Add to PATH
  pause
  exit /b 1
)
python 生成证据图.py %*
echo.
echo 产物在「证据图」目录，可直接上传赛事平台。
pause
