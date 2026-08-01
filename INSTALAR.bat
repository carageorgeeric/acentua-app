@echo off
REM ===========================================================================
REM  Acentua - instalador de 1 clique.
REM
REM  As mensagens deste arquivo sao propositalmente SEM ACENTO. O console do
REM  Windows muda de pagina de codigo dependendo da maquina, e texto acentuado
REM  aqui vira sujeira na tela em alguns PCs. Funcionar vale mais que enfeite.
REM ===========================================================================
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Instalando o Acentua
cd /d "%~dp0"

echo.
echo  ============================================================
echo    ACENTUA - instalacao
echo    Digite sem acento. Aperte Ctrl+Alt+C. Pronto.
echo  ============================================================
echo.
echo  Leva de 1 a 3 minutos. Pode deixar rodando.
echo.

REM ------------------------------------------------------------ 1/6  Python
echo  [1/6] Procurando o Python...
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto :achou_python
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto :achou_python
)
goto :sem_python

:achou_python
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do set "VERSAO_PY=%%v"
echo        OK - %VERSAO_PY%
echo.

REM ------------------------------------------------------- 2/6  versao 3.11+
echo  [2/6] Conferindo se a versao serve (precisa ser 3.11 ou mais nova)...
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :versao_velha
echo        OK
echo.

REM ---------------------------------------------------------- 3/6  ambiente
echo  [3/6] Preparando o ambiente isolado (pasta .venv)...
if exist ".venv\Scripts\python.exe" goto :venv_pronto
%PY% -m venv .venv
if errorlevel 1 goto :erro_venv
echo        OK - ambiente criado
goto :depois_do_venv

:venv_pronto
echo        OK - ambiente ja existia, reaproveitando

:depois_do_venv
set "VENVPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENVPY%" goto :erro_venv
echo.

REM --------------------------------------------------------- 4/6  instalar
echo  [4/6] Instalando o Acentua e o que ele precisa...
echo        (esta e a parte demorada; precisa de internet na primeira vez)
"%VENVPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check >nul 2>&1
"%VENVPY%" -m pip install -e . --disable-pip-version-check
if errorlevel 1 goto :erro_pip
echo        OK
echo.

REM ----------------------------------------------------- 5/6  dados do app
echo  [5/6] Conferindo o dicionario e os icones...
if exist "src\corretor\dados\dicionario.json.gz" goto :dicionario_ok
echo        Dicionario ausente. Gerando agora (pode levar 1 minuto)...
"%VENVPY%" -m pip install pyspellchecker --quiet --disable-pip-version-check
"%VENVPY%" scripts\gerar_dicionario.py
if errorlevel 1 goto :erro_dicionario

:dicionario_ok
if exist "src\corretor\dados\icone.ico" goto :icone_ok
echo        Icones ausentes. Gerando agora...
"%VENVPY%" scripts\gerar_icone.py
if errorlevel 1 echo        Aviso: nao consegui gerar os icones. O app funciona assim mesmo.

:icone_ok
echo        OK
echo.

REM ----------------------------------------------------------- 6/6  atalho
echo  [6/6] Criando o atalho na area de trabalho...
"%VENVPY%" scripts\criar_atalho.py
if errorlevel 1 goto :erro_atalho
echo.

REM ------------------------------------------------------------- terminou
echo  ============================================================
echo    PRONTO! O Acentua esta instalado.
echo  ============================================================
echo.
echo   Para usar:
echo.
echo     1. Abra o atalho "Acentua" na sua area de trabalho.
echo        Nao vai abrir janela nenhuma: ele mora na bandeja do
echo        sistema, ao lado do relogio. Se nao aparecer, clique na
echo        setinha para cima, perto do relogio, para ver os icones
echo        escondidos.
echo.
echo     2. Em qualquer programa, digite sem acento e selecione o texto.
echo.
echo     3. Aperte Ctrl+Alt+C. O texto volta acentuado.
echo.
echo   Outros atalhos:
echo     Ctrl+Alt+S  ver sugestoes antes de trocar
echo     Ctrl+Z      desfaz, como em qualquer programa
echo.
echo   Quer que ele abra sozinho junto com o Windows? Rode:
echo     .venv\Scripts\python.exe scripts\criar_atalho.py --iniciar-com-windows
echo.
goto :fim

