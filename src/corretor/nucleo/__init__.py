"""Núcleo de correção: decide como uma palavra sem acento deve ser escrita.

Só depende da stdlib e de `corretor.tipos`. Nada aqui sabe que existe Windows,
atalho de teclado ou popup — isso é problema das outras camadas.
"""

from __future__ import annotations

from corretor.nucleo.corretor import CorretorOffline
from corretor.nucleo.dicionario import Dicionario
from corretor.nucleo.normalizacao import (
    Token,
    aplicar_capitalizacao,
    chave,
    deve_ignorar,
    remover_acentos,
    tokenizar,
)

__all__ = [
    "CorretorOffline",
    "Dicionario",
    "Token",
    "aplicar_capitalizacao",
    "chave",
    "deve_ignorar",
    "remover_acentos",
    "tokenizar",
]
