@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_python_and_libs.ps1"
if errorlevel 1 (
    echo.
    echo Ошибка установки. Проверьте вывод выше.
    pause
    exit /b %errorlevel%
)
endlocal
