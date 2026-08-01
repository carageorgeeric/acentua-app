"""Camada de interface: tokens de tema, helpers de janela, popup, toast, bandeja.

MODELO DE THREADS (leia antes de mexer em qualquer coisa aqui)
--------------------------------------------------------------
A thread principal do processo é a do tkinter. Existe UM único ``Tk()``,
criado pela aplicação, mantido oculto (``withdraw()``) e rodando o
``mainloop()`` durante toda a vida do programa. Nenhuma classe deste pacote
cria um ``Tk()``: todas recebem o ``root`` no construtor e criam
``Toplevel`` a partir dele. Um segundo ``Tk()`` gera dois interpretadores Tcl
e o comportamento vira loteria.

O ``pynput`` (atalhos) e o ``pystray`` (bandeja) rodam em threads próprias e
NUNCA tocam em widget: entregam trabalho com ``root.after(0, ...)``.

Este ``__init__`` guarda o sistema de design (cores, tipografia, escala) e os
helpers de geometria/foco compartilhados por ``popup``, ``toast`` e
``janela_config``. Ele de propósito não importa os submódulos — importar daqui
de dentro deles criaria ciclo.

SISTEMA DE DESIGN
-----------------
Uma cor de destaque só (o azul do sistema), o resto neutro. A página é cinza e
o conteúdo mora em cartões brancos: separação vem de elevação (sombra difusa),
nunca de borda dura — os hairlines de 1px só dividem duas linhas dentro do
mesmo cartão. Tipografia pequena e disciplinada — 15 semibold para
título de seção, 13 para corpo, 11 para legenda, em pixels e não em pontos,
porque o layout inteiro é medido em pixels e escalado por :class:`Estilo`.
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass, replace

_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# Tokens de tema
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tema:
    """As cores do aplicativo, em claro e escuro.

    Só existe UMA cor de destaque (``destaque``); todo o resto é neutro. Se
    você sentir vontade de acrescentar uma segunda cor de marca, o lugar certo
    é o ícone, não aqui.
    """

    nome: str
    escuro: bool

    #: Fundo da página. Cinza neutro: é o que faz o cartão branco flutuar.
    fundo: str
    #: Fundo do cartão, que é onde o conteúdo mora de verdade.
    superficie: str
    #: Fundo de controle sobre ``superficie``: keycap, trilho do switch, campo.
    elevado: str
    #: Estado pressionado/hover de um controle.
    pressionado: str
    #: Separador de 1px. Baixo contraste de propósito.
    hairline: str
    #: Contorno de campo de texto e keycap.
    contorno: str

    texto: str
    texto_secundario: str
    texto_terciario: str

    #: A única cor de destaque. Azul do sistema.
    destaque: str
    #: Texto sobre ``destaque``.
    destaque_texto: str
    #: Fundo suave de destaque (campo em gravação, linha em hover).
    destaque_suave: str

    #: Vermelho de erro, usado só em aviso inline.
    erro: str

    #: Segmento selecionado dentro de um controle segmentado.
    segmento_ativo: str

    #: Cor da sombra do cartão. Sempre preta; quem muda entre os temas é a
    #: opacidade com que ela é composta contra o fundo da página.
    sombra: str = "#000000"
    #: Quanto da sombra chega ao pixel. No escuro precisa ser bem mais forte:
    #: preto a 12% sobre ``#0F0F11`` não move nada.
    sombra_opacidade: float = 0.12

    def com(self, **campos: str | float) -> Tema:
        return replace(self, **campos)


TEMA_CLARO = Tema(
    nome="claro",
    escuro=False,
    fundo="#F2F2F4",
    superficie="#FFFFFF",
    elevado="#F0F0F3",
    pressionado="#E4E4E8",
    hairline="#EBEBEF",
    contorno="#E0E0E5",
    texto="#1D1D1F",
    texto_secundario="#6E6E73",
    texto_terciario="#9A9AA0",
    destaque="#007AFF",
    destaque_texto="#FFFFFF",
    destaque_suave="#E8F1FF",
    erro="#D70015",
    segmento_ativo="#FFFFFF",
    sombra_opacidade=0.13,
)

TEMA_ESCURO = Tema(
    nome="escuro",
    escuro=True,
    fundo="#0F0F11",
    superficie="#1C1C1E",
    elevado="#2A2A2C",
    pressionado="#38383A",
    hairline="#2E2E31",
    contorno="#3A3A3E",
    texto="#F5F5F7",
    texto_secundario="#A1A1A6",
    texto_terciario="#78787E",
    destaque="#0A84FF",
    destaque_texto="#FFFFFF",
    destaque_suave="#0E3563",
    erro="#FF453A",
    segmento_ativo="#5B5B60",
    sombra_opacidade=0.55,
)

TEMAS: dict[str, Tema] = {"claro": TEMA_CLARO, "escuro": TEMA_ESCURO}

#: Preferências aceitas em ``config.tema``.
PREFERENCIAS_DE_TEMA = ("claro", "escuro", "sistema")

_CHAVE_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def tema_do_sistema() -> str:
    """``"claro"`` ou ``"escuro"``, conforme o Windows.

    ``AppsUseLightTheme`` vale 0 quando o usuário escolheu escuro para os
    aplicativos. A chave não existe em instalações antigas nem fora do
    Windows: nesse caso o padrão do sistema é claro, e é isso que devolvemos.
    """
    if not _WINDOWS:
        return "claro"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_PERSONALIZE) as chave:
            valor, _tipo = winreg.QueryValueEx(chave, "AppsUseLightTheme")
    except (OSError, ImportError, ValueError):
        return "claro"
    return "escuro" if int(valor) == 0 else "claro"


def resolver_tema(preferencia: str | None = "sistema") -> Tema:
    """Traduz ``config.tema`` para o objeto :class:`Tema` de verdade.

    Qualquer valor desconhecido cai em "sistema" — um config.json editado à
    mão com lixo não pode impedir a janela de abrir.
    """
    escolha = (preferencia or "sistema").strip().lower()
    if escolha not in TEMAS:
        escolha = tema_do_sistema()
    return TEMAS[escolha]


def misturar_cores(cor_a: str, cor_b: str, proporcao: float) -> str:
    """Interpola dois ``#RRGGBB``. ``proporcao=0`` devolve ``cor_a``.

    Usado para estados intermediários (animação do switch, keycap sobre o
    azul) sem precisar de mais um token para cada variação.
    """
    proporcao = min(1.0, max(0.0, proporcao))
    a = _componentes(cor_a)
    b = _componentes(cor_b)
    return "#%02X%02X%02X" % tuple(
        round(a[i] + (b[i] - a[i]) * proporcao) for i in range(3)
    )


def _componentes(cor: str) -> tuple[int, int, int]:
    texto = cor.lstrip("#")
    return int(texto[0:2], 16), int(texto[2:4], 16), int(texto[4:6], 16)


# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------

#: A família pedida no brief. O Windows 11 traz a "Segoe UI Variable" em
#: cortes ópticos: Display para texto grande, Text para corpo, Small para
#: legenda. Usar o corte certo em cada tamanho é o que dá o acabamento; sem a
#: variável instalada, tudo cai na "Segoe UI" de sempre.
FAMILIA_PADRAO = "Segoe UI Variable Display"

#: ``(tamanho_minimo, normal, semibold)`` — a primeira faixa que couber vence.
_CORTES_OPTICOS = (
    (16, "Segoe UI Variable Display", "Segoe UI Variable Display Semib"),
    (12, "Segoe UI Variable Text", "Segoe UI Variable Text Semibold"),
    (0, "Segoe UI Variable Small", "Segoe UI Variable Small Semibol"),
)
_RESERVAS = ("Segoe UI", "Segoe UI Semibold")

_familias_cache: frozenset[str] | None = None


def familias_disponiveis(raiz: tk.Misc | None = None) -> frozenset[str]:
    """Nomes de fonte instalados, consultados uma vez por processo."""
    global _familias_cache
    if _familias_cache is None:
        try:
            from tkinter import font as tkfont

            _familias_cache = frozenset(tkfont.families(raiz))
        except (tk.TclError, RuntimeError):
            return frozenset()
    return _familias_cache


def escala_da_tela(raiz: tk.Misc | None = None) -> float:
    """Quantos pixels físicos vale 1px de layout neste monitor.

    Todo o layout é escrito em pixels lógicos (a 96 DPI). Num monitor a 150%
    o Windows entrega 144 DPI e tudo precisa crescer junto — texto, keycap,
    switch e espaçamento — ou a janela sai com metade do tamanho pretendido.
    """
    if raiz is None:
        return 1.0
    try:
        return min(3.0, max(1.0, raiz.winfo_fpixels("1i") / 96.0))
    except (tk.TclError, RuntimeError):
        return 1.0


class Estilo:
    """Tema + escala de DPI + fábrica de fontes, num objeto só.

    Todo widget desenhado à mão recebe um ``Estilo`` e mede tudo com
    ``estilo.px(...)``. Trocar o tema é construir outro ``Estilo`` e remontar
    a tela: nenhum widget guarda cor.
    """

    __slots__ = ("escala", "preferencia", "tema", "_familias", "_fontes")

    def __init__(
        self, raiz: tk.Misc | None = None, preferencia: str | None = "sistema"
    ) -> None:
        self.preferencia = (preferencia or "sistema").strip().lower()
        self.tema = resolver_tema(self.preferencia)
        self.escala = escala_da_tela(raiz)
        self._familias = familias_disponiveis(raiz)
        self._fontes: dict[tuple[int, str], object] = {}

    def px(self, medida: float) -> int:
        """Converte pixel de layout em pixel de tela."""
        return int(round(medida * self.escala))

    def familia(self, tamanho: int = 13, peso: str = "normal") -> str:
        """Corte óptico da Segoe UI Variable para este tamanho, ou a reserva."""
        semibold = peso in ("medio", "forte")
        for minimo, normal, forte in _CORTES_OPTICOS:
            if tamanho >= minimo:
                escolhida = forte if semibold else normal
                if not self._familias or escolhida in self._familias:
                    return escolhida
                break
        reserva = _RESERVAS[1] if semibold else _RESERVAS[0]
        if self._familias and reserva not in self._familias:
            return _RESERVAS[0]
        return reserva

    def fonte(self, tamanho: int = 13, peso: str = "normal") -> tuple[str, int, str]:
        """Tupla de fonte do tkinter. Tamanho negativo = pixels, não pontos.

        Pontos seriam reescalados pelo Tk por conta própria e brigariam com o
        ``px()`` daqui; em pixels, texto e caixa crescem no mesmo passo.

        O Tk só conhece ``normal``/``bold``. Quando existe uma família
        semibold instalada usamos ela com peso normal — semibold de verdade é
        mais leve e mais Apple que o bold sintético do Tk.
        """
        familia = self.familia(tamanho, peso)
        precisa_encorpar = (
            peso in ("medio", "forte") and familia == self.familia(tamanho, "normal")
        )
        return (familia, -self.px(tamanho), "bold" if precisa_encorpar else "normal")

    def medir(self, texto: str, tamanho: int = 13, peso: str = "normal") -> int:
        """Largura em pixels de tela — precisa para posicionar num Canvas."""
        from tkinter import font as tkfont

        chave = (tamanho, peso)
        fonte = self._fontes.get(chave)
        if fonte is None:
            fonte = tkfont.Font(font=self.fonte(tamanho, peso))
            self._fontes[chave] = fonte
        return int(fonte.measure(texto))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Compatibilidade: paleta antiga usada antes do redesenho
# ---------------------------------------------------------------------------

#: Mantido para quem ainda importa ``TEMA`` como dicionário. Novo código deve
#: usar :class:`Tema` / :class:`Estilo`.
TEMA = {
    # ``superficie`` e não ``fundo``: antes do cartão existir, o "fundo" do
    # tema escuro era esta cor, e quem ainda lê este dicionário espera ela.
    "fundo": TEMA_ESCURO.superficie,
    "fundo_alt": TEMA_ESCURO.elevado,
    "borda": TEMA_ESCURO.contorno,
    "texto": TEMA_ESCURO.texto,
    "texto_fraco": TEMA_ESCURO.texto_secundario,
    "destaque": TEMA_ESCURO.destaque,
    "destaque_fundo": TEMA_ESCURO.destaque_suave,
    "acento": TEMA_ESCURO.destaque,
}

FONTE_TITULO = ("Segoe UI", 11)
FONTE_PEQUENA = ("Segoe UI", 9)


# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------

if _WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _Ponto(ctypes.Structure):
        _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))

    class _Retangulo(ctypes.Structure):
        _fields_ = (
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        )

    class _InfoMonitor(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _Retangulo),
            ("rcWork", _Retangulo),
            ("dwFlags", wintypes.DWORD),
        )

    _MONITOR_DEFAULTTONEAREST = 2
    _GWL_EXSTYLE = -20
    _WS_EX_NOACTIVATE = 0x08000000
    _WS_EX_TOOLWINDOW = 0x00000080

    # DwmSetWindowAttribute
    _DWMWA_USAR_MODO_ESCURO = 20
    _DWMWA_CANTO = 33
    _DWMWA_COR_DA_BORDA = 34
    _DWMWA_COR_DA_BARRA = 35
    _DWMWA_COR_DO_TITULO = 36
    #: 0 padrão, 1 nunca arredondar, 2 arredondar, 3 arredondar pouco.
    _CANTO_ARREDONDADO = 2
    _CANTO_ARREDONDADO_PEQUENO = 3

    _user32.MonitorFromPoint.argtypes = (_Ponto, wintypes.DWORD)
    _user32.MonitorFromPoint.restype = wintypes.HANDLE
    _user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_InfoMonitor))
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.GetParent.argtypes = (wintypes.HWND,)
    _user32.GetParent.restype = wintypes.HWND
    _obter_estilo = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _definir_estilo = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _obter_estilo.argtypes = (wintypes.HWND, ctypes.c_int)
    _obter_estilo.restype = ctypes.c_ssize_t
    _definir_estilo.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _definir_estilo.restype = ctypes.c_ssize_t


def ativar_ciencia_de_dpi() -> bool:
    """Marca o processo como DPI-aware. Chame ANTES de criar o ``Tk()``.

    Sem isso, num monitor a 125%/150% o Windows entrega coordenadas
    virtualizadas e o popup aparece deslocado do cursor, além de o texto sair
    borrado. Tentamos primeiro o modo per-monitor v2 (Win10 1703+) e caímos
    para os antigos. Devolve ``True`` se algum modo pegou.
    """
    if not _WINDOWS:
        return False
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        if _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return True
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            return True
    except (AttributeError, OSError):
        pass
    try:
        return bool(_user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def definir_identidade_no_windows(identificador: str) -> bool:
    """Dá ao processo uma identidade própria na barra de tarefas.

    Sem isto o Windows identifica a janela pelo executável que a hospeda — o
    ``pythonw.exe`` — e a barra de tarefas mostra o logo do Python, por mais
    que a janela tenha o ícone certo na barra de título. O AppUserModelID é o
    que separa uma coisa da outra: com um identificador próprio, o Windows
    passa a tratar o Acentua como um aplicativo, com o ícone dele e um botão
    que não se mistura com outros scripts Python abertos.

    Chame ANTES de criar a primeira janela: o Windows lê o identificador no
    momento em que registra a janela, e mudar depois não reetiqueta o que já
    está na barra. O identificador precisa ser estável entre versões, ou o app
    fixado na barra de tarefas vira um ícone morto a cada atualização.
    """
    if not _WINDOWS:
        return False
    try:
        shell32 = ctypes.WinDLL("shell32")
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = (wintypes.LPCWSTR,)
        return shell32.SetCurrentProcessExplicitAppUserModelID(identificador) == 0
    except (AttributeError, OSError):
        return False


def hwnd_da_janela(janela: tk.Misc) -> int:
    """HWND real de um ``Toplevel``.

    ``winfo_id()`` devolve a janela interna do Tk; quem tem moldura, sombra e
    cantos é o pai dela.
    """
    if not _WINDOWS:
        return 0
    try:
        janela.update_idletasks()
        interno = janela.winfo_id()
        return int(_user32.GetParent(interno) or interno)
    except (OSError, tk.TclError):
        return 0


def _dwm(hwnd: int, atributo: int, valor: int) -> bool:
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        bruto = ctypes.c_int(valor)
        resultado = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), atributo, ctypes.byref(bruto), ctypes.sizeof(bruto)
        )
        return resultado == 0
    except (AttributeError, OSError):
        return False


def _cor_win32(cor: str) -> int:
    """``#RRGGBB`` -> COLORREF ``0x00BBGGRR``, que é a ordem que o DWM quer."""
    r, g, b = _componentes(cor)
    return (b << 16) | (g << 8) | r


