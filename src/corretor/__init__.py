"""Acentua — corretor de acentuação para quem digita sem acento.

Selecione um texto em qualquer programa, aperte o atalho e ele volta
acentuado. Pensado para teclados compactos (60%, 65%, 68%) e layouts sem
tecla morta, onde `ç`, `~` e os acentos são difíceis de alcançar.
"""

from pathlib import Path

NOME_APP = "Acentua"
VERSAO = "1.1.0"
DESCRICAO = "Corretor de acentuação para teclados compactos"

#: Pasta com os dados que acompanham o pacote (dicionário, ícones).
DADOS = Path(__file__).parent / "dados"

__all__ = ["NOME_APP", "VERSAO", "DESCRICAO", "DADOS"]
