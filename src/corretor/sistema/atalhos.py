"""Atalhos globais (pynput) entregues na thread do tkinter.

O ``pynput`` escuta o teclado numa thread própria, com um hook de baixo nível
do Windows. Duas consequências mandam no desenho deste módulo:

1. O callback NÃO pode tocar em tkinter — widget criado fora da thread do
   ``mainloop`` trava ou corrompe o Tk.
2. O callback roda DENTRO do hook: enquanto ele não retorna, o teclado do
   sistema inteiro fica parado. E o Windows remove calado um hook de baixo
   nível que demore mais que ``LowLevelHooksTimeout`` (300 ms por padrão) —
   o atalho pararia de funcionar sem nenhum erro.

Por isso aqui NÃO se usa ``root.after`` a partir do hook. Parece a escolha
óbvia, mas ``after`` chamado de outra thread é marshalado pelo ``_tkinter``
e **bloqueia quem chamou** até a thread principal chegar no loop de eventos.
Se a thread principal estiver ocupada (injetando teclas, por exemplo), o hook
fica preso junto — exatamente o cenário do item 2.

O hook então só faz ``fila.put_nowait(acao)``, que nunca bloqueia, e a thread
do tkinter drena a fila periodicamente com ``after``.

A ARMADILHA DO Ctrl+Alt (leia antes de mexer)
---------------------------------------------
``HotKey.parse("<ctrl>+<alt>+c")`` monta o alvo com ``KeyCode.from_char('c')``.
Só que, com Ctrl e Alt pressionados, o Windows não consegue traduzir a tecla
para caractere e o listener entrega ``KeyCode(vk=67, char=None)``. Os dois
nunca casam, e o atalho simplesmente nunca dispara.

Pior: em teclado ABNT2, Ctrl+Alt se comporta como AltGr, e AltGr+C pode
produzir ``₢`` — outro caractere que também não casaria.

A forma em vk (``<ctrl>+<alt>+<67>``) casa nos dois cenários, porque a
igualdade de ``KeyCode`` cai na comparação por ``vk`` quando um dos lados tem
``char=None``. Por isso registramos SEMPRE as duas formas para a mesma ação —
e, como as duas podem casar no mesmo evento, o despachante tem antirrepique
(senão o texto seria colado em dobro).
"""

from __future__ import annotations

import ctypes
import queue
import sys
import time
import tkinter as tk
import traceback
from collections.abc import Callable

from pynput import keyboard

from . import teclado

#: Duas formas do mesmo atalho podem casar no mesmo evento; e teclas seguradas
#: repetem. Um disparo por vez a cada 300 ms é o que separa "corrigiu" de
#: "colou duas vezes".
JANELA_ANTIRREPIQUE = 0.3

#: Como cada modificador aparece na combinação e o nome que
#: ``teclado.modificadores_pressionados()`` usa.
_MODIFICADORES = {
    "<ctrl>": "ctrl",
    "<alt>": "alt",
    "<alt_gr>": "alt",
    "<shift>": "shift",
    "<cmd>": "win",
    "<super>": "win",
    "<win>": "win",
}

#: De quanto em quanto tempo a thread do tkinter olha a fila de atalhos.
#: 20 ms é imperceptível para quem apertou a tecla e não pesa em nada.
INTERVALO_DE_DRENAGEM_MS = 20


class AtalhoInvalido(ValueError):
    """A string da combinação não é um atalho que o pynput entenda.

    Formato esperado: ``"<ctrl>+<alt>+c"``. Modificadores entre ``<>``,
    teclas normais soltas, tudo separado por ``+``.
    """


_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_SYSKEYDOWN = 0x0104
_WM_SYSKEYUP = 0x0105


