"""Testes das regras de contexto.

Cada regra da tabela precisa de pelo menos um caso que a justifique e um caso
que mostre onde ela NÃO deve disparar. Regra sem contraexemplo é regra que
ninguém sabe prever.
"""

from __future__ import annotations

import pytest

from corretor.nucleo.contexto import (
    REGRAS,
    parece_feminino,
    parece_verbo_nos,
    reordenar,
)
from corretor.tipos import Candidato


def escolher(
    grupo: list[tuple[str, int]],
    chave: str,
    anterior: str | None = None,
    seguinte: str | None = None,
    inicio_de_frase: bool = False,
) -> str:
    candidatos = [Candidato(p, f) for p, f in grupo]
    return reordenar(candidatos, chave, anterior, seguinte, inicio_de_frase)[0].palavra


E = [("e", 7_564_611), ("é", 4_710_714)]
A = [("a", 21_770_886), ("à", 396_706)]
AS = [("as", 2_711_701), ("às", 191_745)]
ESTA = [("está", 3_629_193), ("esta", 697_934)]
PAIS = [("pais", 77_137), ("país", 44_445)]
AVO = [("avó", 19_722), ("avô", 18_057)]
SABIA = [("sabia", 175_572), ("sábia", 753)]
SECRETARIA = [("secretária", 10_329), ("secretaria", 418)]
DUVIDA = [("dúvida", 15_392), ("duvida", 1_221)]
PRATICA = [("prática", 4_244), ("pratica", 1_153)]
PUBLICO = [("público", 18_357), ("publico", 720)]
NOS = [("nos", 922_374), ("nós", 401_565)]
DA = [("da", 3_346_238), ("dá", 97_289)]


# --- e / é ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anterior", "seguinte"),
    [
        ("isso", "bom"),
        ("isto", "verdade"),
        ("aquilo", "estranho"),
        ("tudo", "possivel"),
        ("quem", "voce"),
        ("que", "isso"),
        ("nao", "assim"),
        ("cafe", "otimo"),
        ("livro", "interessante"),
        ("prova", "dificil"),
        ("preco", "muito"),
        ("resultado", "melhor"),
        ("maria", "professora"),
        ("novo", "medico"),
    ],
)
def test_e_vira_verbo(anterior: str, seguinte: str) -> None:
    assert escolher(E, "e", anterior, seguinte) == "é"


@pytest.mark.parametrize(
    ("anterior", "seguinte"),
    [
        ("pao", "queijo"),
        ("cafe", "leite"),
        ("preto", "branco"),
        ("bom", "barato"),
        ("rapido", "facil"),
        ("pai", "mae"),
        ("medico", "enfermeiro"),
        ("ela", "ele"),
        ("quando", "onde"),
        ("voce", "o"),
        ("eu", "a"),
        ("mais", "menos"),
    ],
)
def test_e_continua_conjuncao(anterior: str, seguinte: str) -> None:
    assert escolher(E, "e", anterior, seguinte) == "e"


def test_e_sem_vizinhanca_fica_na_frequencia() -> None:
    assert escolher(E, "e", None, None) == "e"


def test_artigo_depois_nao_e_gatilho() -> None:
    """"você e o João" é coordenação; o artigo sozinho não prova predicado."""
    assert escolher(E, "e", "voce", "o") == "e"
    assert escolher(E, "e", "cafe", "o") == "e"


# --- a / à ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anterior", "seguinte"),
    [
        ("vou", "escola"),
        ("fui", "praia"),
        ("devido", "chuva"),
        ("responda", "pergunta"),
        ("referente", "solicitacao"),
        ("gracas", "familia"),
    ],
)
def test_crase(anterior: str, seguinte: str) -> None:
    assert escolher(A, "a", anterior, seguinte) == "à"


@pytest.mark.parametrize(
    ("anterior", "seguinte"),
    [
        ("vou", "pe"),
        ("vou", "um"),
        ("fui", "uma"),
        ("devido", "problemas"),
        ("vou", "casa"),
        ("comprei", "escola"),
        ("a", "escola"),
        ("vou", "sao"),
    ],
)
def test_sem_crase(anterior: str, seguinte: str) -> None:
    assert escolher(A, "a", anterior, seguinte) == "a"


def test_as_vezes() -> None:
    assert escolher(AS, "as", "eu", "vezes") == "às"
    assert escolher(AS, "as", "comprei", "frutas") == "as"


def test_crase_no_plural() -> None:
    assert escolher(AS, "as", "responda", "perguntas") == "às"


# --- esta / está ------------------------------------------------------------


@pytest.mark.parametrize("seguinte", ["semana", "casa", "cidade", "questao", "pessoa", "e"])
def test_esta_demonstrativo(seguinte: str) -> None:
    assert escolher(ESTA, "esta", None, seguinte) == "esta"


@pytest.mark.parametrize("seguinte", ["bom", "boa", "pronta", "aqui", "na", "chovendo", "tarde"])
def test_esta_verbo(seguinte: str) -> None:
    assert escolher(ESTA, "esta", "ela", seguinte) == "está"


# --- pais / país ------------------------------------------------------------


def test_pais_com_determinante_masculino_singular() -> None:
    assert escolher(PAIS, "pais", "o", "esta") == "país"
    assert escolher(PAIS, "pais", "do", "onde") == "país"


def test_pais_no_plural_continua_progenitores() -> None:
    assert escolher(PAIS, "pais", "os", "dele") == "pais"
    assert escolher(PAIS, "pais", "meus", "moram") == "pais"


