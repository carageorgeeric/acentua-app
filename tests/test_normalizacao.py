"""Testes de normalização, tokenização e caixa."""

from __future__ import annotations

import pytest

from corretor.nucleo.normalizacao import (
    aplicar_capitalizacao,
    chave,
    deve_ignorar,
    partes_compostas,
    remover_acentos,
    tem_acento,
    tokenizar,
)


# --- remover_acentos / chave ------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("não", "nao"),
        ("coração", "coracao"),
        ("você", "voce"),
        ("ÇÃO", "CAO"),
        ("pêssego", "pessego"),
        ("Água", "Agua"),
        ("sem acento", "sem acento"),
        ("", ""),
        ("três irmãos à mesa", "tres irmaos a mesa"),
    ],
)
def test_remover_acentos(entrada: str, esperado: str) -> None:
    assert remover_acentos(entrada) == esperado


def test_cedilha_vira_c() -> None:
    assert remover_acentos("ação") == "acao"
    assert remover_acentos("Ç") == "C"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("NÃO", "nao"),
        ("Você", "voce"),
        ("guarda-chuva", "guarda-chuva"),
        ("d’água", "d'agua"),
        ("D'Água", "d'agua"),
    ],
)
def test_chave(entrada: str, esperado: str) -> None:
    assert chave(entrada) == esperado


def test_tem_acento() -> None:
    assert tem_acento("não")
    assert tem_acento("ação")
    assert not tem_acento("nao")
    assert not tem_acento("casa")


# --- aplicar_capitalizacao --------------------------------------------------


@pytest.mark.parametrize(
    ("modelo", "alvo", "esperado"),
    [
        ("nao", "não", "não"),
        ("Nao", "não", "Não"),
        ("NAO", "não", "NÃO"),
        ("nAo", "não", "não"),
        ("VOCE", "você", "VOCÊ"),
        ("Voce", "você", "Você"),
        ("A", "à", "À"),
        ("a", "à", "à"),
        ("", "não", "não"),
    ],
)
def test_aplicar_capitalizacao(modelo: str, alvo: str, esperado: str) -> None:
    assert aplicar_capitalizacao(modelo, alvo) == esperado


def test_caixa_mista_vira_minuscula() -> None:
    """`nAo` é erro de digitação; imitar o padrão daria um resultado imprevisível."""
    assert aplicar_capitalizacao("nAoO", "não") == "não"


# --- tokenizar --------------------------------------------------------------

TEXTOS = [
    "",
    "nao",
    "nao sei",
    "  espaço   duplo  ",
    "linha um\nlinha dois",
    "com\ttab\tno meio",
    "pontuação, vírgula; ponto. exclamação! interrogação?",
    "emoji 🎉 no meio 👋 do texto",
    "aspas \"duplas\" e 'simples'",
    "guarda-chuva e d'água",
    "http://exemplo.com/pagina?x=1 no meio",
    "email@dominio.com.br e @handle e #tag",
    "C:\\Users\\teste\\arquivo.txt",
    "src/corretor/nucleo/corretor.py",
    "\n\n\n",
    "   ",
    "1234 e 12,5 e 3.14",
    "MAIÚSCULAS e minúsculas",
    "reticências... e travessão — aqui",
]


@pytest.mark.parametrize("texto", TEXTOS)
def test_tokenizar_preserva_o_texto_exato(texto: str) -> None:
    assert "".join(t.texto for t in tokenizar(texto)) == texto


@pytest.mark.parametrize("texto", TEXTOS)
def test_tokenizar_indices_batem_com_o_texto(texto: str) -> None:
    for token in tokenizar(texto):
        assert texto[token.inicio : token.fim] == token.texto


@pytest.mark.parametrize("texto", TEXTOS)
def test_tokenizar_nao_deixa_buraco(texto: str) -> None:
    posicao = 0
    for token in tokenizar(texto):
        assert token.inicio == posicao
        posicao = token.fim
    assert posicao == len(texto)


def test_tokenizar_separa_palavra_de_pontuacao() -> None:
    tokens = tokenizar("nao, sim!")
    assert [t.texto for t in tokens] == ["nao", ", ", "sim", "!"]
    assert [t.e_palavra for t in tokens] == [True, False, True, False]


def test_tokenizar_mantem_hifen_e_apostrofo_juntos() -> None:
    assert [t.texto for t in tokenizar("guarda-chuva")] == ["guarda-chuva"]
    assert [t.texto for t in tokenizar("d'agua")] == ["d'agua"]


def test_tokenizar_url_vira_um_token_so() -> None:
    tokens = [t.texto for t in tokenizar("veja https://foo.com/a/b agora")]
    assert "https://foo.com/a/b" in tokens


# --- deve_ignorar -----------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "http://exemplo.com",
        "https://exemplo.com/pagina",
        "www.exemplo.com.br",
        "algo.com/",
        "site.com.br",
        "arquivo.py",
        "relatorio.pdf",
        "usuario@dominio.com",
        "@joao",
        "#carnaval",
        "abc123",
        "2024",
        "nome_da_variavel",
        "src/corretor",
        "C:\\Users",
        "std::vector",
    ],
)
def test_deve_ignorar_verdadeiro(token: str) -> None:
    assert deve_ignorar(token)


@pytest.mark.parametrize(
    "token",
    ["nao", "coracao", "guarda-chuva", "d'agua", "Você", "A", "e", "informacao"],
)
def test_deve_ignorar_falso(token: str) -> None:
    assert not deve_ignorar(token)


# --- partes_compostas -------------------------------------------------------


def test_partes_compostas() -> None:
    assert partes_compostas("guarda-chuva") == ["guarda", "-", "chuva"]
    assert partes_compostas("d'agua") == ["d", "'", "agua"]
    assert partes_compostas("nao") == ["nao"]
    assert partes_compostas("bem-me-quer") == ["bem", "-", "me", "-", "quer"]
