"""Área de transferência do Windows via ctypes (sem pyperclip, sem pywin32).

Regras que este módulo respeita e que não são negociáveis:

* ``CloseClipboard`` sempre num ``finally``. Um clipboard vazado deixa o
  Windows INTEIRO sem copiar e colar até o processo morrer.
* ``OpenClipboard`` falha quando outro processo está com ele aberto — e
  praticamente todo mundo abre o clipboard por alguns milissegundos ao copiar.
  Por isso todo acesso passa por um retry curto em vez de estourar.
* Nada de ``time.sleep`` fixo para esperar uma cópia: comparamos o
  ``GetClipboardSequenceNumber``, que muda a cada escrita de qualquer
  processo. É mais rápido e não tem chute.
"""

from __future__ import annotations

import ctypes
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("corretor.sistema.area_transferencia depende do Windows.")

from . import teclado

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002

#: Tentativas e intervalo do retry do ``OpenClipboard`` (~500 ms no total).
#: Começou em 200 ms e não bastou: medindo contra o Notepad do Windows 11,
#: ele às vezes segura o clipboard por mais de 300 ms logo depois de uma
#: colagem. Meio segundo de espera numa ação que o usuário disparou é
#: invisível; falhar a correção não é.
_TENTATIVAS = 20
_ESPERA_ENTRE_TENTATIVAS = 0.025

#: Quanto esperar o app-alvo LER o clipboard depois de um Ctrl+V, antes de
#: restaurarmos o conteúdo anterior. O app trata WM_PASTE de forma assíncrona:
#: se restaurarmos antes dele abrir o clipboard, ele cola o texto ANTIGO.
#: 120 ms cobriu Notepad, Word, Chrome e VS Code nos testes; abaixo de ~60 ms
#: o Notepad já falhava de vez em quando.
_FOLGA_PARA_COLAR = 0.12
_FOLGA_MAXIMA_PARA_COLAR = 0.45

#: Quantas vezes tentar o Ctrl+C dentro do mesmo ``timeout``.
#: Medido contra o Notepad do Windows 11: em ~2 de 10 corridas o primeiro
#: Ctrl+C logo depois de uma colagem é simplesmente engolido — o app ainda
#: está digerindo o WM_PASTE e nem seleciona, nem copia. O segundo sempre
#: pegou. Como o orçamento total continua sendo ``timeout``, o caso "nada
#: selecionado" não fica mais lento; só ganhamos uma segunda chance.
_TENTATIVAS_DE_COPIA = 2

_user32.OpenClipboard.argtypes = (wintypes.HWND,)
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.argtypes = ()
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.argtypes = ()
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.GetClipboardData.argtypes = (wintypes.UINT,)
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
_user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
_user32.GetClipboardSequenceNumber.argtypes = ()
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.GetOpenClipboardWindow.argtypes = ()
_user32.GetOpenClipboardWindow.restype = wintypes.HWND

# restype padrão do ctypes é c_int (32 bits). Em x64 isso TRUNCA handles e
# ponteiros e o bug aparece só de vez em quando, quando o endereço passa de
# 2 GB. Declarar tudo é obrigatório aqui.
_kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
_kernel32.GlobalFree.restype = wintypes.HGLOBAL


class ClipboardIndisponivel(RuntimeError):
    """Outro processo segurou o clipboard além do nosso retry."""


@contextmanager
def _clipboard_aberto(
    tentativas: int = _TENTATIVAS,
    espera: float = _ESPERA_ENTRE_TENTATIVAS,
) -> Iterator[None]:
    """Abre o clipboard com retry e garante o ``CloseClipboard``."""
    for _ in range(tentativas):
        if _user32.OpenClipboard(None):
            break
        time.sleep(espera)
    else:
        dono = _user32.GetOpenClipboardWindow()
        raise ClipboardIndisponivel(
            f"OpenClipboard falhou em {tentativas} tentativas "
            f"({tentativas * espera:.2f}s). Janela dona: {dono}."
        )
    try:
        yield
    finally:
        _user32.CloseClipboard()


def numero_de_sequencia() -> int:
    """Contador que o Windows incrementa a cada escrita no clipboard.

    Não exige ``OpenClipboard``, o que o torna a forma barata de detectar
    "a cópia já aconteceu" sem dormir um tempo chutado.
    """
    return int(_user32.GetClipboardSequenceNumber())


def ler() -> str | None:
    """Texto do clipboard, ou ``None`` se não houver texto Unicode nele.

    Não normaliza quebras de linha: devolve exatamente o que está lá. O Word
    usa ``\\r`` para parágrafo e o resto do mundo usa ``\\r\\n``; mexer nisso
    quebraria o texto na hora de colar de volta.
    """
    with _clipboard_aberto():
        if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ponteiro = _kernel32.GlobalLock(handle)
        if not ponteiro:
            return None
        try:
            return ctypes.wstring_at(ponteiro)
        finally:
            _kernel32.GlobalUnlock(handle)


