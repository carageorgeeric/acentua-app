"""Selecionar a palavra que o usuário acabou de digitar, sem ele selecionar nada.

O fluxo normal do Acentua exige seleção prévia: o usuário marca o texto e
aperta o atalho. Aqui a mão nunca sai do teclado — ele digita ``coracao``,
aperta o atalho e a palavra vira ``coração``.

A mecânica é injetar ``Ctrl+Shift+Esquerda`` (estende a seleção até o começo
da palavra anterior) e descobrir o que ficou selecionado com
:func:`~corretor.sistema.area_transferencia.ler_selecao`. A seleção fica
**ativa** de propósito, para quem chamou colar por cima com
``substituir_selecao``.

O que foi MEDIDO no Notepad do Windows 11 (seleção lida direto do controle
``RichEditD2DPT`` com ``EM_GETSEL``, não pelo clipboard):

===========================  ==================================  ============
documento (``|`` = cursor)   o que Ctrl+Shift+Esquerda seleciona  extensões
===========================  ==================================  ============
``...o coracao|``            ``coracao``                          1
``...o coracao |``           ``coracao `` (com o espaço)          1
``...o coracao.|``           ``.`` — **só a pontuação**            2
``...o coracao,|``           ``,`` — **só a pontuação**            2
``coracao\\n|``               ``\\r\\n`` — só a quebra               2
``|`` (documento vazio)      nada; ``ler_selecao`` devolve None   1
===========================  ==================================  ============

As duas linhas de pontuação são o motivo de este módulo existir em vez de uma
única tecla injetada. Uma extensão só devolveria ``.`` para ``coracao.|``, e
colar a correção por cima produziria ``coracaocoração.`` — foi exatamente o
que aconteceu na primeira medição. Por isso :func:`selecionar_palavra_anterior`
estende de novo enquanto a seleção não tiver **nenhum caractere alfanumérico**
(ver :func:`_precisa_estender`), no máximo mais duas vezes.

Duas medições que sustentam o resto do desenho:

* ``ler_selecao()`` **preserva a seleção**. O ``Ctrl+C`` dela não colapsa
  nada: o ``EM_GETSEL`` devolveu o mesmo intervalo antes e depois em todos os
  sete casos medidos. Dá para ler e colar por cima em seguida.
* A **Seta Direita colapsa** a seleção para a ponta direita — ``(23, 30)``
  virou ``(30, 30)``, o cursor exatamente onde estava antes do atalho. Mas
  quando **não** há seleção ela anda um caractere (``(0, 0)`` virou
  ``(1, 1)``). Daí :func:`desfazer_selecao` só ser chamada quando sabemos que
  há seleção viva.
"""

from __future__ import annotations

import sys

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("corretor.sistema.selecao depende do user32 (Windows).")

from . import area_transferencia, teclado

#: Quantas vezes reestender além da primeira, quando a seleção veio sem nada
#: alfanumérico. Duas cobre ``coracao.|`` (pontuação) e ``coracao\n|``
#: (quebra de linha). Mais que isso começaria a engolir a palavra ANTERIOR à
#: que o usuário quis corrigir.
_MAXIMO_DE_EXTENSOES_EXTRA = 2


def _precisa_estender(selecionado: str) -> bool:
    """A seleção é pura pontuação/espaço e não dá para corrigir nada nela?

    Lógica pura, sem Win32 — é o que decide se vale gastar mais um par
    injeção+leitura. ``coracao`` e ``2024`` param aqui; ``.``, ``, ``,
    ``\\r\\n`` e ``...`` pedem outra extensão.

    Dígitos contam como conteúdo de propósito. Se o usuário acabou de digitar
    ``2024``, estender de novo pegaria a palavra anterior junto e quem chamou
    colaria a correção por cima de um trecho maior do que devia.
    """
    return not any(caractere.isalnum() for caractere in selecionado)


def _estender_selecao() -> None:
    """Injeta um ``Ctrl+Shift+Esquerda`` limpo na janela em foco.

    Solta os modificadores antes: o usuário ainda está com Ctrl+Alt embaixo
    do dedo quando o atalho dispara, e sem soltar isto viraria
    ``Ctrl+Alt+Shift+Esquerda`` — que em muitos apps é trocar de layout de
    teclado, não selecionar.
    """
    with teclado.injetando():
        teclado.soltar_modificadores()
        teclado.enviar_combinacao(teclado.VK_CONTROL, teclado.VK_SHIFT, teclado.VK_LEFT)


def desfazer_selecao() -> None:
    """Colapsa a seleção de volta para o fim, deixando o cursor onde estava.

    Chame isto sempre que :func:`selecionar_palavra_anterior` devolveu texto e
    você **não** vai colar por cima — palavra já correta, correção idêntica,
    usuário cancelou. Sem isto o usuário fica com uma seleção que não pediu, e
    o próximo caractere que ele digitar apaga a palavra inteira.

    Medido no Notepad: com a seleção ``(23, 30)`` ativa, a Seta Direita levou
    para ``(30, 30)`` — a ponta direita, exatamente o ponto em que o cursor
    estava antes do atalho. Digitar um ``x`` logo depois produziu
    ``...o coracaox``, com a palavra intacta.

    Não chame sem seleção viva: aí a Seta Direita **anda** um caractere
    (medido: ``(0, 0)`` virou ``(1, 1)``). Em fim de documento é inofensiva,
    no meio do texto move o cursor do usuário.

    Propaga :exc:`~corretor.sistema.teclado.FalhaAoEnviarTeclas` se o Windows
    bloquear a injeção (janela elevada em foco).
    """
    with teclado.injetando():
        teclado.soltar_modificadores()
        teclado.enviar_combinacao(teclado.VK_RIGHT)


