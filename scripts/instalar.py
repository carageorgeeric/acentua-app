"""Instala o Acentua. Versao Python do INSTALAR.bat, para quem prefere terminal.

    python scripts/instalar.py
    python scripts/instalar.py --iniciar-com-windows
    python scripts/instalar.py --sem-atalho

Pode rodar quantas vezes quiser: cada passo detecta o que ja esta pronto e
pula. Nada e apagado, o `.venv` existente e reaproveitado.

Rode com o Python do sistema (`py -3 scripts/instalar.py`). Ele cria o `.venv`
e usa o Python de dentro dele para o resto.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENV = RAIZ / ".venv"
DADOS = RAIZ / "src" / "corretor" / "dados"
DICIONARIO = DADOS / "dicionario.json.gz"
ICONE = DADOS / "icone.ico"

PYTHON_MINIMO = (3, 11)
TOTAL_PASSOS = 6

OK = "  [ok]   "
FALHA = "  [FALHA]"
PULOU = "  [pula] "
AVISO = "  [!]    "

LINK_PYTHON = "https://www.python.org/downloads/"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _preparar_saida() -> None:
    """Evita UnicodeEncodeError em consoles antigos (cp850/cp1252)."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def titulo(n: int, texto: str) -> None:
    print()
    print(f"[{n}/{TOTAL_PASSOS}] {texto}")


def falhar(motivo: str, *como_resolver: str) -> None:
    print(f"{FALHA} {motivo}")
    for linha in como_resolver:
        print(f"         {linha}")


def python_do_venv() -> Path:
    """Caminho do interpretador dentro do `.venv`."""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def rodar(comando: list[str], descricao: str) -> bool:
    """Roda um comando mostrando a saida ao vivo. Devolve True se deu certo."""
    # Sem o flush, o texto do subprocesso aparece antes do nosso quando a
    # saida esta sendo redirecionada para um arquivo ou pipe.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(comando, cwd=RAIZ)
    except OSError as e:
        falhar(f"{descricao}: nao consegui executar o comando.", str(e))
        return False
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Passos
# ---------------------------------------------------------------------------


def passo_1_versao_python() -> bool:
    titulo(1, "Conferindo a versao do Python")
    atual = sys.version_info[:3]
    print(f"         Python {'.'.join(map(str, atual))} em {sys.executable}")

    if sys.version_info < PYTHON_MINIMO:
        minimo = ".".join(map(str, PYTHON_MINIMO))
        falhar(
            f"Python {minimo} ou mais novo e obrigatorio.",
            f"Baixe uma versao atual em {LINK_PYTHON}",
            'Marque "Add python.exe to PATH" durante a instalacao.',
            "Depois rode este script de novo.",
        )
        return False

    if os.name != "nt":
        print(f"{AVISO} o Acentua so funciona no Windows. Vou continuar, mas o app")
        print("         nao vai rodar neste sistema.")

    print(f"{OK} versao serve")
    return True


def passo_2_ambiente() -> bool:
    titulo(2, "Preparando o ambiente isolado (.venv)")
    py = python_do_venv()

    if py.is_file():
        print(f"{PULOU} ja existe em {VENV}")
        return True

    print(f"         criando em {VENV} ...")
    if not rodar([sys.executable, "-m", "venv", str(VENV)], "criacao do .venv"):
        falhar(
            "nao consegui criar o ambiente virtual.",
            "1. Se o projeto estiver dentro do OneDrive, mova para algo simples",
            "   como C:\\Acentua e tente de novo.",
            "2. Verifique se o antivirus nao esta bloqueando a pasta.",
            "3. Verifique se ha espaco livre em disco.",
        )
        return False

    if not py.is_file():
        falhar(
            "o comando terminou sem erro mas o Python do venv nao apareceu.",
            f"Esperado em: {py}",
            "Apague a pasta .venv e rode este script de novo.",
        )
        return False

    print(f"{OK} ambiente criado")
    return True


