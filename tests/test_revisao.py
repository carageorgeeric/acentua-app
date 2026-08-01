"""Testes da revisão de frase: montar as perguntas e costurar as respostas.

Tudo aqui é lógica pura — nenhuma janela, nenhum clipboard. O caminho com
popup de verdade está em ``test_interface.py``, marcado com ``gui``.
"""

from __future__ import annotations

import pytest

from corretor.nucleo import revisao
from corretor.nucleo.corretor import CorretorOffline
from corretor.nucleo.dicionario import Dicionario
from corretor.tipos import Alteracao, Resultado


@pytest.fixture(scope="module")
def corretor() -> CorretorOffline:
    return CorretorOffline(Dicionario.carregar())


# ---------------------------------------------------------------------------
# Recorte da frase
# ---------------------------------------------------------------------------


def test_recorte_devolve_os_dois_lados() -> None:
    texto = "pao e queijo"
    antes, depois = revisao.recorte(texto, 4, 5)
    assert antes == "pao "
    assert depois == " queijo"


def test_recorte_corta_em_espaco_e_marca_com_reticencias() -> None:
    texto = "uma frase bem comprida antes da palavra e outra bem comprida depois"
    antes, depois = revisao.recorte(texto, 39, 40, largura=12)
    assert antes.startswith("…")
    assert depois.endswith("…")
    # Nenhum pedaço de palavra pela metade nas pontas do recorte.
    assert antes.lstrip("… ").split(" ")[0] in texto.split()
    assert depois.rstrip("… ").split(" ")[-1] in texto.split()


def test_recorte_achata_quebras_de_linha() -> None:
    """O cabeçalho do popup é UMA linha; um \\n abriria um buraco nela."""
    antes, depois = revisao.recorte("linha um\ne\nlinha dois", 9, 10)
    assert "\n" not in antes and "\n" not in depois
    assert antes == "linha um "


def test_recorte_de_palavra_isolada_nao_inventa_contexto() -> None:
    assert revisao.recorte("e", 0, 1) == ("", "")


# ---------------------------------------------------------------------------
# Montagem das perguntas
# ---------------------------------------------------------------------------


def test_pergunta_so_sobre_as_ambiguas(corretor: CorretorOffline) -> None:
    texto = "isso e bom e o coracao dela"
    resultado = corretor.corrigir(texto)
    duvidas = revisao.duvidas(texto, resultado, corretor)

    assert duvidas, "'e' vira 'é' com alternativa; tem que virar pergunta"
    indices = {d.indice for d in duvidas}
    ambiguos = {i for i, a in enumerate(resultado.alteracoes) if a.ambigua}
    assert indices <= ambiguos
    # `coracao` -> `coração` não tem concorrente e não pode virar pergunta.
    corrigidas = {resultado.alteracoes[i].corrigida for i in indices}
    assert "coração" not in corrigidas


def test_a_primeira_opcao_e_sempre_a_automatica(corretor: CorretorOffline) -> None:
    """Enter em tudo tem que dar o mesmo texto de quando não se pergunta nada."""
    texto = "isso e bom, mas nao e facil"
    resultado = corretor.corrigir(texto)
    duvidas = revisao.duvidas(texto, resultado, corretor)

    for duvida in duvidas:
        assert duvida.automatica == resultado.alteracoes[duvida.indice].corrigida


def test_pergunta_sempre_tem_pelo_menos_duas_opcoes(corretor: CorretorOffline) -> None:
    """Uma opção só não é escolha, é interrupção."""
    texto = "isso e bom e voce sabia disso"
    for duvida in revisao.duvidas(texto, corretor.corrigir(texto), corretor):
        assert len(duvida.sugestoes) >= 2
        palavras = [s.palavra for s in duvida.sugestoes]
        assert len(palavras) == len(set(palavras)), "opção repetida no popup"


def test_contexto_da_pergunta_ja_vem_acentuado(corretor: CorretorOffline) -> None:
    """O popup é prévia do resultado: decidir olhando o texto cru confunde."""
    texto = "o cafe da manha e otimo"
    resultado = corretor.corrigir(texto)
    duvida = revisao.duvidas(texto, resultado, corretor)[0]

    assert duvida.antes == "o café da manhã "
    assert duvida.depois == " ótimo"
    # E o recorte tem que recompor exatamente a frase corrigida.
    assert duvida.antes + duvida.automatica + duvida.depois == resultado.texto