def arredondar_janela(janela: tk.Misc, pequeno: bool = False) -> bool:
    """Pede ao compositor do Windows para arredondar os cantos da janela.

    É o único caminho que dá canto arredondado com antialiasing de verdade:
    o Canvas do Tk desenha polígono sem suavização, e o truque do
    ``-transparentcolor`` recorta por igualdade exata de cor, então a borda
    suavizada vira uma franja da cor-chave. Deixar o DWM recortar resolve os
    dois problemas e ainda traz a sombra do sistema de graça.

    Funciona em janela sem decoração (``overrideredirect``), que é o caso do
    popup e do toast. No Windows 10 a chamada falha em silêncio e a janela
    fica quadrada — feio, mas inteiro.
    """
    hwnd = hwnd_da_janela(janela)
    if not hwnd:
        return False
    canto = _CANTO_ARREDONDADO_PEQUENO if pequeno else _CANTO_ARREDONDADO
    return _dwm(hwnd, _DWMWA_CANTO, canto)


def _recortar_regiao(janela: tk.Misc, raio: int | None) -> bool:
    """Recorta a janela numa região arredondada. ``raio=None`` vira cápsula.

    O DWM só arredonda no raio fixo do sistema (~8px), que numa faixa de 40px
    de altura ainda lê como retângulo, e não existe atributo para pedir mais.
    Recortar a região é o único caminho para raio grande. O preço é a borda sem
    antialiasing: o recorte do Win32 é binário por pixel. A 100% o degrau
    praticamente some; num zoom de 4x ele aparece.

    Chame DEPOIS de definir a geometria: a região é fixa no tamanho atual.
    """
    if not _WINDOWS:
        return False
    hwnd = hwnd_da_janela(janela)
    if not hwnd:
        return False
    try:
        janela.update_idletasks()
        largura = janela.winfo_width()
        altura = janela.winfo_height()
        if largura <= 1 or altura <= 1:
            return False
        # CreateRoundRectRgn recebe a ELIPSE do canto, não o raio: o dobro.
        # Com a elipse igual à altura o canto encosta no meio da lateral, que
        # é exatamente a cápsula.
        elipse = altura if raio is None else min(altura, max(0, raio) * 2)
        gdi32 = ctypes.WinDLL("gdi32")
        gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
        regiao = gdi32.CreateRoundRectRgn(
            0, 0, largura + 1, altura + 1, elipse, elipse
        )
        if not regiao:
            return False
        # O Windows passa a ser dono da região; não pode ser destruída aqui.
        _user32.SetWindowRgn.argtypes = (wintypes.HWND, wintypes.HANDLE, wintypes.BOOL)
        return bool(_user32.SetWindowRgn(wintypes.HWND(hwnd), regiao, True))
    except (AttributeError, OSError, tk.TclError):
        return False


