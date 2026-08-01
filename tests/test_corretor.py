"""Testes do motor de correção, com frases reais de português brasileiro."""

from __future__ import annotations

import time

import pytest

from corretor.nucleo.corretor import CorretorOffline
from corretor.nucleo.dicionario import Dicionario
from corretor.tipos import Resultado, Sugestao


@pytest.fixture(scope="module")
def corretor() -> CorretorOffline:
    return CorretorOffline(Dicionario.carregar())


class PreferenciasFalsas:
    """Implementação mínima de `FonteDePreferencias` para os testes."""

    def __init__(self, memoria: dict[str, str] | None = None) -> None:
        self.memoria = memoria or {}

    def preferida(self, chave: str) -> str | None:
        return self.memoria.get(chave)

    def registrar(self, chave: str, escolha: str) -> None:
        self.memoria[chave] = escolha


# --- frases completas -------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (
            "nao consigo acentuar entao uso o corretor",
            "não consigo acentuar então uso o corretor",
        ),
        ("a licao de casa e dificil", "a lição de casa é difícil"),
        ("vou tomar cafe com pao e manteiga", "vou tomar café com pão e manteiga"),
        ("Voce e o Joao vao para o litoral", "Você e o João vão para o litoral"),
        ("eu e a Maria fomos", "eu e a Maria fomos"),
        ("isso e bom", "isso é bom"),
        ("voce e muito legal", "você é muito legal"),
        ("minha mae fez um bolo", "minha mãe fez um bolo"),
        ("nao sei se voce ja viu a informacao", "não sei se você já viu a informação"),
        ("as vezes eu esqueco o acento", "às vezes eu esqueço o acento"),
        ("o pais esta em crise", "o país está em crise"),
        ("meus pais moram no interior", "meus pais moram no interior"),
        ("meu avo tinha noventa anos", "meu avô tinha noventa anos"),
        ("minha avo fazia bolo", "minha avó fazia bolo"),
        ("eu nao sabia disso", "eu não sabia disso"),
        ("tenho uma duvida sobre o codigo", "tenho uma dúvida sobre o código"),
        ("ele duvida de tudo", "ele duvida de tudo"),
        ("na pratica isso nao funciona", "na prática isso não funciona"),
        ("ela pratica natacao todo dia", "ela pratica natação todo dia"),
        ("o publico aplaudiu de pe", "o público aplaudiu de pé"),
        ("eu publico no blog toda semana", "eu publico no blog toda semana"),
        ("esta semana esta corrida", "esta semana está corrida"),
        ("esta e a minha casa", "esta é a minha casa"),
        ("a comida esta boa", "a comida está boa"),
        ("nao da pra fazer isso hoje", "não dá pra fazer isso hoje"),
        ("a casa da minha irma e grande", "a casa da minha irmã é grande"),
        ("vou a escola de manha", "vou à escola de manhã"),
        ("vou a pe ate a padaria", "vou a pé até a padaria"),
        ("devido a chuva o jogo foi adiado", "devido à chuva o jogo foi adiado"),
        ("nos vamos comecar amanha", "nós vamos começar amanhã"),
        ("ele nos deu um presente", "ele nos deu um presente"),
        ("o coracao dele bateu mais forte", "o coração dele bateu mais forte"),
        ("qual e o numero do seu telefone", "qual é o número do seu telefone"),
        ("a experiencia foi otima", "a experiência foi ótima"),
        ("estamos aqui ha tres anos", "estamos aqui há três anos"),
        ("nao e possivel fazer isso agora", "não é possível fazer isso agora"),
        ("a familia toda esta reunida", "a família toda está reunida"),
        ("ninguem sabe a resposta", "ninguém sabe a resposta"),
        ("estas coisas nao me agradam", "estas coisas não me agradam"),
        ("o pai e a mae chegaram juntos", "o pai e a mãe chegaram juntos"),
        ("a proxima reuniao sera na segunda", "a próxima reunião será na segunda"),
        ("bom dia, tudo bem com voce?", "bom dia, tudo bem com você?"),
    ],
)
def test_frase_completa(corretor: CorretorOffline, entrada: str, esperado: str) -> None:
    assert corretor.corrigir(entrada).texto == esperado


def test_conjuncao_nao_vira_verbo(corretor: CorretorOffline) -> None:
    """O `e` de 'pao e manteiga' liga dois substantivos e tem que ficar quieto."""
    resultado = corretor.corrigir("vou tomar cafe com pao e manteiga")
    assert " e " in resultado.texto
    assert " é " not in resultado.texto


# --- caixa ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("NAO", "NÃO"),
        ("Nao", "Não"),
        ("Voce", "Você"),
        ("VOCE", "VOCÊ"),
        ("Entao ele disse NAO", "Então ele disse NÃO"),
        ("CORACAO", "CORAÇÃO"),
    ],
)
def test_preserva_caixa(corretor: CorretorOffline, entrada: str, esperado: str) -> None:
    assert corretor.corrigir(entrada).texto == esperado


