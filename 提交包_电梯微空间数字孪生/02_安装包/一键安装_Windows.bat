@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "WHEELS=%HERE%wheels_windows_py311"
set "CODE=%HERE%..\01_代码"

echo ============================================================
echo   电梯微空间数字孪生 - 离线依赖安装（Windows / Python 3.11）
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python 命令。
  echo        请先安装 Python 3.11，安装时勾选 "Add python.exe to PATH"。
  pause
  exit /b 1
)
python --version
echo 离线包目录：%WHEELS%
echo.

echo [1/3] 从离线 wheel 安装依赖（--no-index，全程不联网）...
python -m pip install --no-index --find-links "%WHEELS%" -r "%HERE%requirements-lock-windows.txt"
if errorlevel 1 (
  echo.
  echo [错误] 依赖安装失败。若 Python 不是 3.11，请改用联网安装：
  echo        python -m pip install -r "%CODE%\requirements.txt"
  pause
  exit /b 1
)

echo.
echo [2/3] 校验依赖导入...
pushd "%CODE%"
python -c "import mesa, numpy, pandas, matplotlib, flask, requests, mcp; print('[OK] 依赖校验通过：mesa', mesa.__version__)"
if errorlevel 1 (
  echo [错误] 依赖校验失败，请查看上方报错。
  popd
  pause
  exit /b 1
)
popd

echo.
echo [3/3] 安装完成。
echo       下一步：双击  04_测试样例\一键自检_Windows.bat
echo       启动网页：cd 01_代码 ^&^& python webapp.py  ^(浏览器打开 http://127.0.0.1:5000^)
pause
endlocal
