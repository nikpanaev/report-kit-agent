@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0runtime-python.txt" goto system
set /p RK_SUPPORT_PYTHON=<"%~dp0runtime-python.txt"
"%RK_SUPPORT_PYTHON%" -I -B "%~dp0scripts\support_bundle.py" --saved-state --open-folder
goto end
:system
where py >nul 2>nul
if errorlevel 1 goto python
py -3 -I -B "%~dp0scripts\support_bundle.py" --saved-state --open-folder
goto end
:python
where python >nul 2>nul
if errorlevel 1 goto missing
python -I -B "%~dp0scripts\support_bundle.py" --saved-state --open-folder
goto end
:missing
echo Не найден компонент для сбора файла. Сообщите поддержке код SUPPORT_PYTHON_MISSING. Ничего не отправлено.
:end
pause
