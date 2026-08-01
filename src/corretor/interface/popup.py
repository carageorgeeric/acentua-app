"""Popup de sugestões: a única janela que o usuário vê no fluxo normal.

Desenho guiado pelo pedido do usuário: "só a palavra corrigida, ou no máximo
3 sugestões" e "não precisar abrir um app". Então é uma janela sem barra de
título, do tamanho do conteúdo, colada no cursor, que morre no primeiro
Enter/Esc/clique fora.

O conteúdo inteiro é um ``Canvas``, não uma pilha de ``Frame``/``Label``: a
linha selecionada é uma pílula de cantos arredondados, e ``Frame`` no Tk é
sempre retangular. Os cantos da janela vêm de ``moldar_arredondada``: o
compositor do Windows só sabe arredondar no raio fixo dele, curto demais para
a janela ler como cartão.

A janela INTEIRA é o cartão: o fundo dela é ``superficie``, não ``fundo`` —
não existe página cinza atrás de um popup, existe o desktop. Pela mesma razão
a sombra não é desenhada aqui: sem saber o que está atrás, não há contra o que
compor o borrão. Quem dá o relevo é o compositor do Windows, de graça.

Dois modos, a mesma janela:

* :meth:`PopupSugestoes.mostrar` — uma pergunta só, sobre a palavra
  selecionada. É o ``Ctrl+Alt+S``.
* :meth:`PopupSugestoes.perguntar` — uma FILA de dúvidas sobre uma frase
  inteira, com o trecho da frase no cabeçalho e um contador. A janela não
  fecha entre uma pergunta e outra: fechar devolveria o foco para o app do
  usuário e reabrir o roubaria de novo, e três piscadas de foco seguidas são
  o suficiente para o Windows mandar a janela para trás.

Recebe o ``root`` do tkinter no construtor — não cria ``Tk()``. Veja o
modelo de threads em ``corretor.interface``.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable, Sequence

from ..tipos import Duvida, Sugestao
from . import (
    Estilo,
    arredondar_janela,
    encaixar_na_tela,
    focar_janela,
    janela_em_foco,
    moldar_arredondada,
    posicao_do_cursor,
)
from .componentes import imagem_arredondada

#: O usuário pediu no máximo 3. Mais que isso vira leitura, não escolha.
MAX_SUGESTOES = 3

#: Deslocamento em relação ao cursor: longe o bastante para não ficar embaixo
#: da seta do mouse, perto o bastante para o olho não precisar procurar.
_DESLOCAMENTO = (14, 18)

#: Depois de ``focus_force`` o Windows manda um FocusOut espúrio enquanto a
#: ativação assenta. Ignoramos perdas de foco nesse intervalo, senão o popup
#: se fecha sozinho no instante em que aparece.
_CARENCIA_FOCO = 0.25

#: Largura mínima: com uma sugestão curta ("é") a janela viraria um quadrado
#: de 40px que o olho não acha.
_LARGURA_MINIMA = 220

#: Teto de largura. O cabeçalho mostra um pedaço da frase e uma seleção longa
#: esticaria a janela de ponta a ponta do monitor; passando daqui, o trecho é
#: encurtado com reticências em vez de a janela crescer.
_LARGURA_MAXIMA = 460

#: Folga entre fechar o popup e executar a escolha. O popup está com o foco;
#: o app-alvo precisa recuperá-lo antes do Ctrl+V, ou a colagem se perde.
_FOLGA_ANTES_DA_ESCOLHA_MS = 60

# Medidas do cartão, em pixels de layout (escalados por ``Estilo.px``).
#: Respiro entre a borda da janela e a pílula. Precisa ser maior que o raio
#: com que o compositor recorta a janela, ou a pílula encosta na curva.
_MARGEM = 10
_ALTURA_LINHA = 40
_RECUO = 12
_KEYCAP = 22
_ESPACO_APOS_KEYCAP = 12
#: Distância mínima entre a palavra e o percentual de confiança. São dois
#: níveis de leitura diferentes e não podem parecer uma coisa só.
_ESPACO_ANTES_DA_CONFIANCA = 20
#: Faixa da frase, acima das opções. Só existe no modo fila.
_ALTURA_CABECALHO = 40
#: Respiro entre o contador ("2/3") e o trecho da frase, para os dois não
#: colarem quando a frase é longa.
_ESPACO_ANTES_DO_CONTADOR = 14

#: Corpo da sugestão e legenda da confiança. Dois passos de tamanho e um de
#: cor: é o que separa "a palavra que eu vou colar" de "o quanto o motor
#: confia nela".
_TAMANHO_PALAVRA = 14
_TAMANHO_LEGENDA = 11

#: Raio dos cantos da janela, em pixels de layout. Vem de ``moldar_arredondada``
#: e não do DWM: o atributo do compositor é travado em ~8px, que numa janela de
#: 220x150 ainda lê como retângulo.
_RAIO_JANELA = 16

#: Fade de entrada. 120ms é o suficiente para o olho não levar susto e curto
#: demais para alguém perceber que esperou.
_DURACAO_FADE_MS = 120
_QUADRO_FADE_MS = 20


class PopupSugestoes:
    """Lista de até 3 sugestões, navegável só pelo teclado.

    O ``Toplevel`` é criado uma vez e reaproveitado (``withdraw`` /
    ``deiconify``). Criar e destruir janela a cada correção pisca na tela e,
    em sessões longas, vaza handles do Windows.
    """

    def __init__(self, root: tk.Tk, tema: str = "sistema") -> None:
        self._raiz = root
        self._preferencia_de_tema = tema
        self._estilo: Estilo | None = None
        self._janela: tk.Toplevel | None = None
        self._tela: tk.Canvas | None = None
        self._sugestoes: list[Sugestao] = []
        self._indice = 0
        self._visivel = False
        self._ao_escolher: Callable[[Sugestao], None] | None = None
        self._ao_cancelar: Callable[[], None] | None = None
        self._hwnd_anterior = 0
        self._carencia_ate = 0.0
        self._largura = 0
        self._altura = 0
        self._fade: str | None = None
        # Modo fila (revisão de frase). Vazio no modo de pergunta única.
        self._fila: tuple[Duvida, ...] = ()
        self._pergunta = 0
        self._escolhas: dict[int, str] = {}
        self._ao_concluir: Callable[[dict[int, str]], None] | None = None
        self._antes = ""
        self._depois = ""
        self._ancora: tuple[int, int] | None = None

    @property
    def visivel(self) -> bool:
        return self._visivel

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def definir_tema(self, preferencia: str) -> None:
        """Troca claro/escuro/sistema. Vale a partir do próximo ``mostrar``."""
        if preferencia != self._preferencia_de_tema:
            self._preferencia_de_tema = preferencia
            self._estilo = None

    def mostrar(
        self,
        sugestoes: list[Sugestao],
        ao_escolher: Callable[[Sugestao], None],
        ao_cancelar: Callable[[], None] | None = None,
    ) -> None:
        """Abre o popup perto do cursor com as sugestões dadas.

        Lista vazia é tratada como cancelamento imediato: não faz sentido
        mostrar uma janela sem opção.
        """
        self._sugestoes = list(sugestoes)[:MAX_SUGESTOES]
        if not self._sugestoes:
            self.fechar()
            if ao_cancelar is not None:
                ao_cancelar()
            return

        self._fila = ()
        self._ao_concluir = None
        self._ao_escolher = ao_escolher
        self._ao_cancelar = ao_cancelar
        self._antes = self._depois = ""
        self._abrir()

    def perguntar(
        self,
        duvidas: Sequence[Duvida],
        ao_concluir: Callable[[dict[int, str]], None],
    ) -> None:
        """Percorre uma fila de dúvidas sobre uma frase e devolve as escolhas.

        ``ao_concluir`` recebe ``{indice da alteração: grafia escolhida}`` e é
        chamado exatamente uma vez, tanto no fim natural da fila quanto quando
        o usuário desiste no meio. Desistir NÃO cancela a correção: as dúvidas
        que sobraram ficam com a grafia automática, que é justamente o que
        aconteceria se o popup nunca tivesse aparecido. Assim ``Esc`` é sempre
        "tanto faz, pode colar" — nunca "perdi o que eu tinha escrito".
        """
        self._fila = tuple(duvidas)
        self._escolhas = {}
        self._pergunta = 0
        self._ao_concluir = ao_concluir
        self._ao_escolher = None
        self._ao_cancelar = None

        if not self._fila:
            ao_concluir({})
            return

        self._carregar_pergunta()
        self._abrir()

    def _carregar_pergunta(self) -> None:
        duvida = self._fila[self._pergunta]
        self._sugestoes = list(duvida.sugestoes)[:MAX_SUGESTOES]
        self._antes, self._depois = duvida.antes, duvida.depois

    def _abrir(self) -> None:
        """Mostra a janela com o conteúdo já definido e rouba o foco.

        Só é chamado ao ABRIR. Trocar de pergunta dentro da fila passa por
        :meth:`_redesenhar_pergunta`, que não mexe em foco nem em fade.
        """
        self._indice = 0
        self._ancora = None
        self._hwnd_anterior = janela_em_foco()

        janela = self._garantir_janela()
        self._medir()
        self._posicionar(janela)
        self._desenhar()

        janela.attributes("-alpha", 0.0)
        janela.deiconify()
        janela.lift()
        janela.attributes("-topmost", True)
        self._moldar()
        janela.focus_force()
        self._visivel = True
        self._carencia_ate = time.monotonic() + _CARENCIA_FOCO
        self._surgir(0)

    def _redesenhar_pergunta(self) -> None:
        """Troca o conteúdo sem fechar: a janela só muda de tamanho e de texto."""
        self._indice = 0
        self._medir()
        if self._janela is not None:
            self._posicionar(self._janela)
            # A região é fixa no tamanho de quando foi criada, e cada pergunta
            # muda a altura da janela: sem remoldar, a pergunta seguinte sai
            # com o recorte da anterior e aparece cortada.
            self._moldar()
        self._desenhar()

    def _moldar(self) -> None:
        """Arredonda os cantos da janela no tamanho que ela tem agora.

        Cai no arredondamento do DWM se o recorte não pegar (Windows antigo,
        outro sistema): canto pequeno é feio, janela sem canto nenhum não é.
        """
        janela = self._janela
        if janela is None:
            return
        raio = self._garantir_estilo().px(_RAIO_JANELA)
        if not moldar_arredondada(janela, raio):
            arredondar_janela(janela)

    def fechar(self) -> None:
        """Esconde o popup e devolve o foco para o app do usuário.

        Não dispara ``ao_cancelar``: quem cancela é o Esc / a perda de foco.
        """
        if not self._visivel:
            return
        self._visivel = False
        self._cancelar_fade()
        if self._janela is not None:
            self._janela.withdraw()
        focar_janela(self._hwnd_anterior)

    def destruir(self) -> None:
        """Some com o ``Toplevel`` de vez (encerramento do app)."""
        self._visivel = False
        self._cancelar_fade()
        if self._janela is not None:
            self._janela.destroy()
            self._janela = None
            self._tela = None

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _garantir_estilo(self) -> Estilo:
        if self._estilo is None:
            self._estilo = Estilo(self._raiz, self._preferencia_de_tema)
        return self._estilo

    def _garantir_janela(self) -> tk.Toplevel:
        if self._janela is not None:
            superficie = self._garantir_estilo().tema.superficie
            self._janela.configure(bg=superficie)
            if self._tela is not None:
                self._tela.configure(bg=superficie)
            return self._janela

        estilo = self._garantir_estilo()
        janela = tk.Toplevel(self._raiz)
        janela.withdraw()
        janela.overrideredirect(True)
        janela.attributes("-topmost", True)
        janela.configure(bg=estilo.tema.superficie)
        janela.resizable(False, False)

        self._tela = tk.Canvas(
            janela,
            bg=estilo.tema.superficie,
            highlightthickness=0,
            bd=0,
            takefocus=False,
        )
        self._tela.pack(fill="both", expand=True)
        self._tela.bind("<Button-1>", self._ao_clicar)
        self._tela.bind("<Motion>", self._ao_mover_mouse)

        for sequencia, tratador in (
            ("<Escape>", self._ao_esc),
            ("<Return>", self._ao_enter),
            ("<KP_Enter>", self._ao_enter),
            ("<Up>", lambda _e: self._mover(-1)),
            ("<Down>", lambda _e: self._mover(1)),
            ("<Tab>", lambda _e: self._mover(1)),
            ("<FocusOut>", self._ao_perder_foco),
        ):
            janela.bind(sequencia, tratador)
        for numero in range(1, MAX_SUGESTOES + 1):
            janela.bind(str(numero), self._atalho_numerico(numero - 1))
            janela.bind(f"<KP_{numero}>", self._atalho_numerico(numero - 1))

        self._janela = janela
        return janela

    @property
    def _tem_cabecalho(self) -> bool:
        return bool(self._fila)

    def _medir(self) -> None:
        """Calcula a caixa a partir do texto: a janela é do tamanho do conteúdo."""
        estilo = self._garantir_estilo()
        px = estilo.px
        # Medido no peso "medio": é o da linha selecionada, e a janela não pode
        # ficar apertada justo na linha em que o olho está.
        palavras = max(
            estilo.medir(s.palavra, _TAMANHO_PALAVRA, "medio") for s in self._sugestoes
        )
        confiancas = max(
            (
                estilo.medir(self._rotulo_confianca(s), _TAMANHO_LEGENDA)
                for s in self._sugestoes
            ),
            default=0,
        )
        texto_x = px(_MARGEM + _RECUO + _KEYCAP + _ESPACO_APOS_KEYCAP)
        largura = texto_x + palavras + px(_ESPACO_ANTES_DA_CONFIANCA) + confiancas
        largura += px(_MARGEM + _RECUO)

        altura = px(_MARGEM) * 2 + px(_ALTURA_LINHA) * len(self._sugestoes)
        if self._tem_cabecalho:
            largura = max(largura, self._encolher_cabecalho())
            altura += px(_ALTURA_CABECALHO)

        self._largura = min(px(_LARGURA_MAXIMA), max(px(_LARGURA_MINIMA), largura))
        self._altura = altura

    def _encolher_cabecalho(self) -> int:
        """Apara ``antes``/``depois`` até o cabeçalho caber, e devolve a largura.

        A frase é medida com a sugestão MAIS LARGA no lugar da palavra, não com
        a que está destacada agora: navegar com as setas troca a palavra do
        cabeçalho, e medir a atual faria a janela mudar de tamanho a cada seta.
        """
        estilo = self._garantir_estilo()
        px = estilo.px
        fixo = px(_MARGEM + _RECUO) * 2 + px(_ESPACO_ANTES_DO_CONTADOR)
        fixo += estilo.medir(self._rotulo_do_contador(), _TAMANHO_LEGENDA)
        fixo += max(estilo.medir(s.palavra, 12, "medio") for s in self._sugestoes)
        disponivel = px(_LARGURA_MAXIMA) - fixo

        while self._antes or self._depois:
            largura = estilo.medir(self._antes, 12) + estilo.medir(self._depois, 12)
            if largura <= disponivel:
                break
            # Corta do lado mais longo: a frase encolhe pelas duas pontas em
            # vez de sumir só à esquerda.
            if len(self._antes) >= len(self._depois):
                self._antes = "…" + self._antes[2:] if len(self._antes) > 2 else ""
            else:
                self._depois = self._depois[:-2] + "…" if len(self._depois) > 2 else ""

        return fixo + estilo.medir(self._antes, 12) + estilo.medir(self._depois, 12)

    def _posicionar(self, janela: tk.Toplevel) -> None:
        # Durante uma fila a âncora é congelada na abertura: reposicionar a
        # cada pergunta faria o cartão perseguir o mouse, e o usuário responde
        # com o teclado enquanto a mão nem está no mouse.
        if self._ancora is None:
            cx, cy = posicao_do_cursor(self._raiz)
            self._ancora = (cx + _DESLOCAMENTO[0], cy + _DESLOCAMENTO[1])
        x, y = encaixar_na_tela(
            self._raiz, self._ancora[0], self._ancora[1], self._largura, self._altura
        )
        janela.geometry(f"{self._largura}x{self._altura}+{x}+{y}")
        if self._tela is not None:
            self._tela.configure(width=self._largura, height=self._altura)

    def _desenhar(self) -> None:
        """Redesenha as três linhas. Barato: são no máximo 12 itens no Canvas."""
        tela = self._tela
        estilo = self._garantir_estilo()
        if tela is None:
            return
        tema = estilo.tema
        px = estilo.px
        tela.delete("all")

        margem = px(_MARGEM)
        altura_linha = px(_ALTURA_LINHA)
        keycap = px(_KEYCAP)
        topo_das_linhas = margem + (px(_ALTURA_CABECALHO) if self._tem_cabecalho else 0)

        if self._tem_cabecalho:
            self._desenhar_cabecalho(tela, estilo)

        for posicao, sugestao in enumerate(self._sugestoes):
            escolhida = posicao == self._indice
            topo = topo_das_linhas + posicao * altura_linha
            centro = topo + altura_linha // 2

            # A pílula da seleção é um azul lavado, não o azul chapado: numa
            # linha inteira o destaque cheio pesa como um banner e ainda
            # obrigaria a inverter a cor de todo o texto. Quem carrega o azul
            # de verdade é só o keycap, do tamanho de uma unha.
            if escolhida:
                tela.create_image(
                    margem,
                    topo,
                    anchor="nw",
                    image=imagem_arredondada(
                        tela,
                        self._largura - margem * 2,
                        altura_linha,
                        altura_linha // 2,
                        tema.destaque_suave,
                        tema.superficie,
                    ),
                )

            fundo_linha = tema.destaque_suave if escolhida else tema.superficie
            cor_tampa = tema.destaque if escolhida else tema.elevado
            tela.create_image(
                margem + px(_RECUO),
                centro - keycap // 2,
                anchor="nw",
                image=imagem_arredondada(
                    tela, keycap, keycap, px(7), cor_tampa, fundo_linha
                ),
            )
            tela.create_text(
                margem + px(_RECUO) + keycap // 2,
                centro,
                text=str(posicao + 1),
                font=estilo.fonte(_TAMANHO_LEGENDA, "medio"),
                fill=tema.destaque_texto if escolhida else tema.texto_secundario,
            )
            tela.create_text(
                margem + px(_RECUO + _KEYCAP + _ESPACO_APOS_KEYCAP),
                centro,
                anchor="w",
                text=sugestao.palavra,
                font=estilo.fonte(
                    _TAMANHO_PALAVRA, "medio" if escolhida else "normal"
                ),
                fill=tema.texto,
            )
            confianca = self._rotulo_confianca(sugestao)
            if confianca:
                tela.create_text(
                    self._largura - margem - px(_RECUO),
                    centro,
                    anchor="e",
                    text=confianca,
                    font=estilo.fonte(_TAMANHO_LEGENDA),
                    fill=(
                        tema.texto_secundario if escolhida else tema.texto_terciario
                    ),
                )

    def _desenhar_cabecalho(self, tela: tk.Canvas, estilo: Estilo) -> None:
        """A frase com a opção destacada no lugar, e o contador à direita.

        A palavra desenhada é a que está selecionada AGORA, não a original: as
        setas fazem a frase mudar embaixo do olho, e é assim que o usuário
        decide sem precisar montar a frase de cabeça.
        """
        tema = estilo.tema
        px = estilo.px
        base = px(_MARGEM) + px(_ALTURA_CABECALHO)
        centro = base // 2
        x = px(_MARGEM + _RECUO)

        palavra = self._sugestoes[self._indice].palavra
        trechos = (
            (self._antes, "normal", tema.texto_secundario),
            (palavra, "medio", tema.destaque),
            (self._depois, "normal", tema.texto_secundario),
        )
        for texto, peso, cor in trechos:
            if not texto:
                continue
            tela.create_text(
                x, centro, anchor="w", text=texto, font=estilo.fonte(12, peso), fill=cor
            )
            x += estilo.medir(texto, 12, peso)

        tela.create_text(
            self._largura - px(_MARGEM + _RECUO),
            centro,
            anchor="e",
            text=self._rotulo_do_contador(),
            font=estilo.fonte(_TAMANHO_LEGENDA),
            fill=tema.texto_terciario,
        )
        # Hairline separando a frase das opções. Vai de margem a margem, não de
        # ponta a ponta: encostar na borda arredondada deixa o traço cortado.
        tela.create_line(
            px(_MARGEM + _RECUO),
            base,
            self._largura - px(_MARGEM + _RECUO),
            base,
            fill=tema.hairline,
        )

    def _rotulo_do_contador(self) -> str:
        """``"2/3"``, ou vazio quando a fila tem uma pergunta só."""
        if len(self._fila) < 2:
            return ""
        return f"{self._pergunta + 1}/{len(self._fila)}"

    @staticmethod
    def _rotulo_confianca(sugestao: Sugestao) -> str:
        if sugestao.confianca >= 0.999:
            return ""
        return f"{round(sugestao.confianca * 100)}%"

    # ------------------------------------------------------------------
    # Fade
    # ------------------------------------------------------------------

    def _surgir(self, decorrido: int) -> None:
        if not self._visivel or self._janela is None:
            return
        fracao = min(1.0, decorrido / _DURACAO_FADE_MS)
        try:
            self._janela.attributes("-alpha", fracao)
        except tk.TclError:
            return
        if fracao < 1.0:
            self._fade = self._raiz.after(
                _QUADRO_FADE_MS, self._surgir, decorrido + _QUADRO_FADE_MS
            )
        else:
            self._fade = None

    def _cancelar_fade(self) -> None:
        if self._fade is not None:
            try:
                self._raiz.after_cancel(self._fade)
            except (tk.TclError, ValueError):
                pass
            self._fade = None

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def _linha_em(self, y: int) -> int | None:
        estilo = self._garantir_estilo()
        topo = estilo.px(_MARGEM)
        if self._tem_cabecalho:
            topo += estilo.px(_ALTURA_CABECALHO)
        relativo = y - topo
        if relativo < 0:
            return None
        posicao = relativo // estilo.px(_ALTURA_LINHA)
        return posicao if 0 <= posicao < len(self._sugestoes) else None

    def _ao_clicar(self, evento: tk.Event) -> str:
        posicao = self._linha_em(evento.y)
        if posicao is not None:
            self._escolher(posicao)
        return "break"

    def _ao_mover_mouse(self, evento: tk.Event) -> None:
        posicao = self._linha_em(evento.y)
        if self._visivel and posicao is not None and posicao != self._indice:
            self._indice = posicao
            self._desenhar()

    def _atalho_numerico(self, posicao: int) -> Callable[[tk.Event], str]:
        def tratar(_evento: tk.Event) -> str:
            self._escolher(posicao)
            return "break"

        return tratar

    def _mover(self, passo: int) -> str:
        if self._visivel and self._sugestoes:
            self._indice = (self._indice + passo) % len(self._sugestoes)
            self._desenhar()
        return "break"

    def _ao_enter(self, _evento: tk.Event) -> str:
        self._escolher(self._indice)
        return "break"

    def _ao_esc(self, _evento: tk.Event) -> str:
        self._cancelar()
        return "break"

    def _ao_perder_foco(self, _evento: tk.Event) -> None:
        """Perder o foco cancela — mas só se o foco saiu da aplicação.

        ``focus_get()`` devolve ``None`` quando o foco está em outro
        processo. Verificamos depois de um tick porque o FocusOut chega antes
        do foco novo assentar, e durante a carência inicial nem olhamos.
        """
        if not self._visivel or time.monotonic() < self._carencia_ate:
            return
        self._raiz.after(120, self._conferir_foco)

    def _conferir_foco(self) -> None:
        if not self._visivel or self._janela is None:
            return
        try:
            foco = self._raiz.focus_get()
        except (tk.TclError, KeyError):
            foco = None
        # ``focus_get()`` devolve None quando o foco saiu da aplicação, e um
        # widget quando ficou nela — nesse caso só continuamos abertos se o
        # widget for do próprio popup (ex.: clique numa linha).
        if foco is None or not self._pertence_ao_popup(foco):
            self._cancelar()

    def _pertence_ao_popup(self, widget: tk.Misc) -> bool:
        assert self._janela is not None
        caminho, base = str(widget), str(self._janela)
        return caminho == base or caminho.startswith(f"{base}.")

    def _escolher(self, posicao: int) -> None:
        if not self._visivel or not (0 <= posicao < len(self._sugestoes)):
            return
        sugestao = self._sugestoes[posicao]

        if self._fila:
            self._escolhas[self._fila[self._pergunta].indice] = sugestao.palavra
            self._pergunta += 1
            if self._pergunta < len(self._fila):
                self._carregar_pergunta()
                self._redesenhar_pergunta()
                return
            self._concluir()
            return

        acao = self._ao_escolher
        self.fechar()
        if acao is not None:
            # Adiado: o app-alvo ainda está recuperando o foco. Colar agora
            # mandaria o Ctrl+V para uma janela que acabou de sumir.
            self._raiz.after(_FOLGA_ANTES_DA_ESCOLHA_MS, lambda: acao(sugestao))

    def _cancelar(self) -> None:
        """Esc, clique fora ou perda de foco.

        Numa fila isso não é cancelar: as respostas já dadas valem e o resto
        fica com a grafia automática. Ver :meth:`perguntar`.
        """
        if not self._visivel:
            return
        if self._fila:
            self._concluir()
            return
        acao = self._ao_cancelar
        self.fechar()
        if acao is not None:
            self._raiz.after(_FOLGA_ANTES_DA_ESCOLHA_MS, acao)

    def _concluir(self) -> None:
        """Fecha a fila e entrega as escolhas, uma vez só."""
        escolhas = dict(self._escolhas)
        acao = self._ao_concluir
        self._fila = ()
        self._ao_concluir = None
        self.fechar()
        if acao is not None:
            # Mesma folga do modo simples: quem recebe vai colar, e o app-alvo
            # ainda está recuperando o foco.
            self._raiz.after(_FOLGA_ANTES_DA_ESCOLHA_MS, lambda: acao(escolhas))


__all__ = ["MAX_SUGESTOES", "PopupSugestoes"]
