"""Toast: a confirmação silenciosa de "deu certo".

Regra número um: **não roubar o foco**. O usuário acabou de corrigir um texto
e o cursor dele está no meio de uma frase no Word. Uma janela que ativa aqui
tira o caret do lugar e faz a próxima letra digitada sumir. Por isso o toast
é ``overrideredirect`` + ``-topmost`` + ``WS_EX_NOACTIVATE``, e nunca chama
``focus_force``.

Visualmente é uma cápsula de uma linha só, no canto inferior direito, na cor
de ``superficie`` — o toast é um cartão flutuando sobre o desktop, não um
pedaço da página cinza do aplicativo. A cápsula é recortada pelo compositor do
Windows (``moldar_capsula``), que é também quem dá a sombra: desenhar o borrão
aqui exigiria saber o que está atrás da janela, e atrás dela está o desktop
do usuário.
"""

from __future__ import annotations

import tkinter as tk
import weakref

from . import (
    Estilo,
    area_util_do_cursor,
    impedir_roubo_de_foco,
    moldar_capsula,
)

#: Distância entre a cápsula e o canto da área útil, em pixels de layout.
_MARGEM = 28
#: Corpo da mensagem. O mesmo 13 do resto do aplicativo: o toast é a única
#: janela que aparece sem ser pedida e não pode gritar mais alto que as outras.
_TAMANHO_TEXTO = 13
_ALFA_MAXIMO = 0.97
_PASSOS_FADE = 14
_INTERVALO_FADE_MS = 22
_INTERVALO_ENTRADA_MS = 12

#: Espaço interno da cápsula, em pixels de layout. O horizontal é bem maior
#: que o vertical de propósito: numa cápsula, o que sobra nas pontas é comido
#: pela curva, e sem isso o texto encosta no arredondado.
_PADDING_X = 24
_PADDING_Y = 13

#: Um toast por ``Tk`` root. Um novo substitui o anterior em vez de empilhar
#: janelas no mesmo canto. Weak para não segurar o root vivo no shutdown.
_ATIVOS: weakref.WeakKeyDictionary[tk.Misc, _Toast] = weakref.WeakKeyDictionary()

#: Preferência de tema usada pelos próximos toasts ("claro"/"escuro"/"sistema").
_TEMA = "sistema"


def definir_tema(preferencia: str) -> None:
    """Alinha o toast ao ``config.tema``. Vale a partir do próximo toast."""
    global _TEMA
    _TEMA = preferencia or "sistema"


class _Toast:
    """Uma janelinha efêmera. Sempre usada através de :func:`mostrar_toast`."""

    def __init__(self, raiz: tk.Tk, mensagem: str, duracao_ms: int) -> None:
        self._raiz = raiz
        self._duracao_ms = duracao_ms
        self._agendado: str | None = None
        self._morto = False

        estilo = Estilo(raiz, _TEMA)
        tema = estilo.tema
        px = estilo.px
        self._margem = px(_MARGEM)

        self._janela = janela = tk.Toplevel(raiz)
        janela.withdraw()
        janela.overrideredirect(True)
        janela.attributes("-topmost", True)
        janela.attributes("-alpha", 0.0)
        janela.configure(bg=tema.superficie)

        corpo = tk.Frame(janela, bg=tema.superficie, bd=0, highlightthickness=0)
        corpo.pack(fill="both", expand=True, padx=px(_PADDING_X), pady=px(_PADDING_Y))
        tk.Label(
            corpo,
            text=mensagem,
            font=estilo.fonte(_TAMANHO_TEXTO),
            bg=tema.superficie,
            fg=tema.texto,
            justify="left",
        ).pack()

        janela.update_idletasks()
        impedir_roubo_de_foco(janela)
        self._posicionar()
        janela.deiconify()
        janela.lift()
        # Depois do deiconify: a região precisa do tamanho já aplicado.
        moldar_capsula(janela)
        self._entrar(0)

    def _posicionar(self) -> None:
        janela = self._janela
        largura = janela.winfo_reqwidth()
        altura = janela.winfo_reqheight()
        ax, ay, alargura, aaltura = area_util_do_cursor(self._raiz)
        x = ax + alargura - largura - self._margem
        y = ay + aaltura - altura - self._margem
        janela.geometry(f"{largura}x{altura}+{x}+{y}")

    def _entrar(self, passo: int) -> None:
        if self._morto:
            return
        alfa = _ALFA_MAXIMO * min(1.0, (passo + 1) / 6)
        self._janela.attributes("-alpha", alfa)
        if passo + 1 < 6:
            self._agendado = self._raiz.after(
                _INTERVALO_ENTRADA_MS, self._entrar, passo + 1
            )
        else:
            self._agendado = self._raiz.after(self._duracao_ms, self._sair, 0)

    def _sair(self, passo: int) -> None:
        if self._morto:
            return
        alfa = _ALFA_MAXIMO * (1 - (passo + 1) / _PASSOS_FADE)
        if alfa <= 0.01:
            self.destruir()
            return
        self._janela.attributes("-alpha", alfa)
        self._agendado = self._raiz.after(_INTERVALO_FADE_MS, self._sair, passo + 1)

    def destruir(self) -> None:
        if self._morto:
            return
        self._morto = True
        if self._agendado is not None:
            try:
                self._raiz.after_cancel(self._agendado)
            except (tk.TclError, ValueError):
                pass
            self._agendado = None
        try:
            self._janela.destroy()
        except tk.TclError:
            pass


def mostrar_toast(root: tk.Tk, mensagem: str, duracao_ms: int = 1600) -> None:
    """Mostra uma notificação discreta no canto inferior direito.

    Some sozinha com fade após ``duracao_ms``. Não pode ser clicada nem
    focada. Chamar de novo antes do fim substitui o toast anterior, para não
    empilhar janelas no mesmo canto.

    Precisa rodar na thread do tkinter. Vindo de outra thread, use
    ``root.after(0, lambda: mostrar_toast(root, msg))``.
    """
    anterior = _ATIVOS.pop(root, None)
    if anterior is not None:
        anterior.destruir()
    _ATIVOS[root] = _Toast(root, mensagem, duracao_ms)


def fechar_toasts(root: tk.Tk) -> None:
    """Mata o toast pendente (usado ao encerrar o app)."""
    atual = _ATIVOS.pop(root, None)
    if atual is not None:
        atual.destruir()


__all__ = ["definir_tema", "fechar_toasts", "mostrar_toast"]
