"""Widgets desenhados à mão: switch, controle segmentado, botão, gravador.

Por que desenhar em vez de usar ``ttk``
---------------------------------------
O ``ttk`` no Windows não dá canto arredondado, não dá switch e não deixa
pintar o fundo de um ``Checkbutton`` sem brigar com o tema nativo. Todo
controle aqui é um ``Canvas`` com uma imagem de fundo gerada pelo Pillow —
que já é dependência do projeto por causa da bandeja.

A imagem entra porque o ``Canvas`` do Tk desenha polígono sem suavização: um
retângulo arredondado feito com ``create_polygon`` sai serrilhado. Gerando a
forma 4x maior no Pillow e reduzindo por média de área, a borda sai com
antialiasing de verdade. Como o controle está sempre sobre um fundo opaco e
conhecido, a suavização é composta contra a cor do pai e o resultado é
perfeito — o mesmo truque não funcionaria contra o desktop.

O texto NÃO vai na imagem: fica em ``create_text`` para manter o ClearType do
Windows. Forma vem do Pillow, letra vem do Tk.
"""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from . import Estilo, misturar_cores

# ---------------------------------------------------------------------------
# Formas com antialiasing
# ---------------------------------------------------------------------------

#: Fator de supersampling. 4x já elimina o serrilhado a olho nu; mais que isso
#: só custa memória.
_AMOSTRAGEM = 4

#: As formas se repetem muito (três switches iguais, dez keycaps iguais), e um
#: ``PhotoImage`` sem referência viva é coletado e some da tela. O cache
#: resolve as duas coisas de uma vez.
_CACHE: dict[tuple, Any] = {}
_LIMITE_CACHE = 512

#: Interpretador Tcl dono das imagens em cache. Um ``PhotoImage`` pertence ao
#: interpretador que o criou: reaproveitar num ``Tk()`` novo levanta
#: ``image "pyimageN" doesn't exist``. O app só tem um ``Tk``, mas a suíte de
#: testes cria e destrói vários, e o cache tem que acompanhar.
_INTERPRETADOR: Any = None


def _guardar(mestre: tk.Misc, chave: tuple, criar: Callable[[], Any]) -> Any:
    global _INTERPRETADOR
    interpretador = mestre.tk
    if interpretador is not _INTERPRETADOR:
        _CACHE.clear()
        _INTERPRETADOR = interpretador
    imagem = _CACHE.get(chave)
    if imagem is None:
        if len(_CACHE) >= _LIMITE_CACHE:
            _CACHE.clear()
        imagem = criar()
        _CACHE[chave] = imagem
    return imagem


def _reduzir(
    imagem: Image.Image, largura: int, altura: int, mestre: tk.Misc
) -> ImageTk.PhotoImage:
    return ImageTk.PhotoImage(
        imagem.resize((largura, altura), Image.BOX), master=mestre
    )


def imagem_arredondada(
    mestre: tk.Misc,
    largura: int,
    altura: int,
    raio: int,
    preenchimento: str,
    fundo: str,
    contorno: str | None = None,
    espessura: int = 1,
) -> ImageTk.PhotoImage:
    """Retângulo de cantos arredondados, suavizado, sobre ``fundo`` opaco."""
    largura = max(1, largura)
    altura = max(1, altura)
    chave = ("arred", largura, altura, raio, preenchimento, fundo, contorno, espessura)

    def criar() -> ImageTk.PhotoImage:
        f = _AMOSTRAGEM
        imagem = Image.new("RGB", (largura * f, altura * f), fundo)
        desenho = ImageDraw.Draw(imagem)
        desenho.rounded_rectangle(
            (0, 0, largura * f - 1, altura * f - 1),
            radius=max(0, raio) * f,
            fill=preenchimento,
            outline=contorno,
            width=espessura * f if contorno else 0,
        )
        return _reduzir(imagem, largura, altura, mestre)

    return _guardar(mestre, chave, criar)


def imagem_cartao(
    mestre: tk.Misc,
    largura: int,
    altura: int,
    raio: int,
    preenchimento: str,
    fundo: str,
    *,
    margem: int,
    desfoque: int,
    deslocamento: int,
    cor_sombra: str = "#000000",
    opacidade: float = 0.13,
) -> ImageTk.PhotoImage:
    """Cartão com sombra difusa, composta contra o ``fundo`` opaco do pai.

    ``margem`` é a folga em volta do cartão onde a sombra tem espaço para se
    espalhar; sem ela o borrão sai cortado no limite da imagem. A sombra é
    desenhada como máscara em escala de cinza e só depois colada: assim o
    borrão interpola entre o fundo da página e o preto sem precisar de canal
    alfa — que contra o desktop não teria com o que compor.
    """
    largura = max(1, largura)
    altura = max(1, altura)
    chave = (
        "cartao", largura, altura, raio, preenchimento, fundo,
        margem, desfoque, deslocamento, cor_sombra, round(opacidade, 3),
    )

    def criar() -> ImageTk.PhotoImage:
        f = _AMOSTRAGEM
        L, A = largura * f, altura * f
        m, d = margem * f, deslocamento * f
        mascara = Image.new("L", (L, A), 0)
        ImageDraw.Draw(mascara).rounded_rectangle(
            (m, m + d, L - m - 1, A - m - 1 + d),
            radius=max(0, raio) * f,
            fill=round(255 * min(1.0, max(0.0, opacidade))),
        )
        # Metade do desfoque no raio do gaussiano: é o que aproxima o
        # "blur: Npx" do CSS, que é a régua com que as referências foram feitas.
        mascara = mascara.filter(ImageFilter.GaussianBlur(desfoque * f / 2))

        imagem = Image.new("RGB", (L, A), fundo)
        imagem.paste(Image.new("RGB", (L, A), cor_sombra), (0, 0), mascara)
        ImageDraw.Draw(imagem).rounded_rectangle(
            (m, m, L - m - 1, A - m - 1),
            radius=max(0, raio) * f,
            fill=preenchimento,
        )
        return _reduzir(imagem, largura, altura, mestre)

    return _guardar(mestre, chave, criar)