def moldar_capsula(janela: tk.Misc) -> bool:
    """Recorta a janela numa cápsula (raio = metade da altura)."""
    return _recortar_regiao(janela, None)


def moldar_arredondada(janela: tk.Misc, raio: int) -> bool:
    """Recorta a janela num retângulo de canto ``raio``, em pixels de tela.

    Existe porque ``arredondar_janela`` só consegue o canto padrão do sistema:
    numa janela sem decoração, que também não ganha sombra do compositor, 8px
    lêem como retângulo chapado em vez de cartão flutuante. Passe o raio já
    convertido com ``estilo.px``.
    """
    return _recortar_regiao(janela, raio)


def vestir_moldura_nativa(janela: tk.Misc, tema: Tema) -> bool:
    """Deixa a barra de título do Windows na cor do tema da janela.

    Sem isto, uma janela de conteúdo escuro ganha uma barra de título branca
    em cima — o detalhe que mais entrega "app de tkinter".
    """
    hwnd = hwnd_da_janela(janela)
    if not hwnd:
        return False
    ok = _dwm(hwnd, _DWMWA_USAR_MODO_ESCURO, 1 if tema.escuro else 0)
    _dwm(hwnd, _DWMWA_COR_DA_BARRA, _cor_win32(tema.fundo))
    _dwm(hwnd, _DWMWA_COR_DO_TITULO, _cor_win32(tema.texto))
    _dwm(hwnd, _DWMWA_COR_DA_BORDA, _cor_win32(tema.hairline))
    _dwm(hwnd, _DWMWA_CANTO, _CANTO_ARREDONDADO)
    return ok


