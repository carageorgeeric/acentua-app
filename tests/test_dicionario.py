"""Testes do carregamento e das consultas ao dicionário."""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import pytest

from corretor import DADOS
from corretor.nucleo.dicionario import Dicionario


@pytest.fixture(scope="module")
def dicionario() -> Dicionario:
    return Dicionario.carregar()


def test_arquivo_existe() -> None:
    assert (DADOS / "dicionario.json.gz").is_file()
    assert (DADOS / "excecoes.json").is_file()


def test_carrega_em_menos_de_um_segundo() -> None:
    inicio = time.perf_counter()
    Dicionario.carregar()
    assert time.perf_counter() - inicio < 1.0


def test_tem_volume_de_dicionario_de_verdade(dicionario: Dicionario) -> None:
    assert len(dicionario) > 100_000


@pytest.mark.parametrize(
    ("digitada", "esperada"),
    [
        ("nao", "não"),
        ("coracao", "coração"),
        ("voce", "você"),
        ("entao", "então"),
        ("tambem", "também"),
        ("informacao", "informação"),
        ("dificil", "difícil"),
        ("familia", "família"),
        ("tres", "três"),
        ("mae", "mãe"),
        ("irmao", "irmão"),
        ("possivel", "possível"),
    ],
)
def test_candidato_mais_provavel(dicionario: Dicionario, digitada: str, esperada: str) -> None:
    assert dicionario.candidatos(digitada)[0].palavra == esperada


def test_candidatos_vem_ordenados_por_frequencia(dicionario: Dicionario) -> None:
    for chave in ("esta", "avo", "pais", "e", "a"):
        frequencias = [c.frequencia for c in dicionario.candidatos(chave)]
        assert frequencias == sorted(frequencias, reverse=True)


def test_consulta_ignora_caixa_e_acento(dicionario: Dicionario) -> None:
    referencia = dicionario.candidatos("nao")
    assert dicionario.candidatos("NAO") == referencia
    assert dicionario.candidatos("Não") == referencia


def test_palavra_desconhecida_nao_tem_grupo(dicionario: Dicionario) -> None:
    assert dicionario.candidatos("xyzabc") == []
    assert not dicionario.tem_grupo("xyzabc")
    assert dicionario.tem_grupo("nao")


def test_grupo_inutil_foi_descartado(dicionario: Dicionario) -> None:
    """`casa` só tem uma grafia real; guardar o grupo seria peso morto."""
    assert not dicionario.tem_grupo("casa")
    assert not dicionario.tem_grupo("mesa")


def test_grupo_ambiguo_traz_as_duas_grafias(dicionario: Dicionario) -> None:
    palavras = [c.palavra for c in dicionario.candidatos("esta")]
    assert palavras == ["está", "esta"]


# --- exceções ---------------------------------------------------------------


def test_excecoes_corrigem_o_viés_europeu_do_corpus(dicionario: Dicionario) -> None:
    """No corpus, `estás` (tu) ganha de `estas`. No Brasil é o contrário."""
    assert dicionario.candidatos("estas")[0].palavra == "estas"
    assert dicionario.candidatos("facas")[0].palavra == "facas"
    assert dicionario.candidatos("papa")[0].palavra == "papa"


def test_excecoes_criam_grupo_que_falta_no_corpus(dicionario: Dicionario) -> None:
    assert dicionario.candidatos("cade")[0].palavra == "cadê"
    assert dicionario.candidatos("ne")[0].palavra == "né"


def test_excecoes_removem_grafia_fantasma(dicionario: Dicionario) -> None:
    assert [c.palavra for c in dicionario.candidatos("porem")] == ["porém"]


def test_aplicar_excecoes_substitui_o_grupo_inteiro() -> None:
    d = Dicionario({"teste": [("tesTE", 10), ("teste", 5)]})
    d.aplicar_excecoes({"teste": ["testé"]})
    assert [c.palavra for c in d.candidatos("teste")] == ["testé"]


def test_aplicar_excecoes_ignora_comentarios() -> None:
    d = Dicionario({"nao": [("não", 10)]})
    d.aplicar_excecoes({"_comentario": ["ignorado"], "nao": ["não"]})
    assert not d.tem_grupo("_comentario")


def test_carregar_de_caminho_alternativo(tmp_path: Path) -> None:
    alvo = tmp_path / "dicionario.json.gz"
    conteudo = {"versao": 1, "gerado_em": "hoje", "grupos": {"nao": [["não", 9]]}}
    alvo.write_bytes(gzip.compress(json.dumps(conteudo, ensure_ascii=False).encode("utf-8")))

    d = Dicionario.carregar(alvo)
    assert d.versao == 1
    assert len(d) == 1
    assert d.candidatos("nao")[0].palavra == "não"


def test_carregar_aplica_excecoes_do_mesmo_diretorio(tmp_path: Path) -> None:
    alvo = tmp_path / "dicionario.json.gz"
    conteudo = {"versao": 1, "grupos": {"esta": [["está", 9], ["esta", 1]]}}
    alvo.write_bytes(gzip.compress(json.dumps(conteudo, ensure_ascii=False).encode("utf-8")))
    (tmp_path / "excecoes.json").write_text(
        json.dumps({"esta": ["esta", "está"]}, ensure_ascii=False), encoding="utf-8"
    )

    d = Dicionario.carregar(alvo)
    assert d.candidatos("esta")[0].palavra == "esta"


# --- grafia brasileira ------------------------------------------------------


@pytest.mark.parametrize(
    ("digitada", "esperada"),
    [
        ("genero", "gênero"),
        ("cerimonia", "cerimônia"),
        ("quilometros", "quilômetros"),
        ("premio", "prêmio"),
        ("tenis", "tênis"),
        ("bebe", "bebê"),
        ("economico", "econômico"),
        ("fenomeno", "fenômeno"),
    ],
)
def test_grafia_brasileira_vence_a_europeia(
    dicionario: Dicionario, digitada: str, esperada: str
) -> None:
    assert dicionario.candidatos(digitada)[0].palavra == esperada


@pytest.mark.parametrize("digitada", ["tambem", "contem", "alguem", "ninguem", "porem", "alem"])
def test_silaba_fechada_nao_vira_circunflexo(dicionario: Dicionario, digitada: str) -> None:
    """`também` é igual nos dois lados do Atlântico — não pode virar `tambêm`."""
    assert "ê" not in dicionario.candidatos(digitada)[0].palavra