# --- avo / avô / avó --------------------------------------------------------


def test_avo_masculino() -> None:
    assert escolher(AVO, "avo", "meu", "tinha") == "avô"
    assert escolher(AVO, "avo", "o", "dele") == "avô"


def test_avo_feminino_por_frequencia() -> None:
    assert escolher(AVO, "avo", "minha", "fazia") == "avó"
    assert escolher(AVO, "avo", None, None) == "avó"


# --- demais pares -----------------------------------------------------------


def test_sabia_adjetivo() -> None:
    assert escolher(SABIA, "sabia", "muito", "para") == "sábia"
    assert escolher(SABIA, "sabia", "uma", "decisao") == "sábia"


def test_sabia_verbo() -> None:
    assert escolher(SABIA, "sabia", "nao", "disso") == "sabia"
    assert escolher(SABIA, "sabia", "eu", "que") == "sabia"


def test_secretaria_orgao() -> None:
    assert escolher(SECRETARIA, "secretaria", "a", "municipal") == "secretaria"


def test_secretaria_pessoa() -> None:
    assert escolher(SECRETARIA, "secretaria", "a", "dele") == "secretária"


def test_duvida_verbo() -> None:
    assert escolher(DUVIDA, "duvida", "ele", "de") == "duvida"


def test_duvida_substantivo() -> None:
    assert escolher(DUVIDA, "duvida", "uma", "sobre") == "dúvida"
    assert escolher(DUVIDA, "duvida", "tenho", "de") == "dúvida"


def test_pratica_verbo() -> None:
    assert escolher(PRATICA, "pratica", "ela", "natacao") == "pratica"
    assert escolher(PRATICA, "pratica", "quem", "esporte") == "pratica"


def test_pratica_substantivo() -> None:
    assert escolher(PRATICA, "pratica", "na", "isso") == "prática"
    assert escolher(PRATICA, "pratica", "muito", "mesmo") == "prática"


def test_publico_verbo() -> None:
    assert escolher(PUBLICO, "publico", "eu", "no") == "publico"


def test_publico_substantivo() -> None:
    assert escolher(PUBLICO, "publico", "o", "aplaudiu") == "público"


def test_nos_sujeito() -> None:
    assert escolher(NOS, "nos", None, "vamos") == "nós"
    assert escolher(NOS, "nos", None, "ficamos") == "nós"
    assert escolher(NOS, "nos", "entre", "nao") == "nós"


def test_nos_pronome_atono() -> None:
    assert escolher(NOS, "nos", "ele", "deu") == "nos"
    assert escolher(NOS, "nos", "para", "ajudar") == "nos"
    assert escolher(NOS, "nos", None, "termos") == "nos"


def test_da_verbo() -> None:
    assert escolher(DA, "da", "isso", "certo") == "dá"
    assert escolher(DA, "da", "nao", "pra") == "dá"
    assert escolher(DA, "da", "me", "agua") == "dá"


def test_da_preposicao() -> None:
    assert escolher(DA, "da", "casa", "minha") == "da"
    assert escolher(DA, "da", "nao", "forma") == "da"
    assert escolher(DA, "da", "perto", "escola") == "da"


# --- mecânica da tabela -----------------------------------------------------


def test_chave_sem_regra_mantem_a_ordem() -> None:
    grupo = [("história", 100), ("historia", 5)]
    assert escolher(grupo, "historia", "a", "dele") == "história"


def test_candidato_unico_nao_muda() -> None:
    assert escolher([("não", 9)], "nao", "isso", "bom") == "não"


def test_regra_nao_promove_grafia_ausente_do_grupo() -> None:
    """A regra de `é` não pode inventar `é` num grupo que só tem `e`."""
    assert escolher([("e", 10)], "e", "isso", "bom") == "e"


def test_reordenar_nao_perde_candidatos() -> None:
    candidatos = [Candidato(p, f) for p, f in ESTA]
    saida = reordenar(candidatos, "esta", None, "semana", False)
    assert sorted(c.palavra for c in saida) == sorted(c.palavra for c in candidatos)


def test_vizinhos_acentuados_tambem_casam() -> None:
    """O texto sendo corrigido tem palavras já acentuadas; a chave normaliza."""
    assert escolher(E, "e", "você", "ótimo") == "é"
    assert escolher(A, "a", "vou", "reunião") == "à"


def test_toda_regra_tem_justificativa() -> None:
    assert all(regra.porque for regra in REGRAS)


# --- heurísticas auxiliares -------------------------------------------------


@pytest.mark.parametrize(
    "palavra", ["escola", "reuniao", "cidade", "viagem", "experiencia", "solicitacao", "beleza"]
)
def test_parece_feminino(palavra: str) -> None:
    assert parece_feminino(palavra)


@pytest.mark.parametrize("palavra", ["cao", "sao", "pe", "livro", "problema", "carro", "irmao"])
def test_nao_parece_feminino(palavra: str) -> None:
    assert not parece_feminino(palavra)


@pytest.mark.parametrize("palavra", ["vamos", "ficamos", "temos", "fizemos", "precisamos"])
def test_parece_verbo_nos(palavra: str) -> None:
    assert parece_verbo_nos(palavra)


@pytest.mark.parametrize("palavra", ["termos", "ramos", "deu", "casa"])
def test_nao_parece_verbo_nos(palavra: str) -> None:
    assert not parece_verbo_nos(palavra)
