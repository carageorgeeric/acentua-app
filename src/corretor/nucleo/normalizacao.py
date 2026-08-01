"""Texto puro: tirar acento, achar a chave de busca, cortar em tokens, copiar caixa.

Este módulo é a base do núcleo e não conhece dicionário nem regras. Tudo aqui
é determinístico e testável sem I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "Token",
    "aplicar_capitalizacao",
    "chave",
    "deve_ignorar",
    "partes_compostas",
    "remover_acentos",
    "tem_acento",
    "tokenizar",
]


@dataclass(frozen=True, slots=True)
class Token:
    """Um pedaço do texto original. Concatenar todos reproduz o texto exato.

    `inicio` e `fim` são índices no texto de entrada, para a interface poder
    destacar ou desfazer uma troca sem recontar caracteres.
    """

    texto: str
    inicio: int
    fim: int
    e_palavra: bool


#: Apóstrofos tipográficos que os editores inserem no lugar do reto.
_APOSTROFOS = str.maketrans({"‘": "'", "’": "'", "ʼ": "'"})

_LETRA = r"[^\W\d_]"
_ALFANUM = r"[^\W_]"

#: Domínios e extensões que marcam um token como "não é português, não toque".
_TLD = (
    "com|br|org|net|io|dev|gov|edu|info|me|co|app|ai|xyz|pt|us|uk|de|fr|es|"
    "cloud|tech|site|online|store|blog"
)
_EXT = (
    "py|txt|md|json|js|jsx|ts|tsx|html|htm|css|scss|pdf|png|jpg|jpeg|gif|svg|"
    "webp|zip|rar|tar|gz|exe|dll|msi|csv|xls|xlsx|doc|docx|ppt|pptx|log|yml|"
    "yaml|toml|ini|cfg|conf|sh|bat|ps1|sql|db|env|lock|rs|go|java|c|cpp|h"
)

#: Ordem importa: o que é URL/e-mail/caminho tem que casar antes de virar palavra.
_PADRAO_TOKEN = re.compile(
    r"(?:https?|ftp|file)://\S+"
    r"|www\.\S+"
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|[@#]\w[\w.-]*"
    r"|(?:[\w.-]+[\\/]+)+[\w.:\\/+-]*"
    rf"|\w[\w-]*(?:\.[\w-]+)*\.(?:{_TLD}|{_EXT})\b(?:[?#]\S*)?"
    r"|\w[\w']*(?:[-']\w[\w']*)*",
    re.UNICODE,
)

_TEM_DIGITO = re.compile(r"\d")
_SO_LETRAS_E_LIGACOES = re.compile(rf"^{_LETRA}(?:[-']?{_LETRA})*$", re.UNICODE)
_DOMINIO_OU_ARQUIVO = re.compile(
    rf"^{_ALFANUM}[\w-]*(?:\.[\w-]+)*\.(?:{_TLD}|{_EXT})$", re.IGNORECASE
)


def remover_acentos(texto: str) -> str:
    """Decompõe em NFD, joga fora as marcas combinantes e recompõe.

    O `ç` sai de graça: em NFD ele vira `c` + cedilha combinante.
    """
    decomposto = unicodedata.normalize("NFD", texto)
    return unicodedata.normalize(
        "NFC", "".join(c for c in decomposto if not unicodedata.combining(c))
    )


def chave(palavra: str) -> str:
    """A forma que o usuário digita no teclado compacto: minúscula e sem acento."""
    return remover_acentos(palavra.translate(_APOSTROFOS).lower())


def tem_acento(palavra: str) -> bool:
    return remover_acentos(palavra) != palavra


def aplicar_capitalizacao(modelo: str, alvo: str) -> str:
    """Copia o padrão de caixa de `modelo` para `alvo`.

    Caixa mista (`nAo`) é tratada como minúscula: é digitação acidental, e
    inventar um padrão a partir dela deixaria o resultado imprevisível.
    """
    if not modelo or not alvo:
        return alvo
    if len(modelo) > 1 and modelo.isupper():
        return alvo.upper()
    if modelo[0].isupper():
        return alvo[0].upper() + alvo[1:]
    return alvo


def tokenizar(texto: str) -> list[Token]:
    """Corta o texto em palavras e separadores sem perder um caractere.

    Vale a invariante `"".join(t.texto for t in tokenizar(x)) == x` para
    qualquer entrada, inclusive emoji, tabulação e quebra de linha.
    """
    tokens: list[Token] = []
    posicao = 0
    for achado in _PADRAO_TOKEN.finditer(texto):
        inicio, fim = achado.span()
        if inicio > posicao:
            tokens.append(Token(texto[posicao:inicio], posicao, inicio, False))
        tokens.append(Token(achado.group(), inicio, fim, True))
        posicao = fim
    if posicao < len(texto):
        tokens.append(Token(texto[posicao:], posicao, len(texto), False))
    return tokens


def deve_ignorar(token: str) -> bool:
    """True para tudo que nunca deve ganhar acento: URL, e-mail, código, número.

    O critério é conservador de propósito — na dúvida, não mexer. Um `@` ou uma
    barra no meio do token já bastam: nenhuma palavra portuguesa tem isso.
    """
    if not token:
        return True
    if _TEM_DIGITO.search(token):
        return True
    if token[0] in "@#":
        return True
    baixo = token.lower()
    if baixo.startswith(("http://", "https://", "ftp://", "file://", "www.")):
        return True
    if any(c in token for c in "@/\\_"):
        return True
    if "::" in token:
        return True
    if _DOMINIO_OU_ARQUIVO.match(token):
        return True
    return not _SO_LETRAS_E_LIGACOES.match(token)


def partes_compostas(palavra: str) -> list[str]:
    """Quebra `guarda-chuva` / `d'agua` em partes e separadores, alternando.

    Índices pares são pedaços de palavra, ímpares são o hífen ou o apóstrofo.
    Devolve lista de um elemento só quando não há composição.
    """
    return re.split(r"([-'])", palavra)