# --- freios -----------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "acesse http://exemplo.com/pagina agora",
        "acesse https://nao.com.br/entao para ver",
        "escreva para maria@empresa.com.br hoje",
        "siga @joao_silva e #carnaval2024",
        "o arquivo licao.py esta na pasta",
        "rode src/corretor/nucleo/corretor.py",
        "veja C:\\Users\\nao\\entao.txt",
        "use std::vector no codigo",
        "a variavel nome_da_licao mudou",
    ],
)
def test_nao_toca_no_que_nao_e_palavra(corretor: CorretorOffline, texto: str) -> None:
    resultado = corretor.corrigir(texto)
    for token in texto.split():
        if any(c in token for c in "@/\\_:") or token.startswith("#"):
            assert token in resultado.texto


def test_palavra_ja_acentuada_fica_como_esta(corretor: CorretorOffline) -> None:
    """Quem digitou o acento escolheu; o motor não tem o que revisar."""
    for texto in ["você", "não", "está", "país", "avô", "avó", "é", "à", "só"]:
        assert corretor.corrigir(texto).texto == texto


def test_palavra_sem_grupo_nao_muda(corretor: CorretorOffline) -> None:
    assert corretor.corrigir("casa mesa livro carro").texto == "casa mesa livro carro"


def test_nao_faz_correcao_de_digitacao(corretor: CorretorOffline) -> None:
    """Erro de digitação é outro problema; aqui só se resolve acento."""
    assert corretor.corrigir("teclaod qwerrty").texto == "teclaod qwerrty"


def test_texto_vazio(corretor: CorretorOffline) -> None:
    resultado = corretor.corrigir("")
    assert resultado.texto == ""
    assert not resultado.houve_mudanca


# --- preservação do texto ---------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "nao\tsim\nnao",
        "  nao   entao  ",
        "nao... entao?! sim;",
        "linha um\r\nlinha dois",
        "emoji 🎉 e acento: cafe",
        'aspas "nao" e (entao)',
    ],
)
def test_espacos_e_pontuacao_sobrevivem(corretor: CorretorOffline, texto: str) -> None:
    saida = corretor.corrigir(texto).texto
    esqueleto_original = "".join(c for c in texto if not c.isalpha())
    esqueleto_novo = "".join(c for c in saida if not c.isalpha())
    assert esqueleto_original == esqueleto_novo


def test_idempotencia(corretor: CorretorOffline) -> None:
    textos = [
        "nao consigo acentuar entao uso o corretor",
        "a licao de casa e dificil",
        "vou tomar cafe com pao e manteiga",
        "as vezes o pais esta em crise, nao e?",
        "meu avo e minha avo moram la",
    ]
    for texto in textos:
        uma_vez = corretor.corrigir(texto).texto
        duas_vezes = corretor.corrigir(uma_vez).texto
        assert duas_vezes == uma_vez


def test_texto_ja_correto_entra_e_sai_igual(corretor: CorretorOffline) -> None:
    texto = "Não consigo acentuar, então uso o corretor. A lição de casa é difícil!"
    resultado = corretor.corrigir(texto)
    assert resultado.texto == texto
    assert not resultado.houve_mudanca


# --- alterações -------------------------------------------------------------


def test_alteracao_aponta_para_o_texto_original(corretor: CorretorOffline) -> None:
    texto = "eu nao sei"
    resultado = corretor.corrigir(texto)
    (alteracao,) = resultado.alteracoes
    assert alteracao.original == "nao"
    assert alteracao.corrigida == "não"
    assert texto[alteracao.inicio : alteracao.fim] == "nao"


def test_conta_as_alteracoes(corretor: CorretorOffline) -> None:
    resultado = corretor.corrigir("nao consigo acentuar entao uso o corretor")
    assert resultado.total == 2
    assert resultado.houve_mudanca


def test_alternativa_so_aparece_com_ambiguidade_real(corretor: CorretorOffline) -> None:
    ambigua = corretor.corrigir("isso e bom").alteracoes[0]
    assert ambigua.ambigua
    assert "e" in ambigua.alternativas

    tranquila = corretor.corrigir("eu nao sei").alteracoes[0]
    assert not tranquila.ambigua


def test_no_maximo_duas_alternativas(corretor: CorretorOffline) -> None:
    for alteracao in corretor.corrigir("o avo e a avo dela").alteracoes:
        assert len(alteracao.alternativas) <= 2


def test_alternativa_respeita_a_caixa(corretor: CorretorOffline) -> None:
    (alteracao,) = corretor.corrigir("Isso E bom").alteracoes
    assert alteracao.corrigida == "É"
    assert alteracao.alternativas == ("E",)


