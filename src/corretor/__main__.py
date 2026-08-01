"""Permite iniciar o Acentua com ``python -m corretor``.

É assim que o atalho da área de trabalho chama o programa: pelo ``pythonw.exe``
do ambiente virtual, que não abre janela de console.
"""

from corretor.app import main

if __name__ == "__main__":
    raise SystemExit(main())
