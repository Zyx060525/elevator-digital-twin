@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "CODE=%HERE%..\01_代码"

echo ============================================================
echo   电梯微空间数字孪生 - 测试样例自检
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python 命令，请先安装 Python 3.11 并勾选 Add to PATH。
  pause
  exit /b 1
)

pushd "%CODE%"
python -c "import mesa, flask, matplotlib, pandas, mcp" 2>nul
if errorlevel 1 (
  echo [提示] 依赖未安装完整，请先运行  02_安装包\一键安装_Windows.bat
  popd
  pause
  exit /b 1
)
popd

python "%HERE%run_samples.py" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [结果] 全部样例通过。
) else (
  echo [结果] 存在失败项，请查看上方 [FAIL] 行。
)
pause
exit /b %RC%
