"""Carrega o dicionário de grupos de acentuação e responde consultas.

O arquivo `dados/dicionario.json.gz` é gerado por `scripts/gerar_dicionario.py`
e mapeia a chave sem acento para as grafias reais, da mais frequente para a
menos frequente. Aqui a única inteligência é a sobreposição das exceções
curadas — a decisão de qual grafia usar é do corretor.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from corretor import DADOS
from corretor.nucleo.normalizacao import chave
from corretor.tipos import Candidato

__all__ = ["Dicionario"]

ARQUIVO_DICIONARIO = "dicionario.json.gz"
ARQUIVO_EXCECOES = "excecoes.json"

#: Frequência dada a uma grafia que só existe nas exceções, sem apoio do corpus.
_FREQUENCIA_CURADA = 1_000


class Dicionario:
    """Grupos de acentuação em memória. Imutável depois de carregado."""

    __slots__ = ("_grupos", "versao", "gerado_em")

    def __init__(
        self,
        grupos: dict[str, list[tuple[str, int]]],
        versao: int = 0,
        gerado_em: str = "",
    ) -> None:
        self._grupos = grupos
        self.versao = versao
        self.gerado_em = gerado_em

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> Dicionario:
        """Lê o `.gz` inteiro de uma vez — 100 mil grupos custam ~0,2 s e ~40 MB.

        Streaming aqui não compensa: o corretor consulta o dicionário a cada
        palavra e precisa de acesso O(1), então tudo fica residente.
        """
        alvo = caminho or DADOS / ARQUIVO_DICIONARIO
        with gzip.open(alvo, "rb") as arquivo:
            bruto: dict[str, Any] = json.loads(arquivo.read())

        grupos: dict[str, list[tuple[str, int]]] = {
            c: [(p, int(f)) for p, f in membros] for c, membros in bruto["grupos"].items()
        }
        dicionario = cls(grupos, int(bruto.get("versao", 0)), str(bruto.get("gerado_em", "")))

        excecoes = (caminho.parent if caminho else DADOS) / ARQUIVO_EXCECOES
        if excecoes.is_file():
            dicionario.aplicar_excecoes(json.loads(excecoes.read_text(encoding="utf-8")))
        return dicionario

    def aplicar_excecoes(self, excecoes: dict[str, list[str]]) -> None:
        """Substitui o grupo inteiro da chave pela lista curada, na ordem dada.

        Substituição, não fusão: quando a frequência do corpus erra, quase
        sempre é porque ele conta uma grafia que ninguém usa (`porem` como
        verbo, `ate` como forma de atar). Deixar essa grafia no grupo faria o
        popup oferecer lixo. Grafias sem frequência conhecida entram com um
        valor nominal, suficiente para ordenar mas não para dominar o cálculo
        de confiança de grupos reais.
        """
        for bruta, palavras in excecoes.items():
            if bruta.startswith("_") or not palavras:
                continue
            c = chave(bruta)
            conhecidas = dict(self._grupos.get(c, ()))
            self._grupos[c] = [
                (p, conhecidas.get(p, _FREQUENCIA_CURADA)) for p in palavras
            ]

    def candidatos(self, palavra: str) -> list[Candidato]:
        """Grafias possíveis para a palavra, da mais provável para a menos.

        Lista vazia quer dizer "não sei nada sobre isso" — e o corretor então
        não encosta na palavra.
        """
        membros = self._grupos.get(chave(palavra))
        if not membros:
            return []
        return [Candidato(p, f) for p, f in membros]

    def tem_grupo(self, palavra: str) -> bool:
        return chave(palavra) in self._grupos

    def __len__(self) -> int:
        return len(self._grupos)

    def __repr__(self) -> str:
        return f"Dicionario(grupos={len(self._grupos)}, versao={self.versao})"
