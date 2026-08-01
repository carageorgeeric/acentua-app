"""Injeção de teclas no Windows via ``SendInput`` (user32, ctypes).

Por que não usar ``pynput.keyboard.Controller`` ou a lib ``keyboard``:

1. Precisamos mandar **scancodes** (``KEYEVENTF_SCANCODE``). Apps Electron
   (Discord, VS Code, Slack) e jogos costumam ler o scancode e ignoram
   eventos que só trazem virtual-key.
2. Precisamos **soltar os modificadores presos**. Quando o usuário aperta
   ``Ctrl+Alt+C``, o Ctrl e o Alt continuam fisicamente pressionados enquanto
   processamos o atalho. Se injetarmos Ctrl+V nesse estado, o app-alvo recebe
   ``Ctrl+Alt+V`` — que quase nunca é "colar". Nenhuma das duas libs dá
   controle sobre isso.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("corretor.sistema.teclado depende do user32 (Windows).")

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# --------------------------------------------------------------------------
# Constantes Win32
# --------------------------------------------------------------------------

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
#: Setas do bloco de navegação. Ver ``_SEMPRE_ESTENDIDA``: elas PRECISAM do
#: flag de estendida, e ``MAPVK_VK_TO_VSC_EX`` não o entrega sozinho.
VK_LEFT = 0x25
VK_RIGHT = 0x27

VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
VK_X = 0x58
VK_Z = 0x5A

_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008
_MAPVK_VK_TO_VSC_EX = 4

#: Carimbo em ``dwExtraInfo`` para que um listener nosso saiba distinguir uma
#: tecla que nós injetamos de uma que o usuário digitou de verdade.
MARCA_ACENTUA = 0x0AC3_17A0

#: Teclas cujo scancode precisa do prefixo 0xE0. ``MAPVK_VK_TO_VSC_EX`` já
#: devolve o prefixo para quase todas, mas as variantes direita dos
#: modificadores são a fonte clássica de bug: sem o flag de estendida, o
#: Windows entrega o keyup para a tecla ESQUERDA e a direita fica grudada.
#:
#: As SETAS são a outra exceção, e mais traiçoeira. Medido nesta máquina:
#: ``MapVirtualKeyW(VK_LEFT, MAPVK_VK_TO_VSC_EX)`` devolve ``0x004B``, sem
#: prefixo nenhum — e ``0x4B`` cru é o **4 do teclado numérico**. Com NumLock
#: desligado o Windows trata as duas como seta e tudo funciona; com NumLock
#: ligado, injetar a seta esquerda digita ``4`` no documento do usuário. O bug
#: só aparece na máquina dos outros, então o flag vai fixo aqui.
_SEMPRE_ESTENDIDA = frozenset(
    {VK_RCONTROL, VK_RMENU, VK_LWIN, VK_RWIN, VK_LEFT, VK_RIGHT}
)

#: Pausa entre eventos de tecla. Zero funciona na maioria dos apps, mas
#: Electron e apps remotos (RDP, VMs) perdem eventos quando o down e o up
#: chegam no mesmo tick. 8 ms é imperceptível e cobriu todos os testes.
_PAUSA_ENTRE_EVENTOS = 0.008

#: Quanto esperar o Windows processar os keyups que injetamos antes de
#: considerar que os modificadores realmente soltaram.
_PRAZO_SOLTAR = 0.15

_MODIFICADORES: dict[str, tuple[int, ...]] = {
    "ctrl": (VK_LCONTROL, VK_RCONTROL),
    "alt": (VK_LMENU, VK_RMENU),
    "shift": (VK_LSHIFT, VK_RSHIFT),
    "win": (VK_LWIN, VK_RWIN),
}

#: Todas as virtual-keys de modificador, inclusive as genéricas.
VKS_MODIFICADORES = frozenset(
    {VK_SHIFT, VK_CONTROL, VK_MENU, *(vk for teclas in _MODIFICADORES.values() for vk in teclas)}
)

#: Sinaliza que estamos injetando teclas agora.
#:
#: Existe para o filtro de eventos de ``atalhos`` engolir o keyup FÍSICO dos
#: modificadores durante a injeção. Sem isso há uma corrida real: o usuário
#: aperta Ctrl+Alt+C e continua segurando; nós soltamos os modificadores e
#: começamos a mandar Ctrl+V; se o dedo dele sair nesse meio, o keyup real do
#: Ctrl chega ENTRE o nosso ctrl-down e o nosso v-down, e o app recebe um "v"
#: solto — que substitui a seleção do usuário pela letra v. Foi exatamente
#: assim que um "c" apareceu no lugar do texto no teste com o Notepad.
_INJETANDO = threading.Event()


def esta_injetando() -> bool:
    """``True`` enquanto :func:`injetando` está ativo."""
    return _INJETANDO.is_set()


@contextmanager
def injetando() -> Iterator[None]:
    """Marca a janela em que teclas físicas de modificador devem ser ignoradas."""
    _INJETANDO.set()
    try:
        yield
    finally:
        _INJETANDO.clear()


# --------------------------------------------------------------------------
# Estruturas (INPUT / KEYBDINPUT / MOUSEINPUT / HARDWAREINPUT)
# --------------------------------------------------------------------------

_ULONG_PTR = ctypes.c_size_t  # wintypes não define ULONG_PTR


class _EntradaTeclado(ctypes.Structure):
    """KEYBDINPUT."""

    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _EntradaMouse(ctypes.Structure):
    """MOUSEINPUT — só existe para a união ter o tamanho certo."""

    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _EntradaHardware(ctypes.Structure):
    """HARDWAREINPUT."""

    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _UniaoEntrada(ctypes.Union):
    _fields_ = (
        ("ki", _EntradaTeclado),
        ("mi", _EntradaMouse),
        ("hi", _EntradaHardware),
    )


class _Entrada(ctypes.Structure):
    """INPUT."""

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _UniaoEntrada))


_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_Entrada), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_user32.MapVirtualKeyW.restype = wintypes.UINT
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short


class FalhaAoEnviarTeclas(OSError):
    """``SendInput`` foi bloqueado pelo Windows.

    O caso comum é UIPI: a janela em foco pertence a um processo com
    integridade mais alta (algo aberto "como administrador"). Um processo
    normal não consegue injetar entrada nele.
    """


# --------------------------------------------------------------------------
# Primitivas
# --------------------------------------------------------------------------


def _scancode(vk: int) -> tuple[int, bool]:
    """Devolve ``(scancode, é_estendida)`` para uma virtual-key."""
    bruto = _user32.MapVirtualKeyW(vk, _MAPVK_VK_TO_VSC_EX)
    estendida = (bruto >> 8) in (0xE0, 0xE1) or vk in _SEMPRE_ESTENDIDA
    return bruto & 0xFF, estendida


def _evento(vk: int, *, soltar: bool) -> _Entrada:
    codigo, estendida = _scancode(vk)
    flags = _KEYEVENTF_SCANCODE if codigo else 0
    if estendida:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if soltar:
        flags |= _KEYEVENTF_KEYUP

    entrada = _Entrada()
    entrada.type = _INPUT_KEYBOARD
    # Com KEYEVENTF_SCANCODE o Windows ignora wVk; mantemos o vk preenchido
    # só quando não há scancode (teclas virtuais puras, ex. VK_BROWSER_*).
    entrada.ki.wVk = 0 if codigo else vk
    entrada.ki.wScan = codigo
    entrada.ki.dwFlags = flags
    entrada.ki.time = 0
    entrada.ki.dwExtraInfo = MARCA_ACENTUA
    return entrada


def _enviar(eventos: list[_Entrada]) -> None:
    if not eventos:
        return
    lote = (_Entrada * len(eventos))(*eventos)
    enviados = _user32.SendInput(len(eventos), lote, ctypes.sizeof(_Entrada))
    if enviados != len(eventos):
        erro = ctypes.get_last_error()
        raise FalhaAoEnviarTeclas(
            f"SendInput enviou {enviados}/{len(eventos)} eventos "
            f"(GetLastError={erro}). Janela em foco provavelmente é elevada."
        )


def _pressionada(vk: int) -> bool:
    """Estado FÍSICO da tecla (bit alto de ``GetAsyncKeyState``)."""
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------


def modificadores_pressionados() -> set[str]:
    """Modificadores fisicamente pressionados agora.

    Devolve nomes lógicos: ``{"ctrl", "alt", "shift", "win"}``. Não distingue
    esquerda de direita porque nenhum consumidor precisa dessa diferença — a
    distinção só importa internamente, em :func:`soltar_modificadores`.
    """
    return {
        nome
        for nome, teclas in _MODIFICADORES.items()
        if any(_pressionada(vk) for vk in teclas)
    }


def soltar_modificadores() -> None:
    """Injeta keyup em todo modificador que estiver preso.

    Esta é a função que faz o Acentua funcionar. O usuário dispara o atalho
    com ``Ctrl+Alt+C``; enquanto tratamos o evento, Ctrl e Alt continuam
    baixos. Qualquer tecla que injetarmos vira ``Ctrl+Alt+<tecla>`` no
    app-alvo. Soltamos as duas variantes (esquerda e direita) de cada
    modificador que ``GetAsyncKeyState`` reportar como pressionado e
    esperamos o Windows digerir os eventos antes de devolver o controle.

    Efeito colateral aceito: quando o usuário finalmente tirar o dedo da
    tecla, chega um keyup extra. Apps ignoram keyup de tecla já solta.
    """
    presos = [vk for teclas in _MODIFICADORES.values() for vk in teclas if _pressionada(vk)]
    if not presos:
        return

    _enviar([_evento(vk, soltar=True) for vk in presos])

    prazo = time.perf_counter() + _PRAZO_SOLTAR
    while time.perf_counter() < prazo:
        if not any(_pressionada(vk) for vk in presos):
            return
        time.sleep(0.005)
    # Se estourou o prazo, a tecla está fisicamente presa mesmo (o usuário
    # não soltou e o auto-repeat reafirmou o down). Seguimos assim mesmo:
    # falhar aqui deixaria o usuário sem resposta nenhuma.


def enviar_combinacao(*vks: int) -> None:
    """Pressiona as teclas na ordem dada e solta na ordem inversa.

    Não mexe nos modificadores presos de propósito — quem precisa disso é
    :func:`enviar_copiar` / :func:`enviar_colar`. Aqui a semântica é crua.
    """
    if not vks:
        return
    for vk in vks:
        _enviar([_evento(vk, soltar=False)])
        time.sleep(_PAUSA_ENTRE_EVENTOS)
    for vk in reversed(vks):
        _enviar([_evento(vk, soltar=True)])
        time.sleep(_PAUSA_ENTRE_EVENTOS)


def enviar_copiar() -> None:
    """Ctrl+C limpo, com os modificadores do usuário soltos antes."""
    with injetando():
        soltar_modificadores()
        enviar_combinacao(VK_CONTROL, VK_C)


def enviar_colar() -> None:
    """Ctrl+V limpo, com os modificadores do usuário soltos antes."""
    with injetando():
        soltar_modificadores()
        enviar_combinacao(VK_CONTROL, VK_V)


__all__ = [
    "MARCA_ACENTUA",
    "VKS_MODIFICADORES",
    "VK_LEFT",
    "VK_RIGHT",
    "FalhaAoEnviarTeclas",
    "enviar_colar",
    "enviar_combinacao",
    "enviar_copiar",
    "esta_injetando",
    "injetando",
    "modificadores_pressionados",
    "soltar_modificadores",
]