def passo_3_instalar_pacote() -> bool:
    titulo(3, "Instalando o Acentua e suas dependencias")
    print("         (parte demorada; precisa de internet na primeira vez)")
    py = str(python_do_venv())

    subprocess.run(
        [py, "-m", "pip", "install", "--upgrade", "pip", "--quiet",
         "--disable-pip-version-check"],
        cwd=RAIZ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if not rodar([py, "-m", "pip", "install", "-e", ".",
                  "--disable-pip-version-check"], "instalacao do pacote"):
        falhar(
            "o pip nao conseguiu instalar o pacote (veja o erro acima).",
            "1. Sem internet? Conecte e rode de novo.",
            "2. Proxy da empresa? Use: pip install -e . --proxy SEU_PROXY",
            "3. Antivirus/firewall podem bloquear o pip.",
        )
        return False

    print(f"{OK} pacote instalado (modo editavel)")
    return True


def passo_4_dicionario(forcar: bool = False) -> bool:
    titulo(4, "Conferindo o dicionario de palavras")
    gerador = RAIZ / "scripts" / "gerar_dicionario.py"

    if DICIONARIO.is_file() and not forcar:
        mb = DICIONARIO.stat().st_size / (1024 * 1024)
        print(f"{PULOU} ja existe ({mb:.1f} MB) em {DICIONARIO}")
        return True

    if not gerador.is_file():
        falhar(
            "dicionario ausente e o gerador tambem nao esta aqui.",
            f"Esperado: {DICIONARIO}",
            "Baixe o projeto de novo pelo GitHub: o dicionario ja vem pronto.",
        )
        return False

    print("         gerando agora (leva ~1 minuto)...")
    py = str(python_do_venv())
    subprocess.run(
        [py, "-m", "pip", "install", "pyspellchecker", "--quiet",
         "--disable-pip-version-check"],
        cwd=RAIZ,
        check=False,
    )

    if not rodar([py, str(gerador)], "geracao do dicionario") or not DICIONARIO.is_file():
        falhar(
            "nao consegui gerar o dicionario.",
            "Baixe o projeto de novo pelo GitHub: o dicionario ja vem pronto",
            "junto com o codigo, e este passo deixa de ser necessario.",
        )
        return False

    print(f"{OK} dicionario gerado")
    return True


def passo_5_icones() -> bool:
    """Icone ausente nao impede o app de rodar: nunca derruba a instalacao."""
    titulo(5, "Conferindo os icones")
    gerador = RAIZ / "scripts" / "gerar_icone.py"

    if ICONE.is_file():
        print(f"{PULOU} ja existem em {DADOS}")
        return True

    if not gerador.is_file():
        print(f"{AVISO} icones ausentes e sem gerador. O app usa o icone padrao.")
        return True

    print("         gerando agora...")
    if not rodar([str(python_do_venv()), str(gerador)], "geracao dos icones"):
        print(f"{AVISO} nao consegui gerar os icones. O app funciona assim mesmo.")
        return True

    print(f"{OK} icones gerados")
    return True


def passo_6_atalho(iniciar_com_windows: bool) -> bool:
    titulo(6, "Criando o atalho na area de trabalho")
    script = RAIZ / "scripts" / "criar_atalho.py"

    if not script.is_file():
        print(f"{AVISO} scripts/criar_atalho.py nao encontrado. Pulando o atalho.")
        print("         Voce ainda pode abrir o app com o Acentua.bat.")
        return True

    comando = [str(python_do_venv()), str(script)]
    if iniciar_com_windows:
        comando.append("--iniciar-com-windows")

    if not rodar(comando, "criacao do atalho"):
        falhar(
            "nao consegui criar o atalho (o app JA esta instalado, so falta o icone).",
            "Use o arquivo Acentua.bat desta pasta para abrir o app.",
            f"Ou tente de novo: python {script.relative_to(RAIZ)}",
        )
        return False

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def resumo_final(iniciou_com_windows: bool) -> None:
    print()
    print("=" * 62)
    print("  PRONTO! O Acentua esta instalado.")
    print("=" * 62)
    print()
    print("  Como usar:")
    print("    1. Abra o atalho 'Acentua' da area de trabalho.")
    print("       Nao abre janela: ele fica na bandeja, perto do relogio.")
    print("    2. Digite sem acento em qualquer programa e selecione o texto.")
    print("    3. Aperte Ctrl+Alt+C.")
    print()
    print("  Atalhos:")
    print("    Ctrl+Alt+C   corrige a selecao")
    print("    Ctrl+Alt+S   mostra sugestoes antes de trocar")
    print("    Ctrl+Z       desfaz, como em qualquer programa")
    print()
    if not iniciou_com_windows:
        print("  Para abrir junto com o Windows:")
        print("    python scripts/criar_atalho.py --iniciar-com-windows")
        print()


def main(argv: list[str] | None = None) -> int:
    _preparar_saida()

    p = argparse.ArgumentParser(
        prog="instalar.py",
        description="Instala o Acentua neste computador. Pode rodar varias vezes.",
    )
    p.add_argument("--iniciar-com-windows", action="store_true",
                   help="tambem faz o Acentua abrir junto com o Windows")
    p.add_argument("--sem-atalho", action="store_true",
                   help="nao cria o atalho na area de trabalho")
    p.add_argument("--forcar-dicionario", action="store_true",
                   help="regera o dicionario mesmo que ele ja exista")
    args = p.parse_args(argv)

    print()
    print("=" * 62)
    print("  ACENTUA - instalacao")
    print("  Digite sem acento. Aperte Ctrl+Alt+C. Pronto.")
    print("=" * 62)

    if not passo_1_versao_python():
        return 1
    if not passo_2_ambiente():
        return 1
    if not passo_3_instalar_pacote():
        return 1
    if not passo_4_dicionario(forcar=args.forcar_dicionario):
        return 1
    passo_5_icones()

    if args.sem_atalho:
        titulo(6, "Atalho na area de trabalho")
        print(f"{PULOU} pedido com --sem-atalho")
    elif not passo_6_atalho(args.iniciar_com_windows):
        return 1

    resumo_final(args.iniciar_com_windows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