def test_confianca_entre_zero_e_um(corretor: CorretorOffline) -> None:
    resultado = corretor.corrigir("as vezes o pais esta em crise e isso e ruim")
    assert resultado.alteracoes
    for alteracao in resultado.alteracoes:
        assert 0.0 < alteracao.confianca <= 1.0


def test_confianca_alta_quando_a_grafia_e_unica(corretor: CorretorOffline) -> None:
    (alteracao,) = corretor.corrigir("nao").alteracoes
    assert alteracao.confianca == 1.0


def test_ambiguas_filtra_o_resultado(corretor: CorretorOffline) -> None:
    resultado = corretor.corrigir("nao e facil")
    assert all(a.ambigua for a in resultado.ambiguas)
    assert len(resultado.ambiguas) < resultado.total


# --- preferências do usuário ------------------------------------------------


def test_preferencia_do_usuario_ganha_da_frequencia() -> None:
    dicionario = Dicionario.carregar()
    padrao = CorretorOffline(dicionario)
    assert padrao.corrigir("minha avo").texto == "minha avó"

    teimoso = CorretorOffline(dicionario, PreferenciasFalsas({"avo": "avô"}))
    assert teimoso.corrigir("minha avo").texto == "minha avô"


def test_preferencia_do_usuario_ganha_do_contexto() -> None:
    dicionario = Dicionario.carregar()
    padrao = CorretorOffline(dicionario)
    assert padrao.corrigir("isso e bom").texto == "isso é bom"

    teimoso = CorretorOffline(dicionario, PreferenciasFalsas({"e": "e"}))
    assert teimoso.corrigir("isso e bom").texto == "isso e bom"


def test_preferencia_desconhecida_e_ignorada() -> None:
    corretor = CorretorOffline(
        Dicionario.carregar(), PreferenciasFalsas({"nao": "inexistente"})
    )
    assert corretor.corrigir("nao").texto == "não"


# --- compostas --------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("d'agua", "d'água"),
        ("nao-sei", "não-sei"),
        ("guarda-chuva", "guarda-chuva"),
        ("da-me a informacao", "dá-me a informação"),
    ],
)
def test_palavra_composta(corretor: CorretorOffline, entrada: str, esperado: str) -> None:
    assert corretor.corrigir(entrada).texto == esperado


# --- sugestões --------------------------------------------------------------


def test_sugestoes_ordenadas(corretor: CorretorOffline) -> None:
    sugestoes = corretor.sugestoes("avo")
    assert [s.palavra for s in sugestoes] == ["avó", "avô", "avo"]
    assert sugestoes[0].confianca >= sugestoes[1].confianca


def test_sugestoes_respeitam_o_limite(corretor: CorretorOffline) -> None:
    assert len(corretor.sugestoes("avo", limite=2)) == 2
    assert corretor.sugestoes("avo", limite=0) == []


def test_sugestoes_incluem_a_palavra_digitada(corretor: CorretorOffline) -> None:
    assert "esta" in [s.palavra for s in corretor.sugestoes("esta", limite=2)]
    assert "avo" in [s.palavra for s in corretor.sugestoes("avo", limite=2)]


def test_limite_de_uma_sugestao_devolve_so_a_melhor(corretor: CorretorOffline) -> None:
    """Com uma vaga só, a melhor grafia vale mais que repetir o que foi digitado."""
    assert [s.palavra for s in corretor.sugestoes("avo", limite=1)] == ["avó"]


def test_sugestoes_de_palavra_sem_grupo(corretor: CorretorOffline) -> None:
    assert corretor.sugestoes("casa") == [Sugestao("casa", 1.0)]


def test_sugestoes_usam_o_contexto(corretor: CorretorOffline) -> None:
    assert corretor.sugestoes("e", anterior="isso", seguinte="bom")[0].palavra == "é"
    assert corretor.sugestoes("e", anterior="pao", seguinte="queijo")[0].palavra == "e"


def test_sugestoes_preservam_a_caixa(corretor: CorretorOffline) -> None:
    assert corretor.sugestoes("Avo")[0].palavra == "Avó"


# --- desempenho -------------------------------------------------------------


def test_paragrafo_de_duzentas_palavras_em_menos_de_50ms(corretor: CorretorOffline) -> None:
    base = (
        "nao consigo acentuar entao uso o corretor porque a licao de casa e "
        "dificil e o cafe com pao e manteiga esta otimo hoje de manha "
    )
    texto = base * 10
    assert len(texto.split()) >= 200

    corretor.corrigir(texto)  # aquece o cache de regex do módulo
    inicio = time.perf_counter()
    resultado = corretor.corrigir(texto)
    decorrido = (time.perf_counter() - inicio) * 1000

    assert isinstance(resultado, Resultado)
    assert decorrido < 50, f"{decorrido:.1f} ms"
