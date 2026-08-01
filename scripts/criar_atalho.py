"""Cria o atalho do Acentua na area de trabalho (e, opcionalmente, na inicializacao).

Nao depende de pywin32. Usa o `WScript.Shell` via PowerShell, que existe em
qualquer Windows desde o XP.

Uso:
    python scripts/criar_atalho.py                        # area de trabalho
    python scripts/criar_atalho.py --iniciar-com-windows  # + iniciar junto com o Windows
    python scripts/criar_atalho.py --remover              # desfaz tudo

Rodar duas vezes nao duplica nada: o atalho e sempre sobrescrito no mesmo lugar.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NOME_ATALHO = "Acentua.lnk"
DESCRICAO_ATALHO = "Acentua - corrige a acentuacao do texto selecionado (Ctrl+Alt+C)"

OK = "[ok]  "
ERRO = "[erro]"
AVISO = "[!]   "


# ---------------------------------------------------------------------------
# Descoberta de caminhos
# ---------------------------------------------------------------------------


def _pasta_do_registro(nome: str) -> Path | None:
    """Le uma pasta especial do registro do usuario.

    Precisa ser o registro e nao `%USERPROFILE%\\Desktop` porque o OneDrive
    redireciona a area de trabalho para dentro da pasta sincronizada.
    """
    try:
        import winreg
    except ImportError:  # nao e Windows
        return None

    chave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
            valor, _ = winreg.QueryValueEx(k, nome)
    except OSError:
        return None

    caminho = Path(os.path.expandvars(str(valor)))
    return caminho if caminho.is_dir() else None


def area_de_trabalho() -> Path:
    """Pasta da area de trabalho, respeitando redirecionamento do OneDrive."""
    return _pasta_do_registro("Desktop") or Path.home() / "Desktop"


def pasta_inicializacao() -> Path:
    """Pasta `shell:startup` (o que esta aqui abre junto com o Windows)."""
    do_registro = _pasta_do_registro("Startup")
    if do_registro:
        return do_registro
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData/Roaming"
    return base / "Microsoft/Windows/Start Menu/Programs/Startup"


def executavel_sem_console() -> Path | None:
    """`pythonw.exe` do venv do projeto (ou do Python que esta rodando isto).

    Apontar o atalho direto para o `pythonw.exe` evita a janela preta que
    pisca quando o alvo e um `.bat`.
    """
    do_venv = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
    if do_venv.is_file():
        return do_venv

    atual = Path(sys.executable)
    irmao = atual.with_name("pythonw.exe")
    if irmao.is_file():
        return irmao
    return None


def icone() -> Path | None:
    """Icone do app, se o `scripts/gerar_icone.py` ja tiver rodado."""
    caminho = RAIZ / "src" / "corretor" / "dados" / "icone.ico"
    return caminho if caminho.is_file() else None


# ---------------------------------------------------------------------------
# PowerShell
# ---------------------------------------------------------------------------


def _powershell() -> str | None:
    achado = shutil.which("powershell") or shutil.which("pwsh")
    if achado:
        return achado
    # PATH quebrado: tenta o caminho fixo do sistema.
    raiz_win = os.environ.get("SystemRoot", r"C:\Windows")
    fixo = Path(raiz_win) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return str(fixo) if fixo.is_file() else None


def _ps_texto(valor: str) -> str:
    """Escapa uma string para virar literal entre aspas simples no PowerShell."""
    return "'" + valor.replace("'", "''") + "'"


def _rodar_powershell(script: str) -> tuple[bool, str]:
    """Roda um script PowerShell a partir de um arquivo temporario UTF-8 com BOM.

    O BOM importa: sem ele o PowerShell 5.1 le o arquivo como ANSI e caminhos
    com acento (`C:\\Users\\Usuario`) chegam corrompidos.
    """
    ps = _powershell()
    if not ps:
        return False, "PowerShell nao encontrado neste Windows."

    arquivo = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".ps1", delete=False, encoding="utf-8-sig"
        ) as f:
            f.write(script)
            arquivo = f.name
        proc = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", arquivo],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        return False, f"nao foi possivel chamar o PowerShell: {e}"
    finally:
        if arquivo:
            try:
                os.unlink(arquivo)
            except OSError:
                pass

    if proc.returncode != 0:
        detalhe = (proc.stderr or proc.stdout or "").strip()
        return False, detalhe or f"PowerShell terminou com codigo {proc.returncode}"
    return True, (proc.stdout or "").strip()


# ---------------------------------------------------------------------------
# Acoes
# ---------------------------------------------------------------------------


def criar_atalho(destino: Path, alvo: Path, icone_ico: Path | None) -> tuple[bool, str]:
    """Cria (ou sobrescreve) um `.lnk` apontando para `pythonw.exe -m corretor`."""
    destino.parent.mkdir(parents=True, exist_ok=True)

    linhas = [
        "$ErrorActionPreference = 'Stop'",
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_texto(str(destino))})",
        f"$s.TargetPath = {_ps_texto(str(alvo))}",
        "$s.Arguments = '-m corretor'",
        f"$s.WorkingDirectory = {_ps_texto(str(RAIZ))}",
        f"$s.Description = {_ps_texto(DESCRICAO_ATALHO)}",
        "$s.WindowStyle = 7",  # minimizado: o app vive na bandeja
    ]
    if icone_ico is not None:
        linhas.append(f"$s.IconLocation = {_ps_texto(str(icone_ico) + ',0')}")
    linhas.append("$s.Save()")

    ok, saida = _rodar_powershell("\n".join(linhas) + "\n")
    if not ok:
        return False, saida
    if not destino.is_file():
        return False, "o PowerShell nao reclamou, mas o arquivo .lnk nao apareceu."
    return True, ""


def remover_atalho(destino: Path) -> bool:
    try:
        destino.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        print(f"{ERRO} nao consegui apagar {destino}: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="criar_atalho.py",
        description="Cria o atalho do Acentua na area de trabalho.",
    )
    p.add_argument(
        "--iniciar-com-windows",
        action="store_true",
        help="tambem cria o atalho em shell:startup, para o Acentua abrir junto com o Windows",
    )
    p.add_argument(
        "--remover",
        action="store_true",
        help="apaga os atalhos criados (area de trabalho e inicializacao)",
    )
    args = p.parse_args(argv)

    if os.name != "nt":
        print(f"{ERRO} o Acentua so funciona no Windows.")
        return 1

    na_mesa = area_de_trabalho() / NOME_ATALHO
    na_inicializacao = pasta_inicializacao() / NOME_ATALHO

    # ---- remover -----------------------------------------------------------
    if args.remover:
        achou = False
        for alvo in (na_mesa, na_inicializacao):
            if remover_atalho(alvo):
                print(f"{OK} removido: {alvo}")
                achou = True
        if not achou:
            print(f"{AVISO} nenhum atalho do Acentua encontrado. Nada a fazer.")
        return 0

    # ---- criar -------------------------------------------------------------
    alvo = executavel_sem_console()
    if alvo is None:
        print(f"{ERRO} nao achei o `pythonw.exe`.")
        print("      Rode INSTALAR.bat primeiro (ele cria o ambiente em .venv).")
        return 1

    ico = icone()
    if ico is None:
        print(f"{AVISO} icone ainda nao gerado (src/corretor/dados/icone.ico).")
        print("      O atalho vai usar o icone padrao do Python.")
        print("      Para gerar: python scripts/gerar_icone.py  e rode este script de novo.")

    ok, erro = criar_atalho(na_mesa, alvo, ico)
    if not ok:
        print(f"{ERRO} nao consegui criar o atalho na area de trabalho.")
        print(f"      Motivo: {erro}")
        print(f"      Alternativa: crie o atalho a mao apontando para:")
        print(f"        {alvo} -m corretor")
        return 1
    print(f"{OK} atalho criado: {na_mesa}")

    if args.iniciar_com_windows:
        ok, erro = criar_atalho(na_inicializacao, alvo, ico)
        if not ok:
            print(f"{ERRO} nao consegui criar o atalho de inicializacao.")
            print(f"      Motivo: {erro}")
            return 1
        print(f"{OK} inicia com o Windows: {na_inicializacao}")
    else:
        print(f"      (para abrir junto com o Windows: "
              f"python scripts/criar_atalho.py --iniciar-com-windows)")

    print()
    print(f"      Alvo do atalho: {alvo} -m corretor")
    print(f"      Pasta de trabalho: {RAIZ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
