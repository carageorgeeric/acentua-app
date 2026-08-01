"""Janela de configurações — coluna única, três cartões, nada mais.

O produto vive na bandeja e no atalho; esta janela existe para escolher o
atalho, trocar o tema e limpar o aprendizado. Por isso não tem aba, nem busca,
nem perfil: são três seções, na ordem em que alguém realmente mexe nelas.

A página é cinza e cada seção é um cartão branco flutuando sobre ela: a
separação vem da elevação, não de linha. Acima de cada cartão fica um rótulo
pequeno e discreto, como nas listas agrupadas do iOS. A moldura é a nativa do
Windows (barra de título pintada na cor do tema pelo DWM); o conteúdo inteiro
é desenhado pelos widgets de ``componentes``. Não sobrou nenhum ``ttk``: o
tema nativo do ttk não deixa pintar fundo escuro sem brigar, e o switch e o
gravador de atalho não existem lá.

Nenhum erro abre ``messagebox``. Atalho inválido, reservado ou repetido
aparece como texto vermelho embaixo do próprio campo, apagar o aprendizado
pede confirmação no próprio botão, e salvar se anuncia no próprio botão —
sem fechar a janela, porque quem acabou de salvar em geral quer conferir o
que salvou.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from corretor import NOME_APP, VERSAO
from corretor.config import (
    ATALHOS_PROIBIDOS,
    Config,
    Preferencias,
    motivo_para_recusar,
)

from . import (
    Estilo,
    area_util_do_cursor,
    centralizar_no_monitor_do_cursor,
    escala_da_tela,
    vestir_moldura_nativa,
)
from .componentes import (
    Botao,
    BotaoDiscreto,
    Cartao,
    ControleSegmentado,
    GravadorDeAtalho,
    Interruptor,
    normalizar_atalho,
    rotulo,
    tem_modificador,
)

#: Largura fixa. A janela cresce só para baixo — coluna única não se adapta a
#: redimensionamento, e deixar o usuário esticar só produziria layout torto.
LARGURA = 448
#: Distância da borda da janela até a borda visível do cartão.
MARGEM = 20


class _Cartao(Cartao):
    """O cartão desta janela: sombra mais curta que a do padrão.

    Cada cartão reserva a própria margem para a sombra se espalhar, e três
    cartões empilhados pagam essa folga seis vezes. Com 14px a janela não
    caberia numa tela de 1080p a 150%; com 10 cabe, e o desfoque encolhe
    junto para a sombra continuar inteira dentro da folga.
    """

    MARGEM = 9
    PADDING = 12
    RAIO = 18
    DESFOQUE = 9
    DESLOCAMENTO = 2


#: Coluna de texto: tudo — título, rótulo de seção, conteúdo dos cartões e
#: rodapé — começa nesta distância da borda esquerda da janela.
_COLUNA = MARGEM + _Cartao.PADDING

#: Largura útil de dentro de um cartão, em px de layout.
_CONTEUDO = LARGURA - 2 * _COLUNA


TEMAS_DISPONIVEIS = [("Claro", "claro"), ("Escuro", "escuro"), ("Sistema", "sistema")]

_ROTULOS_DE_ATALHO = {
    "corrigir": "Corrigir seleção",
    "ultima_palavra": "Corrigir última palavra",
    "sugestoes": "Ver alternativas",
}

#: Quanto tempo o botão de apagar aprendizado fica em "tem certeza?" antes de
#: voltar sozinho ao normal.
_MS_ATE_DESISTIR = 4000

#: Quanto tempo o botão primário fica anunciando que gravou. Curto o bastante
#: para não parecer travado, longo o bastante para o olho pousar nele.
_MS_MOSTRANDO_SALVO = 1800

#: Quantas vezes o layout pode ser reconstruído menor para caber na tela.
_TETO_DE_TENTATIVAS = 4

_TEXTO_SALVAR = "Salvar"
_TEXTO_SALVO = "✓ Salvo"


class JanelaConfig:
    """Configurações do Acentua. Esc fecha, Enter salva e a janela fica."""

    def __init__(
        self,
        root: tk.Tk,
        config: Config,
        preferencias: Preferencias,
        ao_salvar: Callable[[], None],
    ) -> None:
        self._config = config
        self._preferencias = preferencias
        self._ao_salvar = ao_salvar
        self._posicionada = False
        self._confirmando_apagar = False
        self._agendado_apagar: str | None = None
        self._agendado_salvo: str | None = None
        self._escala_forcada: float | None = None
        self._tentativas_de_encolher = 0
        # Trocar o tema reconstrói a janela inteira; este estado precisa
        # sobreviver a isso, senão "Fechar" volta a ser "Cancelar" depois de
        # o usuário já ter gravado.
        self._ja_salvou = False

        self.janela = tk.Toplevel(root)
        # Escondida ATÉ estar pronta. Um ``Toplevel`` nasce mapeado, no canto
        # que o Windows escolher e com o tamanho errado: o usuário via a janela
        # aparecer vazia, ser remontada uma ou mais vezes por
        # ``_encolher_para_caber`` e só então pular para o lugar certo. Montar
        # com ela oculta transforma isso num único aparecimento já no lugar.
        self.janela.withdraw()
        self.janela.title(f"{NOME_APP} — Configurações")
        # Tamanho fixo. Cada cartão redesenha a própria sombra (desfoque
        # gaussiano numa imagem PIL) a cada ``<Configure>``, então arrastar a
        # borda repintava três sombras por quadro e a janela arrastava junto.
        # A coluna também não tem o que fazer com largura sobrando: é uma
        # lista de rótulo à esquerda e controle à direita.
        self.janela.resizable(False, False)
        # ``transient`` só quando o root está na tela. O root do Acentua vive
        # oculto (``withdraw``), e no Windows uma janela "dona" escondida
        # arrasta a filha junto: a janela nunca chega a ser mapeada e o
        # usuário clica em Configurações sem que nada apareça.
        try:
            if root.winfo_ismapped():
                self.janela.transient(root)
        except tk.TclError:
            pass

        # Todo o estado mora em variáveis, e não nos widgets: trocar o tema
        # reconstrói a tela inteira, e o que estava preenchido tem que voltar.
        self.var_tema = tk.StringVar(value=config.tema)
        self.var_aviso = tk.BooleanVar(value=config.mostrar_aviso)
        self.var_popup = tk.BooleanVar(value=config.popup_em_palavra_unica)
        self.var_revisar = tk.BooleanVar(value=config.revisar_frase)
        self.var_aprender = tk.BooleanVar(value=config.aprender_escolhas)
        self._atalhos = {
            "corrigir": normalizar_atalho(config.atalho_corrigir),
            "ultima_palavra": normalizar_atalho(config.atalho_ultima_palavra),
            "sugestoes": normalizar_atalho(config.atalho_sugestoes),
        }

        self._corpo: tk.Frame | None = None
        self._construir()

        self.janela.bind("<Escape>", lambda _e: self.fechar())
        self.janela.bind("<Return>", lambda _e: self._salvar())
        self.janela.protocol("WM_DELETE_WINDOW", self.fechar)
        # Só agora: ``grab_set`` numa janela não mapeada levanta TclError, e
        # até aqui ela estava oculta de propósito.
        self.janela.deiconify()
        self.janela.grab_set()
        self.janela.focus_force()

    # ------------------------------------------------------------------ ciclo

    def fechar(self) -> None:
        self._cancelar_apagar()
        self._cancelar_aviso_salvo()
        try:
            self.janela.destroy()
        except tk.TclError:
            pass

    # ----------------------------------------------------------------- layout

    def _construir(self) -> None:
        """(Re)desenha a janela inteira no tema atual.

        Chamado de novo quando o usuário troca Claro/Escuro/Sistema: o tema
        muda na hora, sem precisar reabrir. Como nenhum widget guarda estado,
        destruir e refazer é mais simples e mais seguro do que sair repintando
        cor por cor.
        """
        self.estilo = Estilo(self.janela, self.var_tema.get())
        if self._escala_forcada is not None:
            self.estilo.escala = self._escala_forcada
        tema = self.estilo.tema
        self.fundo = tema.fundo
        self.superficie = tema.superficie
        px = self.estilo.px

        self.janela.configure(bg=self.fundo)
        vestir_moldura_nativa(self.janela, tema)

        # O aviso de "salvo" está agendado sobre um botão que vai morrer aqui.
        self._cancelar_aviso_salvo()
        if self._corpo is not None:
            self._corpo.destroy()
        corpo = self._corpo = tk.Frame(self.janela, bg=self.fundo)
        corpo.pack(fill="both", expand=True)
        # Régua invisível: é ela que fixa a largura da coluna.
        tk.Frame(corpo, bg=self.fundo, width=px(LARGURA), height=1).pack()

        self._cabecalho(corpo)
        self._secao_atalhos(self._cartao(corpo, "Atalhos", primeiro=True))
        self._secao_comportamento(self._cartao(corpo, "Comportamento"))
        self._secao_aparencia(self._cartao(corpo, "Aparência"))
        self._rodape(corpo)

        if self._encolher_para_caber():
            return
        self._centralizar()

    def _moldura(self) -> int:
        """Altura da barra de título, que não entra no ``reqheight``.

        Quem a desenha é o Windows, então ela acompanha a escala real da tela
        e não a escala com que este layout foi calculado.
        """
        return round(46 * escala_da_tela(self.janela))

    def _altura_ocupada(self) -> int:
        self.janela.update_idletasks()
        return self.janela.winfo_reqheight() + self._moldura()

    def _encolher_para_caber(self) -> bool:
        """Reconstrói num tamanho menor se a janela não couber na tela.

        Numa tela pequena a 150% os três cartões passam da altura útil, e esta
        janela não rola nem redimensiona: o único jeito de o botão Salvar
        continuar alcançável é o layout inteiro — texto, controle e
        espaçamento — encolher junto. Devolve ``True`` quando disparou a
        reconstrução.

        O arredondamento de cada ``px()`` faz a altura reconstruída cair um
        pouco acima da conta, por isso as tentativas: duas ou três passadas
        convergem, e o teto existe só para não haver como entrar em laço.
        """
        if self._tentativas_de_encolher >= _TETO_DE_TENTATIVAS:
            return False
        precisa = self._altura_ocupada()
        _ax, _ay, _al, disponivel = area_util_do_cursor(self.janela)
        if precisa <= disponivel:
            return False
        moldura = self._moldura()
        self._tentativas_de_encolher += 1
        # Piso em 1.0: abaixo disso o texto sairia menor que o desenhado, e a
        # 100% a janela cabe em qualquer tela que o Windows 11 suporta.
        # O 1% a menos absorve o arredondamento: sem ele a conta acerta o alvo
        # por dentro e sobra um punhado de pixels que pede outra passada.
        self._escala_forcada = max(
            1.0,
            self.estilo.escala * (disponivel - moldura) / (precisa - moldura) * 0.99,
        )
        self._construir()
        return True

    def _cabecalho(self, pai: tk.Misc) -> None:
        """Título grande e uma linha cinza embaixo. Nada mais compete."""
        px = self.estilo.px
        tema = self.estilo.tema
        caixa = tk.Frame(pai, bg=self.fundo)
        caixa.pack(fill="x", padx=px(_COLUNA), pady=(px(16), 0))
        tk.Label(
            caixa,
            text="Configurações",
            font=self.estilo.fonte(21, "forte"),
            fg=tema.texto,
            bg=self.fundo,
            anchor="w",
        ).pack(anchor="w")
        rotulo(
            caixa,
            self.estilo,
            "Atalhos, comportamento e aparência.",
            tamanho=12,
            cor=tema.texto_secundario,
            fundo=self.fundo,
        ).pack(anchor="w", pady=(px(1), 0))

    def _cartao(self, pai: tk.Misc, titulo: str, primeiro: bool = False) -> tk.Frame:
        """Rótulo discreto + cartão branco. Devolve onde as linhas entram.

        O rótulo fica fora do cartão, alinhado com o conteúdo de dentro dele:
        é o que deixa o cartão ser só conteúdo, sem um título ocupando a
        primeira linha de todos eles.
        """
        px = self.estilo.px
        rotulo(
            pai,
            self.estilo,
            titulo,
            tamanho=11,
            cor=self.estilo.tema.texto_terciario,
            fundo=self.fundo,
        ).pack(anchor="w", padx=px(_COLUNA), pady=(px(10 if primeiro else 7), 0))
        cartao = _Cartao(pai, self.estilo, fundo=self.fundo)
        # A margem que o cartão reserva para a sombra sai da margem da janela,
        # ou o cartão fica afastado da borda o dobro do que deveria.
        cartao.pack(fill="x", padx=px(MARGEM) - px(_Cartao.MARGEM))
        return cartao.conteudo

    def _linha(
        self,
        pai: tk.Misc,
        texto: str,
        criar: Callable[[tk.Misc], tk.Widget],
        legenda: str | None = None,
        pady: int = 2,
    ) -> tuple[tk.Widget, tk.Label | None]:
        """Rótulo à esquerda, controle à direita, respiro entre os dois.

        A legenda mora embaixo do rótulo, dentro da mesma linha — uma linha de
        texto solta entre duas linhas de controle quebraria o ritmo da coluna.
        """
        px = self.estilo.px
        linha = tk.Frame(pai, bg=self.superficie)
        linha.pack(fill="x", pady=px(pady))
        linha.columnconfigure(0, weight=1)

        caixa = tk.Frame(linha, bg=self.superficie)
        caixa.grid(row=0, column=0, sticky="w")
        rotulo(caixa, self.estilo, texto, fundo=self.superficie).pack(anchor="w")
        etiqueta = None
        if legenda:
            etiqueta = rotulo(
                caixa,
                self.estilo,
                legenda,
                tamanho=11,
                cor=self.estilo.tema.texto_secundario,
                fundo=self.superficie,
            )
            etiqueta.pack(anchor="w", pady=(px(1), 0))

        controle = criar(linha)
        controle.grid(row=0, column=1, sticky="e", padx=(px(12), 0))

        if etiqueta is not None:
            # A legenda quebra no espaço que sobrou depois do controle. Sem
            # esse limite ela empurraria a coluna para além da largura pedida
            # e cada linha teria uma largura diferente.
            controle.update_idletasks()
            sobra = px(_CONTEUDO - 12) - controle.winfo_reqwidth()
            etiqueta.configure(wraplength=max(px(120), sobra))
        return controle, etiqueta

    # ---------------------------------------------------------------- seção 1

    def _secao_atalhos(self, pai: tk.Misc) -> None:
        self._gravadores: dict[str, GravadorDeAtalho] = {}
        for chave, texto in _ROTULOS_DE_ATALHO.items():
            controle, _legenda = self._linha(
                pai,
                texto,
                lambda mae, k=chave: GravadorDeAtalho(
                    mae,
                    self.estilo,
                    self._atalhos[k],
                    ao_mudar=lambda valor, k=k: self._atalhos.__setitem__(k, valor),
                    validar=self._validador(k),
                    fundo=self.superficie,
                ),
            )
            self._gravadores[chave] = controle  # type: ignore[assignment]

    def _validador(self, qual: str) -> Callable[[str], str | None]:
        """Recusa o que o Windows já usa e o que outro campo já tem."""

        def validar(combinacao: str) -> str | None:
            normal = normalizar_atalho(combinacao)
            recusa = motivo_para_recusar(normal)
            if recusa:
                return recusa
            for outro, valor in self._atalhos.items():
                if outro != qual and normalizar_atalho(valor) == normal:
                    return f"“{_ROTULOS_DE_ATALHO[outro]}” já usa esse atalho."
            return None

        return validar

    # ---------------------------------------------------------------- seção 2

    def _secao_comportamento(self, pai: tk.Misc) -> None:
        for texto, variavel, legenda in (
            ("Mostrar aviso ao corrigir", self.var_aviso, None),
            ("Oferecer alternativas quando houver dúvida", self.var_popup, None),
            (
                "Revisar a frase antes de colar",
                self.var_revisar,
                "Pergunta palavra por palavra só onde ficou ambíguo.",
            ),
            ("Lembrar das grafias que eu escolher", self.var_aprender, None),
        ):
            self._linha(
                pai,
                texto,
                lambda mae, v=variavel: Interruptor(
                    mae, self.estilo, v.get(), ao_mudar=v.set, fundo=self.superficie
                ),
                legenda=legenda,
            )

        px = self.estilo.px
        self._botao_apagar = BotaoDiscreto(
            pai,
            self.estilo,
            self._texto_de_apagar(),
            self._apagar_aprendizado,
            perigo=False,
            fundo=self.superficie,
        )
        if not len(self._preferencias):
            self._botao_apagar.configure(fg=self.estilo.tema.texto_terciario, cursor="")
            self._botao_apagar.unbind("<Button-1>")
        self._botao_apagar.pack(anchor="w", pady=(px(6), 0))

    def _texto_de_apagar(self) -> str:
        total = len(self._preferencias)
        if not total:
            return "Nada aprendido ainda"
        plural = "s" if total != 1 else ""
        return f"Esquecer aprendizado ({total} palavra{plural})"

    def _apagar_aprendizado(self) -> None:
        """Pede confirmação no próprio botão — messagebox quebraria a estética."""
        if not len(self._preferencias):
            return
        if not self._confirmando_apagar:
            self._confirmando_apagar = True
            self._botao_apagar.configure(
                text="Apagar mesmo? Clique de novo.", fg=self.estilo.tema.erro
            )
            self._agendado_apagar = self.janela.after(
                _MS_ATE_DESISTIR, self._cancelar_apagar
            )
            return
        self._cancelar_apagar()
        self._preferencias.limpar()
        self._preferencias.salvar(forcar=True)
        self._botao_apagar.configure(
            text="Aprendizado apagado",
            fg=self.estilo.tema.texto_terciario,
            cursor="",
        )
        self._botao_apagar.unbind("<Button-1>")

    def _cancelar_apagar(self) -> None:
        if self._agendado_apagar is not None:
            try:
                self.janela.after_cancel(self._agendado_apagar)
            except (tk.TclError, ValueError):
                pass
            self._agendado_apagar = None
        if self._confirmando_apagar:
            self._confirmando_apagar = False
            try:
                self._botao_apagar.configure(
                    text=self._texto_de_apagar(), fg=self.estilo.tema.destaque
                )
            except tk.TclError:
                pass

    # ---------------------------------------------------------------- seção 3

    def _secao_aparencia(self, pai: tk.Misc) -> None:
        self._linha(
            pai,
            "Tema",
            lambda mae: ControleSegmentado(
                mae,
                self.estilo,
                TEMAS_DISPONIVEIS,
                self.var_tema.get(),
                ao_mudar=self._trocar_tema,
                fundo=self.superficie,
            ),
        )

    def _trocar_tema(self, valor: str) -> None:
        self.var_tema.set(valor)
        # Reconstruir na próxima volta do loop: estamos dentro do clique do
        # controle segmentado, e destruir o widget que disparou o evento no
        # meio do tratador irrita o Tk.
        self.janela.after(10, self._construir)

    # ---------------------------------------------------------------- rodapé

    def _rodape(self, pai: tk.Misc) -> None:
        px = self.estilo.px
        rodape = tk.Frame(pai, bg=self.fundo)
        rodape.pack(fill="x", padx=px(_COLUNA), pady=(px(12), px(14)))
        rodape.columnconfigure(0, weight=1)

        rotulo(
            rodape,
            self.estilo,
            f"{NOME_APP} {VERSAO}",
            tamanho=11,
            cor=self.estilo.tema.texto_terciario,
            fundo=self.fundo,
        ).grid(row=0, column=0, sticky="w")
        # Os dois botões nascem com a mesma largura mínima porque os dois
        # trocam de texto em tempo de execução; sem isso a fila se mexeria a
        # cada troca.
        self._botao_secundario = Botao(
            rodape,
            self.estilo,
            self._texto_do_secundario(),
            self.fechar,
            largura_minima=94,
            fundo=self.fundo,
        )
        self._botao_secundario.grid(row=0, column=1, padx=(0, px(8)))
        self._botao_primario = Botao(
            rodape,
            self.estilo,
            _TEXTO_SALVAR,
            self._salvar,
            primario=True,
            largura_minima=94,
            fundo=self.fundo,
        )
        self._botao_primario.grid(row=0, column=2)

    def _texto_do_secundario(self) -> str:
        """Depois do primeiro salvamento não há mais o que cancelar."""
        return "Fechar" if self._ja_salvou else "Cancelar"

    def _centralizar(self) -> None:
        """Abre no monitor onde o cursor está, não no monitor primário."""
        self.janela.update_idletasks()
        if self._posicionada:
            self._reposicionar()
            return
        largura = self.janela.winfo_reqwidth()
        altura = self._altura_ocupada()
        x, y = centralizar_no_monitor_do_cursor(self.janela, largura, altura)
        self.janela.geometry(f"+{x}+{y}")
        self._posicionada = True

    def _reposicionar(self) -> None:
        """Sobe a janela se ela cresceu para fora da tela.

        Trocar o tema reconstrói o layout, e uma fonte de sistema mais alta é
        o suficiente para o botão Salvar sair pela borda de baixo.
        """
        altura = self._altura_ocupada()
        _ax, ay, _al, aa = area_util_do_cursor(self.janela)
        y = self.janela.winfo_y()
        limite = ay + aa - altura - 8
        if y > limite:
            self.janela.geometry(f"+{self.janela.winfo_x()}+{max(ay, limite)}")

    # ------------------------------------------------------------------ ações

    def _salvar(self) -> None:
        """Revalida os três atalhos antes de gravar.

        O gravador já recusa combinação ruim na hora, mas o valor pode ter
        vindo de um ``config.json`` editado à mão — e um atalho inválido aqui
        significa um atalho que simplesmente não funciona depois.
        """
        for chave, gravador in self._gravadores.items():
            valor = self._atalhos[chave]
            erro = None
            if not tem_modificador(valor):
                erro = "Use pelo menos Ctrl, Alt ou Shift junto."
            else:
                erro = self._validador(chave)(valor)
            if erro:
                gravador.mostrar_erro(erro)
                return

        c = self._config
        c.atalho_corrigir = self._atalhos["corrigir"]
        c.atalho_ultima_palavra = self._atalhos["ultima_palavra"]
        c.atalho_sugestoes = self._atalhos["sugestoes"]
        c.tema = self.var_tema.get()
        c.mostrar_aviso = self.var_aviso.get()
        c.popup_em_palavra_unica = self.var_popup.get()
        c.revisar_frase = self.var_revisar.get()
        c.aprender_escolhas = self.var_aprender.get()

        self._ao_salvar()
        self._anunciar_salvo()

    def _anunciar_salvo(self) -> None:
        """Salvar não fecha: o botão vira "Salvo" e volta sozinho.

        Fechar a janela era a única confirmação que existia, e ela tirava da
        tela justamente o que o usuário acabou de mexer. O aviso mora no botão
        que ele clicou, que é onde o olho já está.
        """
        self._ja_salvou = True
        self._cancelar_aviso_salvo()
        try:
            self._botao_primario.trocar_texto(_TEXTO_SALVO)
            self._botao_secundario.trocar_texto(self._texto_do_secundario())
            self._agendado_salvo = self.janela.after(
                _MS_MOSTRANDO_SALVO, self._encerrar_aviso_salvo
            )
        except tk.TclError:
            self._agendado_salvo = None

    def _encerrar_aviso_salvo(self) -> None:
        self._agendado_salvo = None
        try:
            self._botao_primario.trocar_texto(_TEXTO_SALVAR)
        except tk.TclError:
            pass

    def _cancelar_aviso_salvo(self) -> None:
        if self._agendado_salvo is not None:
            try:
                self.janela.after_cancel(self._agendado_salvo)
            except (tk.TclError, ValueError):
                pass
            self._agendado_salvo = None


__all__ = ["ATALHOS_PROIBIDOS", "LARGURA", "JanelaConfig"]