def area_util_do_cursor(raiz: tk.Misc) -> tuple[int, int, int, int]:
    """``(x, y, largura, altura)`` da área útil do monitor sob o cursor.

    "Área útil" exclui a barra de tarefas — é onde uma janela pode aparecer
    sem ficar por baixo dela. ``winfo_screenwidth`` só conhece o monitor
    primário, então usamos ``MonitorFromPoint`` para acertar em setup
    multi-monitor. Se algo falhar, caímos no monitor primário inteiro.
    """
    x, y = raiz.winfo_pointerxy()
    if _WINDOWS:
        try:
            monitor = _user32.MonitorFromPoint(_Ponto(x, y), _MONITOR_DEFAULTTONEAREST)
            info = _InfoMonitor()
            info.cbSize = ctypes.sizeof(_InfoMonitor)
            if monitor and _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except OSError:
            pass
    return 0, 0, raiz.winfo_screenwidth(), raiz.winfo_screenheight()


def posicao_do_cursor(raiz: tk.Misc) -> tuple[int, int]:
    return raiz.winfo_pointerxy()


def centralizar_no_monitor_do_cursor(
    janela: tk.Misc, largura: int, altura: int, *, fracao_vertical: float = 0.42
) -> tuple[int, int]:
    """Canto superior esquerdo para centralizar a janela onde o usuário está.

    Centralizar no monitor primário joga a janela para outra tela em setup de
    dois monitores. Um pouco acima do centro (``fracao_vertical``) porque o
    olho lê o centro óptico mais alto que o geométrico.
    """
    ax, ay, alargura, aaltura = area_util_do_cursor(janela)
    x = ax + (alargura - largura) // 2
    y = ay + int((aaltura - altura) * fracao_vertical)
    return max(ax, x), max(ay, y)


