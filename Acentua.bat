@echo off
REM ===========================================================================
REM  Acentua - abre o app na bandeja do sistema, sem janela de console.
REM
REM  `pythonw.exe` (com W no fim) e a versao do Python que nao abre terminal.
REM  Mensagens sem acento de proposito: ver o comentario no INSTALAR.bat.
REM ===========================================================================
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PYW=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%PYW%" goto :sem_venv

start "" "%PYW%" -m corretor
exit /b 0

:sem_venv
echo.
echo  ------------------------------------------------------------
echo   O Acentua ainda nao foi instalado nesta pasta.
echo  ------------------------------------------------------------
echo.
echo   Clique duas vezes em INSTALAR.bat (esta na mesma pasta que
echo   este arquivo) e espere terminar. Depois volte aqui.
echo.
echo   Faltando: %PYW%
echo.
echo  Aperte qualquer tecla para fechar.
pause >nul
exit /b 1
