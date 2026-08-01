"""Revisão de frase: o que ainda vale perguntar depois de corrigir tudo.

``CorretorOffline.corrigir`` já resolve o texto inteiro sozinho e marca quais
trocas ficaram em dúvida (``Resultado.ambiguas``). Este módulo transforma essa
dúvida numa pergunta que o popup sabe mostrar, e depois costura as respostas de
volta no texto.

Duas decisões sustentam o desenho:

1. **Nada é colado antes de perguntar.** A alternativa seria colar a correção
   automática e reescrever a cada escolha, o que empilha um Ctrl+Z por palavra
   e faz a tela piscar. Aqui o texto sai uma vez só, já com as respostas.
2. **A opção automática é sempre a primeira.** ``motor.sugestoes`` ordena por
   frequência e preferência, mas não sabe se a palavra abre frase — a correção
   sabe. Reordenar garante que apertar Enter três vezes dê exatamente o mesmo
   texto que sairia sem perguntar nada.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from corretor.nucleo.corretor import vizinhancas
from corretor.nucleo.normalizacao import tokenizar
from corretor.tipos import Duvida, MotorDeCorrecao, Resultado, Sugestao

__all__ = ["aplicar", "duvidas", "recorte", "total_de_mudancas"]

#: Quantos caracteres da frase mostrar de cada lado da palavra em dúvida. O
#: popup é uma tira estreita colada no cursor; passar disso vira parágrafo.
LARGURA_DO_RECORTE = 20

#: Teto de perguntas por correção.
#:
#: Existe porque `e`, `a`, `as` e `esta` são ambíguos quase sempre, e um
#: parágrafo grande produz uma dúvida a cada duas linhas. Responder onze
#: popups em fila é pior do que aceitar duas palavras erradas e arrumar
#: depois — a correção deixa de ser um atalho e vira um formulário. Seis
#: cobre inteira qualquer frase de tamanho normal; o que passar disso sai com
#: a grafia automática, exatamente como saía antes de existir a revisão.
#:
#: O corte é pelo COMEÇO do texto, não pelas de menor confiança: assim o
#: usuário sabe onde as perguntas param sem precisar adivinhar o critério.
MAX_DUVIDAS = 6

#: Espaço em branco de qualquer tipo vira um espaço só no recorte: o cabeçalho
#: do popup é uma linha, e um ``\n`` no meio dela abriria um buraco.
_ESPACOS = re.compile(r"\s+")


def recorte(texto: str, inicio: int, fim: int, largura: int = LARGURA_DO_RECORTE) -> tuple[str, str]:
    """Os trechos da frase antes e depois de ``texto[inicio:fim]``.

    Corta em espaço, não no meio de uma palavra, e marca o corte com ``…`` —
    metade de uma palavra no cabeçalho faria o usuário reler para entender.
    """
    antes = _ESPACOS.sub(" ", texto[:inicio])
    depois = _ESPACOS.sub(" ", texto[fim:])

    if len(antes) > largura:
        cauda = antes[-largura:]
        espaco = cauda.find(" ")
        antes = "… " + (cauda[espaco + 1 :] if espaco != -1 else cauda)
    if len(depois) > largura:
        cabeca = depois[:largura]
        espaco = cabeca.rfind(" ")
        depois = (cabeca[:espaco] if espaco > 0 else cabeca) + " …"

    return antes, depois


def duvidas(
    texto: str,
    resultado: Resultado,
    motor: MotorDeCorrecao,
    limite: int = 3,
    maximo: int = MAX_DUVIDAS,
) -> tuple[Duvida, ...]:
    """As perguntas a fazer sobre ``resultado``, na ordem em que aparecem.

    Só vira pergunta a troca que o motor marcou como ambígua E que tem mais de
    uma grafia para oferecer. Perguntar com uma opção só não é escolha, é
    interrupção. ``maximo`` corta a fila — veja :data:`MAX_DUVIDAS`.
    """
    if not resultado.ambiguas or limite <= 1 or maximo <= 0:
        return ()

    vizinhos = _por_posicao(texto)
    # O contexto vem do texto JÁ CORRIGIDO, não do que o usuário digitou. O
    # popup é uma prévia de como a frase vai sair: mostrar "o cafe da manha"
    # embaixo de uma escolha entre `é` e `e` faria o usuário decidir olhando
    # um texto que não vai existir.
    spans = _spans_corrigidos(resultado)
    perguntas: list[Duvida] = []

    for indice, alteracao in enumerate(resultado.alteracoes):
        if not alteracao.ambigua:
            continue
        anterior, seguinte = vizinhos.get(alteracao.inicio, (None, None))
        opcoes = _opcoes(motor, alteracao.original, alteracao.corrigida, anterior, seguinte, limite)
        if len(opcoes) < 2:
            continue
        antes, depois = recorte(resultado.texto, *spans[indice])
        perguntas.append(Duvida(indice=indice, antes=antes, depois=depois, sugestoes=opcoes))
        if len(perguntas) == maximo:
            break

    return tuple(perguntas)


def aplicar(texto: str, resultado: Resultado, escolhas: Mapping[int, str]) -> str:
    """Reconstrói o texto trocando cada alteração pela grafia escolhida.

    Parte do texto ORIGINAL, não de ``resultado.texto``: os índices de
    ``Alteracao`` são posições no original, e é neles que dá para recortar sem
    recontar caractere nenhum. As alterações vêm em ordem crescente e não se
    sobrepõem — são tokens distintos —, então uma passada basta.

    Uma chave de ``escolhas`` fora do intervalo é ignorada em silêncio: quem
    responde é a interface, e um popup fechado no meio não pode derrubar a
    colagem.
    """
    pedacos: list[str] = []
    posicao = 0
    for indice, alteracao in enumerate(resultado.alteracoes):
        pedacos.append(texto[posicao : alteracao.inicio])
        pedacos.append(escolhas.get(indice, alteracao.corrigida))
        posicao = alteracao.fim
    pedacos.append(texto[posicao:])
    return "".join(pedacos)


def total_de_mudancas(resultado: Resultado, escolhas: Mapping[int, str]) -> int:
    """Quantas palavras realmente saem diferentes do que o usuário digitou.

    Não é ``resultado.total``: se o usuário olhou o popup e escolheu de volta a
    grafia que ele mesmo tinha escrito, aquela palavra não mudou, e contá-la
    faria o aviso mentir.
    """
    return sum(
        1
        for indice, alteracao in enumerate(resultado.alteracoes)
        if escolhas.get(indice, alteracao.corrigida) != alteracao.original
    )


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------


def _spans_corrigidos(resultado: Resultado) -> list[tuple[int, int]]:
    """Onde cada alteração caiu dentro de ``resultado.texto``.

    ``Alteracao`` guarda posição no texto original, e a grafia corrigida quase
    sempre tem outro tamanho (``nao`` -> ``não`` cresce zero, ``as`` -> ``às``
    também, mas ``d'agua`` -> ``d'água`` desloca tudo à frente). Acumular a
    diferença de tamanho é suficiente porque as alterações vêm em ordem e não
    se sobrepõem.
    """
    spans: list[tuple[int, int]] = []
    deslocamento = 0
    for alteracao in resultado.alteracoes:
        inicio = alteracao.inicio + deslocamento
        fim = inicio + len(alteracao.corrigida)
        spans.append((inicio, fim))
        deslocamento += len(alteracao.corrigida) - (alteracao.fim - alteracao.inicio)
    return spans


def _por_posicao(texto: str) -> dict[int, tuple[str | None, str | None]]:
    """Vizinhos de cada palavra corrigível, indexados pelo início dela.

    ``Alteracao`` guarda posição no texto, e não índice de token, então este é
    o formato que serve para reencontrar a vizinhança de uma troca.
    """
    tokens = tokenizar(texto)
    return {
        tokens[i].inicio: (anterior, seguinte)
        for i, (anterior, seguinte, _abre_frase) in vizinhancas(tokens).items()
    }


def _opcoes(
    motor: MotorDeCorrecao,
    original: str,
    automatica: str,
    anterior: str | None,
    seguinte: str | None,
    limite: int,
) -> tuple[Sugestao, ...]:
    """Grafias possíveis com a automática na frente e sem repetição."""
    sugestoes = motor.sugestoes(original, anterior, seguinte, limite)
    palavras = [s.palavra for s in sugestoes]

    if automatica in palavras:
        posicao = palavras.index(automatica)
        sugestoes = [sugestoes[posicao]] + sugestoes[:posicao] + sugestoes[posicao + 1 :]
    else:
        # O motor decidiu por um caminho que ``sugestoes`` não reproduz (regra
        # de início de frase, palavra composta). A decisão da correção manda.
        sugestoes = [Sugestao(automatica, 1.0)] + sugestoes[: limite - 1]

    return tuple(_sem_repetidas(sugestoes))


def _sem_repetidas(sugestoes: Sequence[Sugestao]) -> list[Sugestao]:
    vistas: set[str] = set()
    unicas: list[Sugestao] = []
    for sugestao in sugestoes:
        if sugestao.palavra not in vistas:
            vistas.add(sugestao.palavra)
            unicas.append(sugestao)
    return unicas