def encaixar_na_tela(
    raiz: tk.Misc,
    x: int,
    y: int,
    largura: int,
    altura: int,
    *,
    margem: int = 8,
) -> tuple[int, int]:
    """Empurra um retângulo para dentro da área útil do monitor do cursor.

    Perto da borda direita/inferior a janela vira para o outro lado do cursor
    em vez de só encostar — encostada ela cobriria justamente o texto que o
    usuário está olhando.
    """
    ax, ay, alargura, aaltura = area_util_do_cursor(raiz)
    if x + largura + margem > ax + alargura:
        x = min(x - largura - 2 * margem, ax + alargura - largura - margem)
    if y + altura + margem > ay + aaltura:
        y = min(y - altura - 2 * margem, ay + aaltura - altura - margem)
    x = max(ax + margem, x)
    y = max(ay + margem, y)
    return x, y


def janela_em_foco() -> int:
    """HWND da janela em primeiro plano (0 se não der para saber)."""
    if not _WINDOWS:
        return 0
    try:
        return int(_user32.GetForegroundWindow() or 0)
    except OSError:
        return 0


def focar_janela(hwnd: int) -> bool:
    """Devolve o foco para ``hwnd``.

    Usado depois de fechar o popup: ele roubou o foco para receber as teclas,
    e o Ctrl+V precisa cair no app do usuário, não em lugar nenhum. O Windows
    permite essa chamada porque quem está em foco somos nós.
    """
    if not _WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32.SetForegroundWindow(wintypes.HWND(hwnd)))
    except OSError:
        return False