REM ===========================================================================
REM  Erros - cada um diz O QUE FAZER, nao so o que quebrou.
REM ===========================================================================

:sem_python
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   O Python nao esta instalado (ou nao esta no PATH).
echo  ------------------------------------------------------------
echo.
echo   Como resolver, em 3 passos:
echo.
echo     1. Abra:  https://www.python.org/downloads/
echo     2. Baixe e rode o instalador.
echo     3. IMPORTANTE: na primeira tela, MARQUE a caixinha
echo        "Add python.exe to PATH" antes de clicar em Install.
echo        Sem essa caixinha marcada, este instalador nao acha o Python.
echo.
echo   Depois disso, feche esta janela e rode o INSTALAR.bat de novo.
echo.
goto :fim

:versao_velha
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   Seu Python e antigo demais: %VERSAO_PY%
echo   O Acentua precisa do Python 3.11 ou mais novo.
echo  ------------------------------------------------------------
echo.
echo   Baixe uma versao atual em:
echo     https://www.python.org/downloads/
echo   Marque "Add python.exe to PATH" durante a instalacao.
echo.
echo   Depois, rode o INSTALAR.bat de novo.
echo.
goto :fim

:erro_venv
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   Nao consegui criar a pasta .venv aqui.
echo  ------------------------------------------------------------
echo.
echo   Causas comuns, na ordem:
echo     1. A pasta do projeto esta no OneDrive e ele travou os arquivos.
echo        Mova o projeto para uma pasta simples, ex: C:\Acentua
echo     2. O antivirus bloqueou. Libere a pasta e tente de novo.
echo     3. Falta espaco em disco.
echo.
echo   Para ver a mensagem de erro completa, abra o Prompt de Comando
echo   nesta pasta e rode:  py -3 -m venv .venv
echo.
goto :fim

:erro_pip
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   Nao consegui baixar/instalar as dependencias.
echo  ------------------------------------------------------------
echo.
echo   Causas comuns, na ordem:
echo     1. Sem internet. Conecte e rode o INSTALAR.bat de novo.
echo     2. Antivirus ou firewall bloqueando o pip.
echo     3. Proxy da empresa. Nesse caso rode manualmente:
echo        .venv\Scripts\python.exe -m pip install -e . --proxy SEU_PROXY
echo.
echo   Para ver o erro completo, abra o Prompt de Comando nesta pasta e rode:
echo     .venv\Scripts\python.exe -m pip install -e .
echo.
goto :fim

:erro_dicionario
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   Nao consegui gerar o dicionario de palavras.
echo  ------------------------------------------------------------
echo.
echo   O jeito mais facil de resolver: baixe o projeto de novo pelo
echo   GitHub. O dicionario ja vem pronto junto com o codigo.
echo.
echo   Para tentar gerar manualmente, rode nesta pasta:
echo     .venv\Scripts\python.exe scripts\gerar_dicionario.py
echo.
goto :fim

:erro_atalho
echo        FALHOU
echo.
echo  ------------------------------------------------------------
echo   O Acentua foi instalado, mas nao consegui criar o atalho.
echo  ------------------------------------------------------------
echo.
echo   Nao tem problema: da para usar assim mesmo. Clique duas vezes
echo   no arquivo "Acentua.bat" que esta nesta mesma pasta.
echo.
echo   Se quiser tentar o atalho de novo:
echo     .venv\Scripts\python.exe scripts\criar_atalho.py
echo.
goto :fim

:fim
echo.
echo  Aperte qualquer tecla para fechar esta janela.
pause >nul
endlocal
