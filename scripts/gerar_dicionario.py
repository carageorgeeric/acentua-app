"""Gera `src/corretor/dados/dicionario.json.gz` a partir do corpus do pyspellchecker.

Rode com o Python do projeto:

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/gerar_dicionario.py

O `pyspellchecker` só é usado AQUI. O pacote em produção lê apenas o `.gz`
gerado, então não há dependência externa em runtime.

Formato do arquivo (JSON comprimido com gzip, UTF-8):

    {
      "versao": 1,
      "gerado_em": "2026-07-30T12:00:00Z",
      "fonte": "pyspellchecker pt",
      "grupos": {
        "nao":  [["não", 9235830]],
        "esta": [["está", 3629193], ["esta", 697934]]
      }
    }

A chave de cada grupo é a palavra em minúsculas e sem acentos — exatamente o
que o usuário digita no teclado compacto. O valor é a lista de grafias reais
ordenada por frequência decrescente.

Só entram grupos "úteis": aqueles em que alguma grafia difere da chave (ou
seja, tem acento ou cedilha). Um grupo cujo único membro é a própria chave
nunca gera correção e só ocuparia espaço.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "src" / "corretor" / "dados" / "dicionario.json.gz"

#: Letras aceitas numa palavra portuguesa. Qualquer entrada com um caractere
#: fora daqui é lixo do corpus (nomes estrangeiros, siglas, resíduo de OCR).
ALFABETO = set("abcdefghijklmnopqrstuvwxyzáàâãéêíóôõúüç'-")

#: Palavras portuguesas legítimas de uma letra. O corpus também tem `v` e `x`
#: soltos, que são resíduo e precisam sair.
UMA_LETRA = {"a", "à", "e", "é", "o", "ó"}

VERSAO_FORMATO = 1

#: O corpus é predominantemente de Portugal e o Acentua é para brasileiros.
#: Onde o europeu escreve `ó`/`é` antes de consoante nasal seguida de vogal
#: (`cerimónia`, `género`, `ténis`), o Brasil escreve `ô`/`ê`. A sílaba fechada
#: fica de fora de propósito: `também`, `contém` e `armazém` são iguais nos dois
#: lados do Atlântico e não podem virar `tambêm`.
_NASAL_ABERTA = re.compile(r"[óé](?=[mn][aeiouáâãéêíóôõú])")
_PARA_CIRCUNFLEXO = {"ó": "ô", "é": "ê"}

#: Diferenças lexicais que a regra da nasal não pega.
_LEXICO_BRASILEIRO = {
    "bebé": "bebê",
    "bebés": "bebês",
    "cocó": "cocô",
    "caché": "cachê",
    "cachés": "cachês",
    "suflé": "suflê",
    "suflés": "suflês",
    "puré": "purê",
    "purés": "purês",
    "bidé": "bidê",
    "croché": "crochê",
}


def abrasileirar(palavra: str) -> str:
    """Converte a grafia europeia do corpus para a brasileira, quando difere."""
    if palavra in _LEXICO_BRASILEIRO:
        return _LEXICO_BRASILEIRO[palavra]
    return _NASAL_ABERTA.sub(lambda m: _PARA_CIRCUNFLEXO[m.group()], palavra)


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return unicodedata.normalize(
        "NFC", "".join(c for c in decomposto if not unicodedata.combining(c))
    )


def diacriticos(palavra: str) -> int:
    """Quantas marcas de acento a palavra carrega — usado para desempate."""
    return sum(1 for c in unicodedata.normalize("NFD", palavra) if unicodedata.combining(c))


def aceita(palavra: str) -> bool:
    if not palavra:
        return False
    if any(c.isdigit() for c in palavra):
        return False
    if not set(palavra) <= ALFABETO:
        return False
    if len(palavra) == 1 and palavra not in UMA_LETRA:
        return False
    if palavra.startswith("-") or palavra.endswith("-"):
        return False
    return True


def carregar_corpus() -> tuple[dict[str, int], int]:
    """Devolve o corpus limpo e abrasileirado, mais o número de grafias trocadas."""
    from spellchecker import SpellChecker  # dependência só do script

    bruto = SpellChecker(language="pt").word_frequency.dictionary
    limpo: dict[str, int] = defaultdict(int)
    trocadas = 0
    for palavra, frequencia in bruto.items():
        p = palavra.strip().lower()
        if not aceita(p):
            continue
        brasileira = abrasileirar(p)
        trocadas += brasileira != p
        limpo[brasileira] += frequencia
    return dict(limpo), trocadas


def agrupar(corpus: dict[str, int]) -> dict[str, list[tuple[str, int]]]:
    grupos: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for palavra, frequencia in corpus.items():
        grupos[sem_acentos(palavra)].append((palavra, frequencia))
    return grupos


def podar(membros: list[tuple[str, int]], piso: int) -> list[tuple[str, int]]:
    """Remove grafias sem nenhuma evidência de uso dentro de um grupo que tem.

    O corpus dá frequência real a ~46 mil palavras e carimba as outras 370 mil
    com o mesmo valor de piso. Quando um grupo mistura os dois casos, o membro
    no piso é ruído (tipicamente o infinitivo com clítico: `casá`, `usá`,
    `historiá`) e atrapalharia o popup de alternativas.
    """
    teto = max(f for _, f in membros)
    if teto <= piso:
        return membros
    return [(p, f) for p, f in membros if f > piso]


def ordenar(chave: str, membros: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Frequência manda. No empate, vence a grafia que o usuário já digitou.

    Empate acontece nos 370 mil verbetes sem frequência real, quase todos
    pares como `abafamos`/`abafámos` (pretérito europeu) ou `abaliza`/`abalizá`
    (infinitivo com clítico). Nesses, não mexer é sempre mais seguro que
    inventar um acento.
    """
    return sorted(membros, key=lambda m: (-m[1], m[0] != chave, diacriticos(m[0]), m[0]))


def construir() -> tuple[dict[str, list[tuple[str, int]]], int]:
    corpus, trocadas = carregar_corpus()
    piso = min(corpus.values())
    uteis: dict[str, list[tuple[str, int]]] = {}
    for chave, membros in agrupar(corpus).items():
        podados = podar(membros, piso)
        if not any(p != chave for p, _ in podados):
            continue
        uteis[chave] = ordenar(chave, podados)
    return dict(sorted(uteis.items())), trocadas


def main() -> int:
    grupos, trocadas = construir()
    ambiguos = sum(1 for m in grupos.values() if len(m) > 1)

    conteudo = {
        "versao": VERSAO_FORMATO,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "fonte": "pyspellchecker pt",
        "grupos": {c: [[p, f] for p, f in m] for c, m in grupos.items()},
    }

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    bruto = json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    DESTINO.write_bytes(gzip.compress(bruto, 9))

    tamanho = DESTINO.stat().st_size
    print(f"grupos          : {len(grupos):,}")
    print(f"ambiguos (>1)   : {ambiguos:,}")
    print(f"grafias pt-BR   : {trocadas:,}")
    print(f"json cru        : {len(bruto) / 1024:,.0f} KiB")
    print(f"{DESTINO.name:<16}: {tamanho / 1024:,.0f} KiB")
    print(f"destino         : {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