class _OuvinteDeAtalhos(keyboard.GlobalHotKeys):
    """``GlobalHotKeys`` com duas mudanças que o Acentua precisa.

    **1. Aceita tecla injetada.** O pynput descarta tudo que chega com
    ``LLKHF_INJECTED`` (veja o ``if not injected`` no
    ``GlobalHotKeys._on_press``). Teclado com camada de macro — justamente o
    público de teclado 68% —, AutoHotkey, RDP, Parsec e máquina virtual
    entregam a tecla como injetada, e o atalho não funcionaria em nenhum
    desses casos.

    **2. Engole (suprime) a tecla do atalho.** Sem isso o ``Ctrl+Alt+C`` chega
    também no app do usuário. Em layout ABNT2 o Ctrl+Alt age como AltGr e a
    combinação vira um caractere: o app substitui a seleção por essa letra —
    ou seja, destrói justamente o texto que íamos corrigir, antes de a gente
    conseguir lê-lo.

    ``alvos`` mapeia a virtual-key final de cada atalho para
    ``(modificadores exigidos, despachante)``. O despacho acontece aqui
    mesmo, porque ``suppress_event()`` levanta exceção e os callbacks normais
    do pynput não chegam a rodar.
    """

    def __init__(self, hotkeys, alvos, **kwargs) -> None:
        self._alvos = alvos
        self._keyups_a_engolir: set[int] = set()
        super().__init__(hotkeys, win32_event_filter=self._filtrar, **kwargs)

    def _on_press(self, key, injected: bool = False) -> None:  # noqa: ARG002
        for atalho in self._hotkeys:
            atalho.press(self.canonical(key))

    def _on_release(self, key, injected: bool = False) -> None:  # noqa: ARG002
        for atalho in self._hotkeys:
            atalho.release(self.canonical(key))

    def _filtrar(self, msg: int, data) -> bool:
        """Roda dentro do hook, antes de qualquer app ver a tecla.

        Devolver ``True`` deixa passar; ``suppress_event()`` engole de vez.
        """
        vk = int(data.vkCode)
        if (data.dwExtraInfo or 0) == teclado.MARCA_ACENTUA:
            return True  # tecla nossa: nunca engolir, ela É o trabalho

        if teclado.esta_injetando() and vk in teclado.VKS_MODIFICADORES:
            # O usuário soltando Ctrl/Alt no meio da nossa injeção quebraria
            # o Ctrl+V em um "v" solto. Ver teclado._INJETANDO.
            self.suppress_event()

        if msg in (_WM_KEYUP, _WM_SYSKEYUP):
            if vk in self._keyups_a_engolir:
                self._keyups_a_engolir.discard(vk)
                self.suppress_event()
            return True

        if msg not in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            return True

        alvo = self._alvos.get(vk)
        if alvo is None:
            return True
        exigidos, disparar = alvo
        # Sem modificador não engolimos nada: seria comer digitação normal.
        if not exigidos or not exigidos <= teclado.modificadores_pressionados():
            return True

        disparar()
        self._keyups_a_engolir.add(vk)
        self.suppress_event()
        return False


def _vk_do_caractere(tecla: str) -> int | None:
    """Virtual-key de um caractere solto, ou ``None`` se não houver."""
    if len(tecla) != 1:
        return None
    if tecla.isascii() and tecla.isalnum():
        return ord(tecla.upper())
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.VkKeyScanW.argtypes = (ctypes.c_wchar,)
        user32.VkKeyScanW.restype = ctypes.c_short
        resultado = user32.VkKeyScanW(tecla)
    except (OSError, ValueError):
        return None
    return None if resultado == -1 else resultado & 0xFF


def modificadores_exigidos(combinacao: str) -> frozenset[str]:
    """Modificadores que a combinação exige, em nomes de ``teclado``."""
    return frozenset(
        _MODIFICADORES[parte.strip().lower()]
        for parte in combinacao.split("+")
        if parte.strip().lower() in _MODIFICADORES
    )


def vk_final(combinacao: str) -> int | None:
    """Virtual-key da tecla não-modificadora do atalho.

    Aceita as três formas que aparecem numa combinação: caractere solto
    (``c``), nome do pynput (``<space>``, ``<f5>``) e vk cru (``<67>``).
    """
    ultima = combinacao.split("+")[-1].strip()
    if not ultima.startswith("<") or not ultima.endswith(">"):
        return _vk_do_caractere(ultima)
    interno = ultima[1:-1]
    if interno.isdigit():
        return int(interno)
    tecla = getattr(keyboard.Key, interno, None)
    if tecla is None:
        return None
    return getattr(tecla.value, "vk", None)


def variante_em_vk(combinacao: str) -> str | None:
    """``"<ctrl>+<alt>+c"`` -> ``"<ctrl>+<alt>+<67>"``.

    Devolve ``None`` quando não faz sentido: a tecla final já está em
    ``<...>`` (``<space>``, ``<f5>``) ou não tem virtual-key conhecida.
    """
    partes = [parte.strip() for parte in combinacao.split("+")]
    if len(partes) < 2:
        return None
    ultima = partes[-1]
    if ultima.startswith("<") and ultima.endswith(">"):
        return None
    codigo = _vk_do_caractere(ultima)
    if codigo is None:
        return None
    variante = "+".join([*partes[:-1], f"<{codigo}>"])
    return None if variante == combinacao else variante