def imagem_interruptor(
    mestre: tk.Misc,
    largura: int,
    altura: int,
    posicao: float,
    cor_trilho: str,
    cor_bolinha: str,
    fundo: str,
) -> ImageTk.PhotoImage:
    """Trilho + bolinha num quadro só, com ``posicao`` de 0 (off) a 1 (on).

    Desenhar os dois juntos é o que deixa a sombra da bolinha compor certo
    sobre o trilho — em dois ``create_image`` sobrepostos a borda suavizada de
    cima brigaria com a de baixo.
    """
    chave = ("switch", largura, altura, round(posicao, 3), cor_trilho, cor_bolinha, fundo)

    def criar() -> ImageTk.PhotoImage:
        f = _AMOSTRAGEM
        L, A = largura * f, altura * f
        imagem = Image.new("RGB", (L, A), fundo)
        desenho = ImageDraw.Draw(imagem)
        desenho.rounded_rectangle((0, 0, L - 1, A - 1), radius=A // 2, fill=cor_trilho)

        margem = max(1, round(2.5 * f))
        diametro = A - 2 * margem
        percurso = L - 2 * margem - diametro
        x = margem + percurso * min(1.0, max(0.0, posicao))
        # Um anel meio pixel mais escuro embaixo faz a bolinha "sentar" no
        # trilho. Fora a sombra do cartão, é o único relevo do sistema.
        sombra = misturar_cores(cor_trilho, "#000000", 0.22)
        desenho.ellipse(
            (x, margem + f * 0.5, x + diametro, margem + diametro + f * 0.6), fill=sombra
        )
        desenho.ellipse((x, margem, x + diametro, margem + diametro), fill=cor_bolinha)
        return _reduzir(imagem, largura, altura, mestre)

    return _guardar(mestre, chave, criar)


def imagem_segmentado(
    mestre: tk.Misc,
    largura: int,
    altura: int,
    quantidade: int,
    ativo: int,
    fundo: str,
    cor_trilho: str,
    cor_ativo: str,
    cor_hairline: str,
    raio: int | None = None,
    raio_ativo: int | None = None,
) -> ImageTk.PhotoImage:
    """Trilho do controle segmentado com a pílula do item selecionado.

    Os raios são opcionais e caem em cápsula (metade da altura) quando não
    informados — o padrão certo para um controle desta altura.
    """
    folga = 2
    if raio is None:
        raio = altura // 2
    if raio_ativo is None:
        raio_ativo = max(0, altura - 2 * folga) // 2
    chave = (
        "seg", largura, altura, quantidade, ativo,
        fundo, cor_trilho, cor_ativo, cor_hairline, raio, raio_ativo,
    )

    def criar() -> ImageTk.PhotoImage:
        f = _AMOSTRAGEM
        L, A = largura * f, altura * f
        imagem = Image.new("RGB", (L, A), fundo)
        desenho = ImageDraw.Draw(imagem)
        desenho.rounded_rectangle((0, 0, L - 1, A - 1), radius=raio * f, fill=cor_trilho)

        passo = L / quantidade
        # Divisórias só onde nenhum dos dois lados está selecionado: é assim
        # que o macOS evita a linha encostando na pílula.
        for i in range(1, quantidade):
            if i in (ativo, ativo + 1):
                continue
            x = round(i * passo)
            desenho.rectangle(
                (x, round(A * 0.26), x + max(1, f // 2), round(A * 0.74)),
                fill=cor_hairline,
            )

        if 0 <= ativo < quantidade:
            recuo = round(folga * f)
            x1 = round(ativo * passo) + recuo
            x2 = round((ativo + 1) * passo) - recuo
            desenho.rounded_rectangle(
                (x1, recuo + round(f * 0.4), x2, A - recuo + round(f * 0.4)),
                radius=raio_ativo * f,
                fill=misturar_cores(cor_ativo, "#000000", 0.16),
            )
            desenho.rounded_rectangle(
                (x1, recuo, x2, A - recuo), radius=raio_ativo * f, fill=cor_ativo
            )
        return _reduzir(imagem, largura, altura, mestre)

    return _guardar(mestre, chave, criar)


# ---------------------------------------------------------------------------
# Atalhos: keysym do tkinter -> formato do pynput
# ---------------------------------------------------------------------------

#: Cada lado do teclado tem seu keysym, mas o pynput só conhece o modificador
#: genérico. ``Meta``/``Win`` aparecem em layouts e VMs diferentes.
MODIFICADORES: dict[str, str] = {
    "Control_L": "<ctrl>",
    "Control_R": "<ctrl>",
    "Alt_L": "<alt>",
    "Alt_R": "<alt>",
    "Shift_L": "<shift>",
    "Shift_R": "<shift>",
    "Super_L": "<cmd>",
    "Super_R": "<cmd>",
    "Win_L": "<cmd>",
    "Win_R": "<cmd>",
    "Meta_L": "<alt>",
    "Meta_R": "<alt>",
}

#: Ordem canônica. Dois atalhos com os mesmos modificadores em ordem diferente
#: são o mesmo atalho, e só comparando na mesma ordem dá para achar duplicata.
ORDEM_MODIFICADORES = ("<ctrl>", "<alt>", "<shift>", "<cmd>")

_NOMEADAS: dict[str, str] = {
    "space": "<space>",
    "Return": "<enter>",
    "KP_Enter": "<enter>",
    "Tab": "<tab>",
    "BackSpace": "<backspace>",
    "Delete": "<delete>",
    "KP_Delete": "<delete>",
    "Insert": "<insert>",
    "Home": "<home>",
    "End": "<end>",
    "Prior": "<page_up>",
    "Next": "<page_down>",
    "Up": "<up>",
    "Down": "<down>",
    "Left": "<left>",
    "Right": "<right>",
    "Escape": "<esc>",
    "Pause": "<pause>",
    "Print": "<print_screen>",
    "Caps_Lock": "<caps_lock>",
    "Num_Lock": "<num_lock>",
    "Scroll_Lock": "<scroll_lock>",
    "Menu": "<menu>",
}

#: O keysym vem por nome; o pynput quer o caractere.
_PONTUACAO: dict[str, str] = {
    "comma": ",",
    "period": ".",
    "slash": "/",
    "backslash": "\\",
    "semicolon": ";",
    "colon": ":",
    "apostrophe": "'",
    "quotedbl": '"',
    "bracketleft": "[",
    "bracketright": "]",
    "braceleft": "{",
    "braceright": "}",
    "minus": "-",
    "underscore": "_",
    "equal": "=",
    "plus": "+",
    "asterisk": "*",
    "grave": "`",
    "asciitilde": "~",
    "acute": "´",
    "ccedilla": "ç",
    "Ccedilla": "ç",
    "KP_Add": "+",
    "KP_Subtract": "-",
    "KP_Multiply": "*",
    "KP_Divide": "/",
    "KP_Decimal": ".",
}

_TECLA_F = re.compile(r"^F([1-9]|1[0-9]|2[0-4])$")
_TECLA_KP = re.compile(r"^KP_([0-9])$")

#: Como cada tecla aparece no keycap. Setas viram símbolo: cabe melhor e o
#: usuário reconhece na hora.
_ROTULOS: dict[str, str] = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "cmd": "Win",
    "space": "Espaço",
    "enter": "Enter",
    "esc": "Esc",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Del",
    "insert": "Ins",
    "home": "Home",
    "end": "End",
    "page_up": "PgUp",
    "page_down": "PgDn",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "caps_lock": "Caps",
    "num_lock": "Num",
    "scroll_lock": "Scroll",
    "print_screen": "PrtSc",
    "pause": "Pause",
    "menu": "Menu",
}


def modificador_de_keysym(keysym: str) -> str | None:
    """``"Control_L"`` -> ``"<ctrl>"``; ``None`` se não for modificador."""
    return MODIFICADORES.get(keysym)


def traduzir_keysym(keysym: str) -> str | None:
    """Keysym do tkinter -> tecla no formato do pynput.

    Devolve ``None`` para modificadores (que entram na combinação por outro
    caminho) e para teclas que o pynput não sabe nomear — melhor ignorar a
    tecla do que gravar um atalho que nunca vai disparar.
    """
    if not keysym or keysym in MODIFICADORES:
        return None
    if keysym in _NOMEADAS:
        return _NOMEADAS[keysym]
    if keysym in _PONTUACAO:
        return _PONTUACAO[keysym]
    combina = _TECLA_F.match(keysym)
    if combina:
        return f"<f{combina.group(1)}>"
    combina = _TECLA_KP.match(keysym)
    if combina:
        return combina.group(1)
    if len(keysym) == 1 and keysym.isprintable() and not keysym.isspace():
        return keysym.lower()
    return None


def montar_atalho(modificadores: Iterable[str], tecla: str) -> str:
    """``{"<alt>", "<ctrl>"}`` + ``"c"`` -> ``"<ctrl>+<alt>+c"``."""
    presentes = set(modificadores)
    ordenados = [m for m in ORDEM_MODIFICADORES if m in presentes]
    return "+".join([*ordenados, tecla])


def partes_do_atalho(combinacao: str) -> list[str]:
    return [parte for parte in (combinacao or "").split("+") if parte]


def teclas_legiveis(combinacao: str) -> list[str]:
    """``"<ctrl>+<alt>+c"`` -> ``["Ctrl", "Alt", "C"]``, um item por keycap."""
    rotulos = []
    for parte in partes_do_atalho(combinacao):
        nu = parte.strip("<>")
        rotulos.append(_ROTULOS.get(nu, nu.upper() if len(nu) == 1 else nu.capitalize()))
    return rotulos


def atalho_legivel(combinacao: str) -> str:
    """Uma linha só, para mensagem de erro: ``"Ctrl+Alt+C"``."""
    return "+".join(teclas_legiveis(combinacao))


def tem_modificador(combinacao: str) -> bool:
    """Atalho global sem modificador sequestra a tecla no sistema inteiro."""
    partes = partes_do_atalho(combinacao)
    return len(partes) >= 2 and any(p in ORDEM_MODIFICADORES for p in partes[:-1])


def normalizar_atalho(combinacao: str) -> str:
    """Põe os modificadores na ordem canônica e baixa a caixa.

    Sem isto, ``<alt>+<ctrl>+c`` e ``<ctrl>+<alt>+c`` passariam pela checagem
    de duplicidade como se fossem atalhos diferentes.
    """
    partes = [p.lower() for p in partes_do_atalho(combinacao)]
    if not partes:
        return ""
    modificadores = [p for p in partes[:-1] if p in ORDEM_MODIFICADORES]
    resto = [p for p in partes[:-1] if p not in ORDEM_MODIFICADORES]
    return montar_atalho(modificadores, "+".join([*resto, partes[-1]]))


# ---------------------------------------------------------------------------
# Keycaps
# ---------------------------------------------------------------------------

_KEYCAP_ALTURA = 22
_KEYCAP_RAIO = 7
_KEYCAP_ESPACO = 5
_KEYCAP_PADDING = 8


def largura_dos_keycaps(estilo: Estilo, teclas: Sequence[str], tamanho: int = 11) -> int:
    """Quanto espaço a fila de keycaps vai ocupar, em pixels de tela."""
    if not teclas:
        return 0
    total = estilo.px(_KEYCAP_ESPACO) * (len(teclas) - 1)
    for tecla in teclas:
        total += max(
            estilo.px(_KEYCAP_ALTURA),
            estilo.medir(tecla, tamanho, "medio") + estilo.px(_KEYCAP_PADDING) * 2,
        )
    return total


def desenhar_keycaps(
    canvas: tk.Canvas,
    estilo: Estilo,
    teclas: Sequence[str],
    x: int,
    centro_y: int,
    *,
    fundo: str,
    cor_tampa: str,
    cor_texto: str,
    contorno: str | None = None,
    tamanho: int = 11,
    tags: str | tuple[str, ...] = (),
) -> int:
    """Desenha ``[Ctrl] [Alt] [C]`` a partir de ``x``. Devolve a largura usada.

    Um retângulo por tecla, não uma etiqueta só com ``+``: é o que faz o olho
    ler "isto é uma tecla que eu aperto".
    """
    altura = estilo.px(_KEYCAP_ALTURA)
    topo = centro_y - altura // 2
    cursor = x
    for tecla in teclas:
        largura = max(
            altura, estilo.medir(tecla, tamanho, "medio") + estilo.px(_KEYCAP_PADDING) * 2
        )
        canvas.create_image(
            cursor,
            topo,
            anchor="nw",
            image=imagem_arredondada(
                canvas,
                largura,
                altura,
                estilo.px(_KEYCAP_RAIO),
                cor_tampa,
                fundo,
                contorno,
                max(1, estilo.px(1)),
            ),
            tags=tags,
        )
        canvas.create_text(
            cursor + largura // 2,
            centro_y,
            text=tecla,
            font=estilo.fonte(tamanho, "medio"),
            fill=cor_texto,
            tags=tags,
        )
        cursor += largura + estilo.px(_KEYCAP_ESPACO)
    return cursor - estilo.px(_KEYCAP_ESPACO) - x


# ---------------------------------------------------------------------------
# Base dos controles
# ---------------------------------------------------------------------------


class _Controle(tk.Canvas):
    """Canvas com fundo do tema, sem borda de foco e com ``after`` seguro.

    O ``fundo`` cai em ``superficie`` porque o lugar natural de um controle é
    dentro de um cartão. Quem o puser direto sobre a página passa o ``fundo``
    na mão — ele precisa bater com a cor de trás para a suavização compor.
    """

    def __init__(self, pai: tk.Misc, estilo: Estilo, largura: int, altura: int, **kw: Any):
        super().__init__(
            pai,
            width=largura,
            height=altura,
            bg=kw.pop("fundo", estilo.tema.superficie),
            highlightthickness=0,
            bd=0,
            takefocus=kw.pop("takefocus", False),
            **kw,
        )
        self.estilo = estilo
        self._agendado: str | None = None
        self.bind("<Destroy>", lambda _e: self._cancelar(), add="+")

    def _agendar(self, atraso: int, funcao: Callable[[], None]) -> None:
        self._cancelar()
        try:
            self._agendado = self.after(atraso, funcao)
        except tk.TclError:
            self._agendado = None

    def _cancelar(self) -> None:
        if self._agendado is not None:
            try:
                self.after_cancel(self._agendado)
            except (tk.TclError, ValueError):
                pass
            self._agendado = None

    @property
    def vivo(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False


# ---------------------------------------------------------------------------
# Interruptor
# ---------------------------------------------------------------------------


class Interruptor(_Controle):
    """O switch do iOS: trilho, bolinha e 120ms de deslizada.

    É o controle mais reconhecível da linguagem da Apple e o motivo de não
    existir nenhum ``Checkbutton`` neste aplicativo.
    """

    LARGURA = 42
    ALTURA = 26
    _DURACAO_MS = 120
    _QUADRO_MS = 16

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        valor: bool = False,
        ao_mudar: Callable[[bool], None] | None = None,
        fundo: str | None = None,
    ) -> None:
        largura = estilo.px(self.LARGURA)
        altura = estilo.px(self.ALTURA)
        super().__init__(
            pai, estilo, largura, altura, cursor="hand2", fundo=fundo or estilo.tema.superficie
        )
        self._valor = bool(valor)
        self._posicao = 1.0 if valor else 0.0
        self._ao_mudar = ao_mudar
        self.bind("<Button-1>", lambda _e: self.alternar())
        self._redesenhar()

    @property
    def valor(self) -> bool:
        return self._valor

    def definir(self, valor: bool, *, animar: bool = True, avisar: bool = False) -> None:
        valor = bool(valor)
        if valor == self._valor:
            return
        self._valor = valor
        if animar:
            self._animar(0)
        else:
            self._posicao = 1.0 if valor else 0.0
            self._redesenhar()
        if avisar and self._ao_mudar is not None:
            self._ao_mudar(self._valor)

    def alternar(self) -> str:
        self.definir(not self._valor, avisar=True)
        return "break"

    def _animar(self, decorrido: int) -> None:
        if not self.vivo:
            return
        fracao = min(1.0, decorrido / self._DURACAO_MS)
        # Suavização em S: sai devagar, corre no meio, encosta devagar.
        suave = fracao * fracao * (3 - 2 * fracao)
        alvo = 1.0 if self._valor else 0.0
        origem = 0.0 if self._valor else 1.0
        self._posicao = origem + (alvo - origem) * suave
        self._redesenhar()
        if fracao < 1.0:
            self._agendar(self._QUADRO_MS, lambda: self._animar(decorrido + self._QUADRO_MS))

    def _redesenhar(self) -> None:
        if not self.vivo:
            return
        tema = self.estilo.tema
        self.delete("all")
        self.create_image(
            0,
            0,
            anchor="nw",
            image=imagem_interruptor(
                self,
                self.estilo.px(self.LARGURA),
                self.estilo.px(self.ALTURA),
                self._posicao,
                misturar_cores(tema.pressionado, tema.destaque, self._posicao),
                "#FFFFFF",
                self["bg"],
            ),
        )


# ---------------------------------------------------------------------------
# Controle segmentado
# ---------------------------------------------------------------------------


class ControleSegmentado(_Controle):
    """Escolha entre 2 e 4 opções curtas, no lugar de um combobox.

    Combobox esconde as opções atrás de um clique; com três valores curtos
    ("Claro", "Escuro", "Sistema") mostrar tudo custa a mesma largura e o
    usuário decide sem abrir nada.
    """

    ALTURA = 30
    _RAIO = 11
    _PADDING = 13

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        opcoes: Sequence[tuple[str, str]],
        valor: str,
        ao_mudar: Callable[[str], None] | None = None,
        fundo: str | None = None,
        largura_minima: int = 0,
    ) -> None:
        self._opcoes = list(opcoes)
        rotulos = [rotulo for rotulo, _ in self._opcoes]
        largura_segmento = max(
            estilo.medir(r, 12, "medio") + estilo.px(self._PADDING) * 2 for r in rotulos
        )
        largura = max(estilo.px(largura_minima), largura_segmento * len(rotulos))
        altura = estilo.px(self.ALTURA)
        super().__init__(
            pai, estilo, largura, altura, cursor="hand2", fundo=fundo or estilo.tema.superficie
        )
        self._largura = largura
        self._altura = altura
        self._ao_mudar = ao_mudar
        self._indice = self._indice_de(valor)
        self.bind("<Button-1>", self._clicar)
        self._redesenhar()

    @property
    def valor(self) -> str:
        return self._opcoes[self._indice][1]

    def definir(self, valor: str, *, avisar: bool = False) -> None:
        indice = self._indice_de(valor)
        if indice == self._indice:
            return
        self._indice = indice
        self._redesenhar()
        if avisar and self._ao_mudar is not None:
            self._ao_mudar(self.valor)

    def _indice_de(self, valor: str) -> int:
        for posicao, (_rotulo, chave) in enumerate(self._opcoes):
            if chave == valor:
                return posicao
        return 0

    def _clicar(self, evento: tk.Event) -> str:
        passo = self._largura / len(self._opcoes)
        indice = min(len(self._opcoes) - 1, max(0, int(evento.x // passo)))
        if indice != self._indice:
            self._indice = indice
            self._redesenhar()
            if self._ao_mudar is not None:
                self._ao_mudar(self.valor)
        return "break"

    def _redesenhar(self) -> None:
        if not self.vivo:
            return
        tema = self.estilo.tema
        self.delete("all")
        self.create_image(
            0,
            0,
            anchor="nw",
            image=imagem_segmentado(
                self,
                self._largura,
                self._altura,
                len(self._opcoes),
                self._indice,
                self["bg"],
                tema.elevado,
                tema.segmento_ativo,
                tema.contorno,
                self.estilo.px(self._RAIO),
            ),
        )
        passo = self._largura / len(self._opcoes)
        for posicao, (rotulo, _chave) in enumerate(self._opcoes):
            ativo = posicao == self._indice
            self.create_text(
                round(passo * (posicao + 0.5)),
                self._altura // 2,
                text=rotulo,
                font=self.estilo.fonte(12, "medio" if ativo else "normal"),
                fill=tema.texto if ativo else tema.texto_secundario,
            )


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------


class Botao(_Controle):
    """Botão em cápsula. ``primario`` é o único item azul da tela.

    Cápsula e não retângulo de canto 8: nas referências não existe um único
    botão de canto quadrado, e a meia-altura é o que separa "botão" de "caixa".
    """

    ALTURA = 34
    _PADDING = 18

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        texto: str,
        comando: Callable[[], None],
        *,
        primario: bool = False,
        largura_minima: int = 76,
        fundo: str | None = None,
    ) -> None:
        largura = max(
            estilo.px(largura_minima),
            estilo.medir(texto, 13, "medio") + estilo.px(self._PADDING) * 2,
        )
        altura = estilo.px(self.ALTURA)
        super().__init__(
            pai, estilo, largura, altura, cursor="hand2", fundo=fundo or estilo.tema.superficie
        )
        self._texto = texto
        self._comando = comando
        self._primario = primario
        self._largura = largura
        self._altura = altura
        self._sob_o_mouse = False
        self.bind("<Button-1>", lambda _e: self._acionar())
        self.bind("<Enter>", lambda _e: self._realce(True))
        self.bind("<Leave>", lambda _e: self._realce(False))
        self._redesenhar()

    def _acionar(self) -> str:
        self._comando()
        return "break"

    def trocar_texto(self, texto: str) -> None:
        """Troca o rótulo sem refazer o botão.

        A largura continua a que foi calculada na criação, de propósito: um
        botão que encolhesse ao virar "Salvo" empurraria o vizinho e a fila
        inteira dançaria. Quem troca de texto reserva a largura no
        ``largura_minima``.
        """
        self._texto = texto
        self._redesenhar()

    def _realce(self, dentro: bool) -> None:
        self._sob_o_mouse = dentro
        self._redesenhar()

    def _redesenhar(self) -> None:
        if not self.vivo:
            return
        tema = self.estilo.tema
        if self._primario:
            cor = tema.destaque
            if self._sob_o_mouse:
                cor = misturar_cores(cor, "#FFFFFF" if tema.escuro else "#000000", 0.12)
            texto = tema.destaque_texto
        else:
            cor = tema.pressionado if self._sob_o_mouse else tema.elevado
            texto = tema.texto
        self.delete("all")
        self.create_image(
            0,
            0,
            anchor="nw",
            image=imagem_arredondada(
                self, self._largura, self._altura, self._altura // 2, cor, self["bg"]
            ),
        )
        self.create_text(
            self._largura // 2,
            self._altura // 2,
            text=self._texto,
            font=self.estilo.fonte(13, "medio"),
            fill=texto,
        )


class BotaoDiscreto(tk.Label):
    """Ação secundária escrita como texto azul, sem caixa em volta.

    Usado para "Esquecer aprendizado": é destrutivo, então não pode ficar tão
    convidativo quanto um botão cheio, mas precisa estar visível.
    """

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        texto: str,
        comando: Callable[[], None],
        *,
        perigo: bool = False,
        fundo: str | None = None,
    ) -> None:
        cor = estilo.tema.erro if perigo else estilo.tema.destaque
        super().__init__(
            pai,
            text=texto,
            font=estilo.fonte(13),
            fg=cor,
            bg=fundo or estilo.tema.superficie,
            cursor="hand2",
            bd=0,
            padx=0,
            pady=0,
        )
        self._cor = cor
        self.bind("<Button-1>", lambda _e: comando())
        self.bind("<Enter>", lambda _e: self.configure(fg=misturar_cores(cor, "#808080", 0.35)))
        self.bind("<Leave>", lambda _e: self.configure(fg=self._cor))

    def trocar_texto(self, texto: str) -> None:
        self.configure(text=texto)


# ---------------------------------------------------------------------------
# Gravador de atalho
# ---------------------------------------------------------------------------


#: Quantas teclas fecham a gravação sozinhas. Três é o formato dos atalhos
#: padrão (``Ctrl+Alt+C``) e o limite prático de um atalho global: com
#: quatro a mão já não alcança. Combinações de duas teclas se confirmam
#: com Enter.
_TETO_DE_TECLAS = 3


class GravadorDeAtalho(tk.Frame):
    """Campo que grava a combinação que o usuário apertar.

    Digitar ``<ctrl>+<alt>+c`` à mão exige saber a sintaxe do pynput e não
    perdoa erro de digitação. Aqui o usuário clica, aperta as teclas e vê o
    resultado como keycaps — e a validação (precisa de modificador, não pode
    ser reservado do Windows, não pode repetir outro campo) aparece inline,
    dentro do campo, sem caixa de diálogo.
    """

    ALTURA = 34
    _RAIO = 12
    _PULSO_MS = 90
    _CICLO_PULSO = 14

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        valor: str,
        *,
        ao_mudar: Callable[[str], None] | None = None,
        validar: Callable[[str], str | None] | None = None,
        largura: int = 152,
        fundo: str | None = None,
    ) -> None:
        fundo = fundo or estilo.tema.superficie
        super().__init__(pai, bg=fundo, bd=0, highlightthickness=0)
        self.estilo = estilo
        self._valor = normalizar_atalho(valor)
        self._ao_mudar = ao_mudar
        self._validar = validar
        self._largura = estilo.px(largura)
        self._altura = estilo.px(self.ALTURA)
        self._gravando = False
        self._modificadores: set[str] = set()
        self._tecla: str | None = None
        self._erro: str | None = None
        self._passo_pulso = 0
        self._agendado: str | None = None

        self._tela = tk.Canvas(
            self,
            width=self._largura,
            height=self._altura,
            bg=fundo,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            takefocus=True,
        )
        self._tela.pack(anchor="e")

        self._aviso = tk.Label(
            self,
            text="",
            font=estilo.fonte(11),
            fg=estilo.tema.erro,
            bg=fundo,
            anchor="e",
            justify="right",
            wraplength=self._largura + estilo.px(90),
        )

        self._tela.bind("<Button-1>", lambda _e: self.iniciar())
        self._tela.bind("<KeyPress>", self._ao_apertar)
        self._tela.bind("<KeyRelease>", self._ao_soltar)
        self._tela.bind("<FocusOut>", lambda _e: self.cancelar())
        self.bind("<Destroy>", lambda _e: self._parar_pulso(), add="+")
        self._redesenhar()

    # ------------------------------------------------------------------ API

    @property
    def valor(self) -> str:
        return self._valor

    @property
    def gravando(self) -> bool:
        return self._gravando

    def definir(self, valor: str) -> None:
        self._valor = normalizar_atalho(valor)
        self._redesenhar()

    def mostrar_erro(self, mensagem: str | None) -> None:
        """Aviso inline embaixo do campo. ``None`` esconde."""
        self._erro = mensagem
        if mensagem:
            self._aviso.configure(text=mensagem)
            self._aviso.pack(anchor="e", pady=(self.estilo.px(4), 0))
        else:
            self._aviso.pack_forget()
        self._redesenhar()

    def iniciar(self) -> str:
        if self._gravando:
            return "break"
        self._gravando = True
        self._modificadores.clear()
        self._tecla = None
        self.mostrar_erro(None)
        self._tela.focus_set()
        self._passo_pulso = 0
        self._pulsar()
        return "break"

    def cancelar(self) -> None:
        """Esc ou perda de foco: mantém o atalho anterior, sem drama."""
        if not self._gravando:
            return
        self._gravando = False
        self._modificadores.clear()
        self._tecla = None
        self._parar_pulso()
        self._redesenhar()

    # -------------------------------------------------------------- teclado

    def _ao_apertar(self, evento: tk.Event) -> str:
        if not self._gravando:
            return ""
        if evento.keysym == "Escape":
            self.cancelar()
            return "break"
        if evento.keysym in ("Return", "KP_Enter"):
            # Enter fecha a gravação com o que já foi apertado. É a saída para
            # combinações de duas teclas, que nunca chegam ao teto de três.
            if self._tecla is not None:
                self._confirmar(montar_atalho(self._modificadores, self._tecla))
            else:
                self.mostrar_erro("Aperte também a tecla final, além dos modificadores.")
            return "break"

        modificador = modificador_de_keysym(evento.keysym)
        if modificador is not None:
            self._modificadores.add(modificador)
        else:
            tecla = traduzir_keysym(evento.keysym)
            if tecla is not None:
                self._tecla = tecla
        self._redesenhar()

        if self._tecla is not None and self._total_de_teclas() >= _TETO_DE_TECLAS:
            self._confirmar(montar_atalho(self._modificadores, self._tecla))

        # Enquanto grava, NENHUMA tecla escapa: Tab tiraria o foco do campo no
        # meio da gravação e as setas andariam pela janela.
        return "break"

    def _total_de_teclas(self) -> int:
        return len(self._modificadores) + (1 if self._tecla is not None else 0)

    def _ao_soltar(self, _evento: tk.Event) -> str:
        """Soltar tecla não faz nada — de propósito.

        Antes a gravação fechava no primeiro ``KeyRelease``. Quem soltasse o
        Ctrl uma fração antes de apertar a terceira tecla gravava só duas, e
        montar ``Ctrl+Alt+C`` virava sorte. Agora a gravação só fecha no teto
        de três teclas ou no Enter, e o usuário pode soltar e reapertar à
        vontade enquanto monta a combinação.
        """
        return "break" if self._gravando else ""

    def _confirmar(self, combinacao: str) -> None:
        self._gravando = False
        self._modificadores.clear()
        self._tecla = None
        self._parar_pulso()

        mensagem = None
        if not tem_modificador(combinacao):
            mensagem = "Use pelo menos Ctrl, Alt ou Shift junto."
        elif self._validar is not None:
            mensagem = self._validar(combinacao)

        if mensagem:
            self.mostrar_erro(mensagem)
            self._redesenhar()
            return

        self._valor = combinacao
        self.mostrar_erro(None)
        self._redesenhar()
        if self._ao_mudar is not None:
            self._ao_mudar(combinacao)

    # ---------------------------------------------------------------- pulso

    def _pulsar(self) -> None:
        if not self._gravando:
            return
        self._passo_pulso = (self._passo_pulso + 1) % self._CICLO_PULSO
        self._redesenhar()
        try:
            self._agendado = self.after(self._PULSO_MS, self._pulsar)
        except tk.TclError:
            self._agendado = None

    def _parar_pulso(self) -> None:
        if self._agendado is not None:
            try:
                self.after_cancel(self._agendado)
            except (tk.TclError, ValueError):
                pass
            self._agendado = None

    def _intensidade_do_pulso(self) -> float:
        """Triângulo de 0 a 1 e de volta — respiração, não pisca-pisca."""
        metade = self._CICLO_PULSO / 2
        passo = self._passo_pulso
        return (passo / metade) if passo <= metade else (2 - passo / metade)

    # -------------------------------------------------------------- desenho

    def _redesenhar(self) -> None:
        try:
            if not self._tela.winfo_exists():
                return
        except tk.TclError:
            return
        tema = self.estilo.tema
        tela = self._tela
        tela.delete("all")

        if self._gravando:
            intensidade = self._intensidade_do_pulso()
            preenchimento = misturar_cores(tema.elevado, tema.destaque_suave, intensidade)
            contorno = misturar_cores(
                misturar_cores(tema.destaque, tema.superficie, 0.45),
                tema.destaque,
                intensidade,
            )
            espessura = 2
        elif self._erro:
            preenchimento = tema.elevado
            contorno = tema.erro
            espessura = 1
        else:
            preenchimento = tema.elevado
            contorno = tema.contorno
            espessura = 1

        tela.create_image(
            0,
            0,
            anchor="nw",
            image=imagem_arredondada(
                tela,
                self._largura,
                self._altura,
                self.estilo.px(self._RAIO),
                preenchimento,
                tela["bg"],
                contorno,
                max(1, self.estilo.px(espessura)),
            ),
        )

        centro_y = self._altura // 2
        teclas = self._teclas_visiveis()
        if not teclas:
            tela.create_text(
                self._largura // 2,
                centro_y,
                text="Pressione as teclas — Enter salva",
                font=self.estilo.fonte(12),
                fill=tema.destaque if self._gravando else tema.texto_terciario,
            )
            return

        # Alinhados à esquerda, não centralizados: os três campos começam com
        # os mesmos modificadores, e alinhar faz [Ctrl] e [Alt] baterem entre
        # as linhas em vez de dançarem conforme o tamanho da última tecla.
        desenhar_keycaps(
            tela,
            self.estilo,
            teclas,
            self.estilo.px(10),
            centro_y,
            fundo=preenchimento,
            cor_tampa=tema.superficie,
            cor_texto=tema.destaque if self._gravando else tema.texto,
            contorno=tema.contorno,
        )

    def _teclas_visiveis(self) -> list[str]:
        if self._gravando:
            ao_vivo = [m for m in ORDEM_MODIFICADORES if m in self._modificadores]
            if self._tecla:
                ao_vivo.append(self._tecla)
            return teclas_legiveis("+".join(ao_vivo)) if ao_vivo else []
        return teclas_legiveis(self._valor)


# ---------------------------------------------------------------------------
# Peças de layout
# ---------------------------------------------------------------------------


class Cartao(tk.Frame):
    """Cartão branco flutuando sobre a página cinza.

    Empacote os filhos em ``.conteudo``, nunca no cartão em si: o cartão
    reserva as bordas para a sombra e para o padding, e ``.conteudo`` é o
    frame já chapado na cor certa onde o layout de verdade acontece.

    A sombra é uma imagem num ``Canvas`` esticado por baixo de tudo. O padding
    do conteúdo é maior que o raio de propósito — é o que mantém os quatro
    cantos arredondados visíveis, já que o frame do conteúdo é retangular e
    cobriria a curva se encostasse nela.
    """

    #: Folga em volta do cartão onde a sombra se espalha. Precisa comportar o
    #: desfoque inteiro, ou o borrão sai cortado num degrau visível.
    MARGEM = 14
    PADDING = 18
    RAIO = 16
    DESFOQUE = 14
    DESLOCAMENTO = 3

    def __init__(
        self,
        pai: tk.Misc,
        estilo: Estilo,
        *,
        fundo: str | None = None,
        padding: int | None = None,
        raio: int | None = None,
    ) -> None:
        fundo = fundo or estilo.tema.fundo
        super().__init__(pai, bg=fundo, bd=0, highlightthickness=0)
        self.estilo = estilo
        self._fundo = fundo
        self._raio = self.RAIO if raio is None else raio
        self._tamanho: tuple[int, int] = (0, 0)

        self._tela = tk.Canvas(
            self, bg=fundo, highlightthickness=0, bd=0, takefocus=False
        )
        self._tela.place(x=0, y=0, relwidth=1, relheight=1)
        # ``Canvas.lower`` é o ``tag_lower`` dos itens, não o da pilha de
        # widgets; para rebaixar o canvas em si é preciso o método do ``Misc``.
        tk.Misc.lower(self._tela)

        self.conteudo = tk.Frame(
            self, bg=estilo.tema.superficie, bd=0, highlightthickness=0
        )
        recuo = estilo.px(self.MARGEM + (self.PADDING if padding is None else padding))
        self.conteudo.pack(fill="both", expand=True, padx=recuo, pady=recuo)

        self.bind("<Configure>", self._ao_redimensionar, add="+")

    def _ao_redimensionar(self, evento: tk.Event) -> None:
        # Sem a guarda o desenho dispara outro <Configure> e o cartão entra em
        # laço enquanto a janela está viva.
        if (evento.width, evento.height) == self._tamanho:
            return
        self._tamanho = (evento.width, evento.height)
        self._redesenhar()

    def _redesenhar(self) -> None:
        largura, altura = self._tamanho
        if largura <= 1 or altura <= 1:
            return
        tema = self.estilo.tema
        self._tela.delete("all")
        self._tela.create_image(
            0,
            0,
            anchor="nw",
            image=imagem_cartao(
                self._tela,
                largura,
                altura,
                self.estilo.px(self._raio),
                tema.superficie,
                self._fundo,
                margem=self.estilo.px(self.MARGEM),
                desfoque=self.estilo.px(self.DESFOQUE),
                deslocamento=self.estilo.px(self.DESLOCAMENTO),
                cor_sombra=tema.sombra,
                opacidade=tema.sombra_opacidade,
            ),
        )


def hairline(pai: tk.Misc, estilo: Estilo) -> tk.Frame:
    """Separador de 1px. Nunca cerca um bloco — só divide dois."""
    return tk.Frame(
        pai, height=max(1, estilo.px(1)), bg=estilo.tema.hairline, bd=0, highlightthickness=0
    )


def titulo_secao(
    pai: tk.Misc, estilo: Estilo, texto: str, fundo: str | None = None
) -> tk.Label:
    return tk.Label(
        pai,
        text=texto,
        font=estilo.fonte(15, "medio"),
        fg=estilo.tema.texto,
        bg=fundo or estilo.tema.superficie,
        anchor="w",
    )


def rotulo(
    pai: tk.Misc,
    estilo: Estilo,
    texto: str,
    *,
    tamanho: int = 13,
    cor: str | None = None,
    fundo: str | None = None,
    quebra: int = 0,
) -> tk.Label:
    return tk.Label(
        pai,
        text=texto,
        font=estilo.fonte(tamanho),
        fg=cor or estilo.tema.texto,
        bg=fundo or estilo.tema.superficie,
        anchor="w",
        justify="left",
        wraplength=quebra,
    )


__all__ = [
    "MODIFICADORES",
    "ORDEM_MODIFICADORES",
    "Botao",
    "BotaoDiscreto",
    "Cartao",
    "ControleSegmentado",
    "GravadorDeAtalho",
    "Interruptor",
    "atalho_legivel",
    "desenhar_keycaps",
    "hairline",
    "imagem_arredondada",
    "imagem_cartao",
    "imagem_interruptor",
    "imagem_segmentado",
    "largura_dos_keycaps",
    "modificador_de_keysym",
    "montar_atalho",
    "normalizar_atalho",
    "partes_do_atalho",
    "rotulo",
    "teclas_legiveis",
    "tem_modificador",
    "titulo_secao",
    "traduzir_keysym",
]