def _ir_para_o_fim_da_palavra() -> None:
    """Leva o caret para depois da palavra que ele está encostando.

    ``Ctrl+Direita`` pula para o começo da próxima palavra. Partindo de
    ``cora|cao mais`` isso deixa o caret em ``coracao |mais``, e aí a seleção
    para trás pega ``coracao`` inteiro — que é o que a pessoa quis dizer com
    "a palavra em que eu estou". No fim do texto a tecla não anda nada, então
    o caso de quem acabou de digitar (``coracao|``) continua idêntico.
    """
    with teclado.injetando():
        teclado.soltar_modificadores()
        teclado.enviar_combinacao(teclado.VK_CONTROL, teclado.VK_RIGHT)


def selecionar_palavra_do_caret(timeout: float = 0.6) -> str | None:
    """Seleciona a palavra que o caret está encostando, de qualquer lado.

    É a função que o atalho de corrigir-enquanto-digita usa. Diferente de
    :func:`selecionar_palavra_anterior`, que exige o caret logo depois da
    palavra, esta acerta o alvo em todas as posições que alguém usa de verdade:

    ==================  ==========================================
    Caret               Palavra escolhida
    ==================  ==========================================
    ``coracao|``        ``coracao`` — acabou de digitar
    ``cora|cao``        ``coracao`` — parou no meio
    ``|coracao``        ``coracao`` — colado antes
    ``coracao |``       ``coracao`` — já digitou o espaço
    ``arrumar o |``     ``o`` — caret solto, pega a anterior
    ==================  ==========================================

    Depois da correção o caret fica no fim da palavra corrigida, que é onde
    quem estava digitando quer continuar.
    """
    _ir_para_o_fim_da_palavra()
    return selecionar_palavra_anterior(timeout)


def selecionar_palavra_anterior(timeout: float = 0.6) -> str | None:
    """Seleciona a palavra imediatamente antes do caret e devolve o texto.

    Deixa a seleção **ATIVA** no app de destino, para quem chamou poder colar
    por cima com
    :func:`~corretor.sistema.area_transferencia.substituir_selecao`. Devolve
    ``None`` se não havia palavra — e nesse caso não deixa seleção nenhuma
    para trás.

    Devolve o texto **exatamente** como veio do app, sem aparar nada. Quem
    chamou precisa recolocar o que não for a palavra:

    * ``coracao `` (caso 2) — o espaço final tem que sobreviver à correção,
      senão as palavras grudam.
    * ``coracao.`` (caso 3) — a pontuação idem.
    * ``coracao\\r\\n`` (caso 4b, cursor no começo de uma linha nova) — a quebra
      idem, e esta é a mais perigosa: quem normalizar espaços em branco antes
      de colar junta as duas linhas do usuário.

    ``CorretorOffline.corrigir`` já devolve os três intactos (conferido:
    ``'coracao.'`` vira ``'coração.'``, ``'coracao\\r\\n'`` vira
    ``'coração\\r\\n'``), então basta colar ``resultado.texto`` por cima. O
    aviso vale para qualquer outro backend que venha depois.

    ``timeout`` é o orçamento de cada leitura de clipboard, não o total. O
    caso da pontuação faz duas leituras e leva o dobro.

    Propaga :exc:`~corretor.sistema.teclado.FalhaAoEnviarTeclas` quando o
    Windows recusa a injeção — janela elevada em foco (UIPI). Engolir viraria
    um atalho que não faz nada e não explica por quê.
    """
    _estender_selecao()
    selecionado = area_transferencia.ler_selecao(timeout)

    # Nada mudou no clipboard. Quase sempre significa cursor no início do
    # documento, sem nada à esquerda para selecionar — e aí não há seleção
    # para desfazer. Mas há um caso em que HÁ seleção viva e mesmo assim o
    # Ctrl+C não copia: terminais, onde Ctrl+C é interromper, não copiar.
    # Deixar essa seleção de pé faria a próxima tecla do usuário apagar a
    # palavra, então colapsamos. O preço quando realmente não havia seleção é
    # o cursor andar um caractere no início do documento.
    if selecionado is None:
        desfazer_selecao()
        return None

    for _ in range(_MAXIMO_DE_EXTENSOES_EXTRA):
        if not _precisa_estender(selecionado):
            break
        _estender_selecao()
        maior = area_transferencia.ler_selecao(timeout)
        if maior is None:
            # A seleção agora é MAIOR do que o texto que temos em mãos, e não
            # sabemos por quanto. Devolver o valor antigo faria quem chamou
            # colar uma correção curta por cima de um trecho longo, comendo
            # texto do usuário. Desistimos inteiro.
            desfazer_selecao()
            return None
        selecionado = maior

    return selecionado


__all__ = [
    "desfazer_selecao",
    "selecionar_palavra_anterior",
    "selecionar_palavra_do_caret",
]
