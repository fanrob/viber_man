$ErrorActionPreference = "Stop"

$TesseractRoot = "C:\Users\56\AppData\Local\Tesseract-OCR"
$TesseractExe = Join-Path $TesseractRoot "tesseract.exe"

Write-Host "Проверка Tesseract..."
if (-not (Test-Path $TesseractExe)) {
    Write-Warning "Tesseract не найден по пути: $TesseractExe"
    Write-Warning "Убедитесь, что OCR установлен в этой папке или измените путь в скрипте."
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($winget) {
    Write-Host "Установка Python 3.12 через winget..."
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "winget не найден. Скачиваю Python с python.org..."
    $installerUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    $downloadPath = Join-Path $env:TEMP "python312-installer.exe"
    Invoke-WebRequest -Uri $installerUrl -OutFile $downloadPath
    Start-Process -FilePath $downloadPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0" -Wait
}

$pythonExe = $null
$pythonCandidates = @(
    (Get-Command py -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312-32\python.exe"),
    (Join-Path $env:ProgramFiles "Python312\python.exe"),
    (Join-Path $env:ProgramFiles "Python312-32\python.exe")
) | Where-Object { $_ }

foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    throw "Python не найден после установки. Закройте окно и выполните скрипт ещё раз или проверьте PATH."
}

$pythonDir = Split-Path $pythonExe -Parent
$ScriptsDir = Join-Path $pythonDir "Scripts"

Write-Host "Используем Python: $pythonExe"

# Поднимаем PATH для текущей сессии
$env:Path = "$pythonDir;$ScriptsDir;$env:Path"

& $pythonExe -m pip install --upgrade pip setuptools wheel
& $pythonExe -m pip install mss pyautogui pytesseract pillow

Write-Host ""
Write-Host "Установка завершена."
Write-Host "Проверка Tesseract: $TesseractExe"
if (Test-Path $TesseractExe) {
    Write-Host "OK: Tesseract найден."
} else {
    Write-Host "ВНИМАНИЕ: Tesseract не найден по этому пути."
}

Write-Host "Теперь можно запускать скрипт: python .\ocr_screen.py"