def impedir_roubo_de_foco(janela: tk.Toplevel) -> bool:
    """Marca a janela como WS_EX_NOACTIVATE: ela aparece mas nunca ativa.

    É o que garante que o toast não tire o cursor de texto do usuário no meio
    de uma frase. Precisa do HWND real: o ``winfo_id()`` do Tk devolve a
    janela interna, e o estilo tem que ir no pai (o frame do gerenciador).
    """
    if not _WINDOWS:
        return False
    try:
        hwnd = hwnd_da_janela(janela)
        if not hwnd:
            return False
        estilo = _obter_estilo(hwnd, _GWL_EXSTYLE)
        _definir_estilo(hwnd, _GWL_EXSTYLE, estilo | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
        return True
    except (OSError, tk.TclError):
        return False


__all__ = [
    "FAMILIA_PADRAO",
    "FONTE_PEQUENA",
    "FONTE_TITULO",
    "PREFERENCIAS_DE_TEMA",
    "TEMA",
    "TEMAS",
    "TEMA_CLARO",
    "TEMA_ESCURO",
    "Estilo",
    "Tema",
    "area_util_do_cursor",
    "arredondar_janela",
    "ativar_ciencia_de_dpi",
    "centralizar_no_monitor_do_cursor",
    "definir_identidade_no_windows",
    "encaixar_na_tela",
    "escala_da_tela",
    "familias_disponiveis",
    "focar_janela",
    "hwnd_da_janela",
    "impedir_roubo_de_foco",
    "janela_em_foco",
    "misturar_cores",
    "moldar_arredondada",
    "moldar_capsula",
    "posicao_do_cursor",
    "resolver_tema",
    "tema_do_sistema",
    "vestir_moldura_nativa",
]