class GerenciadorAtalhos:
    """Registra atalhos globais e chama as ações na thread da interface.

    Recebe o ``root`` do tkinter (nunca cria um) porque o despacho depende de
    ``root.after``.
    """

    def __init__(self, root: tk.Tk, *, aceitar_injetados: bool = True) -> None:
        self._raiz = root
        self._mapa: dict[str, Callable[[], None]] = {}
        self._ouvinte: keyboard.GlobalHotKeys | None = None
        self._ultimo_disparo: dict[str, float] = {}
        self._aceitar_injetados = aceitar_injetados
        self._fila: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._drenagem: str | None = None

    @property
    def ativo(self) -> bool:
        return self._ouvinte is not None

    @property
    def combinacoes(self) -> tuple[str, ...]:
        return tuple(self._mapa)

    def registrar(self, combinacao: str, acao: Callable[[], None]) -> None:
        """Adiciona (ou substitui) um atalho.

        Valida na hora do registro em vez de deixar o pynput falhar em
        silêncio quando o listener sobe — atalho que não funciona e não
        reclama é o pior modo de falha possível aqui.
        """
        self._validar(combinacao)
        self._mapa[combinacao] = acao
        if self.ativo:
            self._resubir()

    def remover(self, combinacao: str) -> None:
        if self._mapa.pop(combinacao, None) is not None and self.ativo:
            self._resubir()

    def recarregar(self, mapa: dict[str, Callable[[], None]]) -> None:
        """Troca todos os atalhos de uma vez (usado ao salvar configurações)."""
        for combinacao in mapa:
            self._validar(combinacao)
        self._mapa = dict(mapa)
        if self.ativo:
            self._resubir()

    def iniciar(self) -> None:
        """Sobe o listener global. Idempotente."""
        if self.ativo or not self._mapa:
            return
        despachantes = self._despachantes()
        if self._aceitar_injetados:
            self._ouvinte = _OuvinteDeAtalhos(despachantes, self._alvos())
        else:
            self._ouvinte = keyboard.GlobalHotKeys(despachantes)
        self._ouvinte.daemon = True
        self._ouvinte.start()
        self._agendar_drenagem()

    def _alvos(self) -> dict[int, tuple[frozenset[str], Callable[[], None]]]:
        """``{virtual-key final: (modificadores, despachante)}`` para o filtro."""
        alvos: dict[int, tuple[frozenset[str], Callable[[], None]]] = {}
        for combinacao, acao in self._mapa.items():
            codigo = vk_final(combinacao)
            if codigo is None:
                continue
            alvos[codigo] = (
                modificadores_exigidos(combinacao),
                self._despachar(combinacao, acao),
            )
        return alvos

    def parar(self) -> None:
        """Derruba o listener e a drenagem. Idempotente."""
        ouvinte, self._ouvinte = self._ouvinte, None
        if ouvinte is not None:
            ouvinte.stop()
        agendado, self._drenagem = self._drenagem, None
        if agendado is not None:
            try:
                self._raiz.after_cancel(agendado)
            except (tk.TclError, ValueError, RuntimeError):
                pass

    # ------------------------------------------------------------------

    def _agendar_drenagem(self) -> None:
        try:
            self._drenagem = self._raiz.after(INTERVALO_DE_DRENAGEM_MS, self._drenar)
        except (tk.TclError, RuntimeError):
            self._drenagem = None

    def _drenar(self) -> None:
        """Roda na thread do tkinter as ações que o hook enfileirou."""
        while True:
            try:
                acao = self._fila.get_nowait()
            except queue.Empty:
                break
            try:
                acao()
            except Exception:  # noqa: BLE001 - uma ação ruim não pode parar o resto
                traceback.print_exc()
        if self._ouvinte is not None:
            self._agendar_drenagem()

    # ------------------------------------------------------------------

    @staticmethod
    def _validar(combinacao: str) -> None:
        try:
            keyboard.HotKey.parse(combinacao)
        except (ValueError, KeyError) as erro:
            raise AtalhoInvalido(
                f"Atalho inválido: {combinacao!r}. "
                'Use o formato "<ctrl>+<alt>+c".'
            ) from erro

    def _despachantes(self) -> dict[str, Callable[[], None]]:
        """Mapa que vai para o ``GlobalHotKeys``, com as duas formas de cada atalho.

        O MESMO objeto despachante é usado nas duas entradas, então o
        antirrepique é compartilhado e a ação roda uma vez só.
        """
        despachantes: dict[str, Callable[[], None]] = {}
        for combinacao, acao in self._mapa.items():
            despachante = self._despachar(combinacao, acao)
            despachantes[combinacao] = despachante

            variante = variante_em_vk(combinacao)
            if variante is None or variante in self._mapa:
                continue
            try:
                keyboard.HotKey.parse(variante)
            except (ValueError, KeyError):
                continue
            despachantes[variante] = despachante
        return despachantes

    def _despachar(
        self, combinacao: str, acao: Callable[[], None]
    ) -> Callable[[], None]:
        exigidos = modificadores_exigidos(combinacao)

        def disparar() -> None:
            # Roda DENTRO do hook de teclado: nada aqui pode bloquear.
            # Confere no estado real do teclado que os modificadores estão
            # mesmo baixos. O ``HotKey`` do pynput guarda estado próprio e
            # ele encardece quando alguém engole o keyup — Alt+Espaço abrindo
            # o menu de sistema da janela é o caso clássico. Sem esta
            # conferência, o atalho volta a disparar sozinho lá na frente.
            if exigidos and not exigidos <= teclado.modificadores_pressionados():
                return
            agora = time.monotonic()
            if agora - self._ultimo_disparo.get(combinacao, 0.0) < JANELA_ANTIRREPIQUE:
                return
            self._ultimo_disparo[combinacao] = agora
            self._fila.put_nowait(acao)

        return disparar

    def _resubir(self) -> None:
        self.parar()
        self.iniciar()


__all__ = [
    "INTERVALO_DE_DRENAGEM_MS",
    "JANELA_ANTIRREPIQUE",
    "AtalhoInvalido",
    "GerenciadorAtalhos",
    "modificadores_exigidos",
    "variante_em_vk",
    "vk_final",
]