def escrever(texto: str) -> None:
    """Põe ``texto`` no clipboard como CF_UNICODETEXT.

    O bloco é alocado com GMEM_MOVEABLE ANTES de abrir o clipboard, para
    segurar o clipboard aberto pelo menor tempo possível. Depois de um
    ``SetClipboardData`` bem-sucedido o bloco pertence ao sistema e não pode
    ser liberado por nós — só liberamos se o Set falhar.
    """
    buffer = ctypes.create_unicode_buffer(texto)  # já inclui o terminador
    tamanho = ctypes.sizeof(buffer)

    handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, tamanho)
    if not handle:
        raise ClipboardIndisponivel("GlobalAlloc falhou ao reservar o texto.")

    ponteiro = _kernel32.GlobalLock(handle)
    if not ponteiro:
        _kernel32.GlobalFree(handle)
        raise ClipboardIndisponivel("GlobalLock falhou.")
    try:
        ctypes.memmove(ponteiro, buffer, tamanho)
    finally:
        _kernel32.GlobalUnlock(handle)

    try:
        with _clipboard_aberto():
            _user32.EmptyClipboard()
            if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise ClipboardIndisponivel(
                    f"SetClipboardData falhou (GetLastError={ctypes.get_last_error()})."
                )
    except BaseException:
        _kernel32.GlobalFree(handle)
        raise


def limpar() -> None:
    """Esvazia o clipboard."""
    with _clipboard_aberto():
        _user32.EmptyClipboard()


def restaurar(anterior: str | None) -> bool:
    """Devolve ao clipboard o que :func:`ler` tinha capturado antes.

    ``None`` significa "não havia texto", e nesse caso esvaziamos. Nunca
    levanta: restaurar é sempre melhor-esforço, e falhar aqui não pode
    derrubar a correção que já deu certo.
    """
    try:
        if anterior is None:
            limpar()
        else:
            escrever(anterior)
    except (ClipboardIndisponivel, OSError):
        return False
    return True


@contextmanager
def preservando() -> Iterator[str | None]:
    """Roda o bloco e devolve o clipboard ao estado em que estava.

    Cede o conteúdo anterior, para quem quiser inspecioná-lo.
    """
    try:
        anterior = ler()
    except ClipboardIndisponivel:
        anterior = None
    try:
        yield anterior
    finally:
        restaurar(anterior)


def _esperar_alvo_consumir() -> None:
    """Dá tempo do app-alvo ler o clipboard depois do Ctrl+V.

    Espera o mínimo fixo e, se alguém ainda estiver com o clipboard aberto
    (é o alvo lendo), espera até ele fechar, com teto. Ver
    ``_FOLGA_PARA_COLAR``.
    """
    inicio = time.perf_counter()
    time.sleep(_FOLGA_PARA_COLAR)
    while time.perf_counter() - inicio < _FOLGA_MAXIMA_PARA_COLAR:
        if not _user32.GetOpenClipboardWindow():
            return
        time.sleep(0.01)


def _esperar_mudanca(sequencia: int, prazo: float) -> bool:
    """Espera o clipboard ser escrito por alguém. ``True`` se foi."""
    limite = time.perf_counter() + prazo
    while time.perf_counter() < limite:
        if numero_de_sequencia() != sequencia:
            return True
        time.sleep(0.005)
    return False


def ler_selecao(timeout: float = 0.6) -> str | None:
    """Copia a seleção do app em foco e devolve o texto, sem sujar o clipboard.

    Dispara Ctrl+C e espera o ``GetClipboardSequenceNumber`` mudar. Se ele não
    mudar dentro de ``timeout`` (contando as tentativas, ver
    ``_TENTATIVAS_DE_COPIA``), é porque não havia nada selecionado — apps não
    tocam no clipboard num Ctrl+C sem seleção — e devolvemos ``None``. O
    conteúdo original é sempre restaurado.

    ``timeout`` limita só a espera pela mudança do clipboard. O tempo total
    de parede é maior: soma a injeção das teclas e a restauração do conteúdo
    anterior (na prática, ~0,2 s a mais).

    Limitação conhecida: se o clipboard continha imagem ou arquivos, esse
    conteúdo se perde. Ele já é destruído pelo Ctrl+C do usuário — só
    conseguimos restaurar o formato texto.
    """
    try:
        anterior = ler()
    except ClipboardIndisponivel:
        anterior = None

    texto: str | None = None
    fatia = timeout / _TENTATIVAS_DE_COPIA
    for _ in range(_TENTATIVAS_DE_COPIA):
        sequencia = numero_de_sequencia()
        try:
            teclado.enviar_copiar()
        except OSError:
            break
        if not _esperar_mudanca(sequencia, fatia):
            continue
        # O dono pode estar escrevendo mais formatos ainda; uma folga mínima
        # evita ler um CF_UNICODETEXT ainda não publicado.
        time.sleep(0.01)
        try:
            texto = ler()
        except ClipboardIndisponivel:
            texto = None
        break

    restaurar(anterior)
    # Cópia vazia é o mesmo que não ter seleção, para quem chama.
    return texto or None


def substituir_selecao(texto: str) -> bool:
    """Cola ``texto`` por cima da seleção atual e restaura o clipboard.

    Devolve ``False`` se não deu para escrever no clipboard ou se o Windows
    bloqueou o ``SendInput`` (janela elevada em foco).
    """
    try:
        anterior = ler()
    except ClipboardIndisponivel:
        anterior = None

    try:
        escrever(texto)
    except ClipboardIndisponivel:
        return False

    try:
        teclado.enviar_colar()
    except OSError:
        restaurar(anterior)
        return False

    _esperar_alvo_consumir()
    restaurar(anterior)
    return True


__all__ = [
    "CF_UNICODETEXT",
    "ClipboardIndisponivel",
    "escrever",
    "ler",
    "ler_selecao",
    "limpar",
    "numero_de_sequencia",
    "preservando",
    "restaurar",
    "substituir_selecao",
]