def test_contexto_acerta_a_posicao_depois_de_palavra_que_cresceu(
    corretor: CorretorOffline,
) -> None:
    """Uma correção com tamanho diferente desloca tudo o que vem à frente."""
    texto = "d'agua fresca isso e bom"
    resultado = corretor.corrigir(texto)
    duvidas = revisao.duvidas(texto, resultado, corretor)
    assert duvidas
    for duvida in duvidas:
        assert duvida.antes + duvida.automatica + duvida.depois == resultado.texto


def test_sem_ambiguidade_nao_pergunta_nada(corretor: CorretorOffline) -> None:
    texto = "o coracao e a emocao"
    resultado = Resultado(
        texto,
        tuple(a for a in corretor.corrigir(texto).alteracoes if not a.ambigua),
    )
    assert revisao.duvidas(texto, resultado, corretor) == ()


def test_limite_de_uma_opcao_desliga_a_revisao(corretor: CorretorOffline) -> None:
    texto = "isso e bom"
    resultado = corretor.corrigir(texto)
    assert revisao.duvidas(texto, resultado, corretor, limite=1) == ()


def test_fila_tem_teto_e_corta_pelo_fim(corretor: CorretorOffline) -> None:
    """Um parágrafo cheio de `e`/`a` não pode virar onze popups em fila."""
    texto = (
        "isso e bom, mas nao e facil. vou a escola as vezes e ela esta la, "
        "e o pais e grande e a gente sabia disso e nao e pouco"
    )
    resultado = corretor.corrigir(texto)
    todas = revisao.duvidas(texto, resultado, corretor, maximo=99)
    assert len(todas) > revisao.MAX_DUVIDAS, "frase fraca para este teste"

    cortadas = revisao.duvidas(texto, resultado, corretor)
    assert len(cortadas) == revisao.MAX_DUVIDAS
    # As que sobraram são as primeiras do texto, na mesma ordem.
    assert [d.indice for d in cortadas] == [d.indice for d in todas[: revisao.MAX_DUVIDAS]]


def test_maximo_zero_desliga_a_revisao(corretor: CorretorOffline) -> None:
    texto = "isso e bom"
    assert revisao.duvidas(texto, corretor.corrigir(texto), corretor, maximo=0) == ()


# ---------------------------------------------------------------------------
# Aplicar as escolhas
# ---------------------------------------------------------------------------


def test_aplicar_sem_escolhas_reproduz_a_correcao(corretor: CorretorOffline) -> None:
    for texto in (
        "isso e bom",
        "o coracao dela nao e facil",
        "vou a escola as 8h",
        "veja https://exemplo.com.br e o arquivo dados.json",
        "linha um\nlinha dois com acao\n",
        "",
    ):
        resultado = corretor.corrigir(texto)
        assert revisao.aplicar(texto, resultado, {}) == resultado.texto


def test_aplicar_troca_so_a_palavra_escolhida(corretor: CorretorOffline) -> None:
    texto = "isso e bom"
    resultado = corretor.corrigir(texto)
    indice = next(i for i, a in enumerate(resultado.alteracoes) if a.original == "e")
    assert revisao.aplicar(texto, resultado, {indice: "e"}) == "isso e bom"


def test_aplicar_preserva_espacos_e_pontuacao() -> None:
    texto = "  ola,   voce  ta ai?  "
    resultado = Resultado(
        "  olá,   você  ta ai?  ",
        (
            Alteracao("ola", "olá", 2, 5),
            Alteracao("voce", "você", 9, 13),
        ),
    )
    assert revisao.aplicar(texto, resultado, {}) == "  olá,   você  ta ai?  "
    assert revisao.aplicar(texto, resultado, {1: "voce"}) == "  olá,   voce  ta ai?  "


def test_aplicar_ignora_indice_que_nao_existe() -> None:
    texto = "ola"
    resultado = Resultado("olá", (Alteracao("ola", "olá", 0, 3),))
    assert revisao.aplicar(texto, resultado, {7: "xxx"}) == "olá"


# ---------------------------------------------------------------------------
# Contagem para o aviso
# ---------------------------------------------------------------------------


def test_total_conta_o_que_realmente_mudou() -> None:
    resultado = Resultado(
        "olá você",
        (Alteracao("ola", "olá", 0, 3), Alteracao("voce", "você", 4, 8)),
    )
    assert revisao.total_de_mudancas(resultado, {}) == 2
    # Escolher de volta o que o usuário digitou tira a palavra da conta.
    assert revisao.total_de_mudancas(resultado, {1: "voce"}) == 1
    assert revisao.total_de_mudancas(resultado, {0: "ola", 1: "voce"}) == 0
