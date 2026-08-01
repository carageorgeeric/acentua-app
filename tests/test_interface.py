"""Testes da camada de interface.

O que dá para testar sem tela — tradução de tecla, validação de atalho,
resolução de tema, mistura de cor — roda sempre. O que precisa de janela de
verdade está marcado com ``gui``, e o que lê o registro do Windows com
``sistema``; o CI roda ``-m "not gui and not sistema"``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from corretor.interface import (
    TEMA_CLARO,
    TEMA_ESCURO,
    Estilo,
    misturar_cores,
    resolver_tema,
    tema_do_sistema,
)
from corretor.interface.componentes import (
    ORDEM_MODIFICADORES,
    atalho_legivel,
    modificador_de_keysym,
    montar_atalho,
    normalizar_atalho,
    teclas_legiveis,
    tem_modificador,
    traduzir_keysym,
)
from corretor.interface.janela_config import ATALHOS_PROIBIDOS

# ---------------------------------------------------------------------------
# keysym do tkinter -> formato do pynput
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keysym, esperado",
    [
        ("c", "c"),
        ("C", "c"),
        ("7", "7"),
        ("KP_7", "7"),
        ("space", "<space>"),
        ("Return", "<enter>"),
        ("KP_Enter", "<enter>"),
        ("Escape", "<esc>"),
        ("Tab", "<tab>"),
        ("Delete", "<delete>"),
        ("Prior", "<page_up>"),
        ("Next", "<page_down>"),
        ("Up", "<up>"),
        ("F5", "<f5>"),
        ("F12", "<f12>"),
        ("F24", "<f24>"),
        ("comma", ","),
        ("period", "."),
        ("ccedilla", "ç"),
    ],
)
def test_traduz_keysym_para_pynput(keysym: str, esperado: str) -> None:
    assert traduzir_keysym(keysym) == esperado


@pytest.mark.parametrize(
    "keysym", ["Control_L", "Control_R", "Alt_L", "Shift_R", "Super_L", "Meta_R"]
)
def test_modificador_nao_vira_tecla_final(keysym: str) -> None:
    """Modificador entra na combinação por outro caminho, nunca como tecla."""
    assert traduzir_keysym(keysym) is None
    assert modificador_de_keysym(keysym) in ORDEM_MODIFICADORES


@pytest.mark.parametrize(
    "keysym, esperado",
    [("Control_L", "<ctrl>"), ("Alt_R", "<alt>"), ("Shift_L", "<shift>"), ("Win_L", "<cmd>")],
)
def test_modificador_de_keysym(keysym: str, esperado: str) -> None:
    assert modificador_de_keysym(keysym) == esperado


def test_keysym_desconhecido_e_ignorado() -> None:
    """Melhor ignorar a tecla do que gravar um atalho que nunca dispara."""
    assert traduzir_keysym("XF86AudioPlay") is None
    assert traduzir_keysym("") is None


def test_monta_atalho_na_ordem_canonica() -> None:
    assert montar_atalho({"<alt>", "<ctrl>"}, "c") == "<ctrl>+<alt>+c"
    assert montar_atalho({"<shift>", "<alt>", "<ctrl>"}, "<f5>") == (
        "<ctrl>+<alt>+<shift>+<f5>"
    )


def test_normalizar_deixa_atalhos_equivalentes_iguais() -> None:
    """Sem isto, <alt>+<ctrl>+c passaria batido pela checagem de duplicata."""
    assert normalizar_atalho("<alt>+<ctrl>+C") == normalizar_atalho("<ctrl>+<alt>+c")
    assert normalizar_atalho("<ctrl>+<alt>+c") == "<ctrl>+<alt>+c"


def test_normalizar_atalho_vazio() -> None:
    assert normalizar_atalho("") == ""
    assert normalizar_atalho("+++") == ""


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("combinacao", ["c", "<f5>", "<space>", ""])
def test_rejeita_atalho_sem_modificador(combinacao: str) -> None:
    """Atalho global sem modificador sequestra a tecla no sistema inteiro."""
    assert not tem_modificador(combinacao)


@pytest.mark.parametrize(
    "combinacao",
    ["<ctrl>+<alt>+c", "<ctrl>+<shift>+s", "<alt>+<f5>", "<ctrl>+<alt>+<shift>+w"],
)
def test_aceita_atalho_com_modificador(combinacao: str) -> None:
    assert tem_modificador(combinacao)


@pytest.mark.parametrize(
    "combinacao",
    ["<alt>+<space>", "<ctrl>+<esc>", "<alt>+<tab>", "<ctrl>+<alt>+<delete>",
     "<ctrl>+<alt>+<space>"],
)
def test_combinacoes_reservadas_do_windows_estao_na_lista(combinacao: str) -> None:
    """O Windows já usa estas; ou disparam duplicado ou nem chegam até nós."""
    assert normalizar_atalho(combinacao) in ATALHOS_PROIBIDOS


def test_reservadas_sao_reconhecidas_em_qualquer_ordem() -> None:
    """Gravar Ctrl+Alt+Del ou Alt+Del+Ctrl tem que dar na mesma recusa."""
    assert normalizar_atalho("<alt>+<TAB>") in ATALHOS_PROIBIDOS
    assert normalizar_atalho("<alt>+<ctrl>+<delete>") in ATALHOS_PROIBIDOS
    assert normalizar_atalho("<shift>+<alt>+c") not in ATALHOS_PROIBIDOS


# ---------------------------------------------------------------------------
# Rótulos
# ---------------------------------------------------------------------------


def test_teclas_legiveis_viram_um_keycap_por_tecla() -> None:
    assert teclas_legiveis("<ctrl>+<alt>+c") == ["Ctrl", "Alt", "C"]
    assert teclas_legiveis("<ctrl>+<shift>+<f5>") == ["Ctrl", "Shift", "F5"]
    assert teclas_legiveis("<alt>+<space>") == ["Alt", "Espaço"]
    assert teclas_legiveis("<ctrl>+<up>") == ["Ctrl", "↑"]


def test_atalho_legivel_para_mensagem_de_erro() -> None:
    assert atalho_legivel("<alt>+<tab>") == "Alt+Tab"


# ---------------------------------------------------------------------------
# Tema
# ---------------------------------------------------------------------------


def test_resolver_tema_explicito() -> None:
    assert resolver_tema("claro") is TEMA_CLARO
    assert resolver_tema("escuro") is TEMA_ESCURO
    assert resolver_tema("ESCURO") is TEMA_ESCURO


def test_resolver_tema_sistema_consulta_o_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import corretor.interface as interface

    monkeypatch.setattr(interface, "tema_do_sistema", lambda: "escuro")
    assert resolver_tema("sistema") is TEMA_ESCURO
    monkeypatch.setattr(interface, "tema_do_sistema", lambda: "claro")
    assert resolver_tema("sistema") is TEMA_CLARO


def test_config_com_lixo_nao_impede_a_janela_de_abrir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Um config.json editado à mão não pode derrubar a interface."""
    import corretor.interface as interface

    monkeypatch.setattr(interface, "tema_do_sistema", lambda: "claro")
    assert resolver_tema("roxo-neon") is TEMA_CLARO
    assert resolver_tema(None) is TEMA_CLARO
    assert resolver_tema("") is TEMA_CLARO


def test_so_existe_uma_cor_de_destaque() -> None:
    """Azul do sistema no claro e no escuro; nenhuma segunda cor de marca."""
    assert TEMA_CLARO.destaque == "#007AFF"
    assert TEMA_ESCURO.destaque == "#0A84FF"


@pytest.mark.sistema
def test_tema_do_sistema_le_o_registro() -> None:
    assert tema_do_sistema() in ("claro", "escuro")


@pytest.mark.sistema
def test_tema_do_sistema_com_registro_indisponivel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem a chave (Windows antigo), o padrão do sistema é claro."""
    import winreg

    def explodir(*_args, **_kw):
        raise OSError("sem chave")

    monkeypatch.setattr(winreg, "OpenKey", explodir)
    assert tema_do_sistema() == "claro"


# ---------------------------------------------------------------------------
# Cor
# ---------------------------------------------------------------------------


def test_misturar_cores() -> None:
    assert misturar_cores("#000000", "#FFFFFF", 0.0) == "#000000"
    assert misturar_cores("#000000", "#FFFFFF", 1.0) == "#FFFFFF"
    assert misturar_cores("#000000", "#FFFFFF", 0.5) == "#808080"


def test_misturar_cores_satura_fora_do_intervalo() -> None:
    assert misturar_cores("#102030", "#FFFFFF", -3.0) == "#102030"
    assert misturar_cores("#102030", "#FFFFFF", 9.0) == "#FFFFFF"


# ---------------------------------------------------------------------------
# Invariantes que não podem regredir
# ---------------------------------------------------------------------------


def test_toast_nunca_rouba_o_foco() -> None:
    """Se o toast ativar, o Ctrl+V do app vai para a janela errada.

    O teste olha o código-fonte de propósito: a regressão que importa é
    alguém acrescentar ``focus_force`` achando que "a janela não aparece".
    """
    fonte = Path(__file__).resolve().parents[1] / "src/corretor/interface/toast.py"
    codigo = fonte.read_text(encoding="utf-8")
    assert ".focus_force(" not in codigo
    assert "impedir_roubo_de_foco(janela)" in codigo


def test_estilo_sem_raiz_usa_escala_neutra() -> None:
    estilo = Estilo(None, "claro")
    assert estilo.escala == 1.0
    assert estilo.px(13) == 13
    assert estilo.tema is TEMA_CLARO


# ---------------------------------------------------------------------------
# Com janela de verdade
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _interpretador():
    """UM ``Tk`` para a sessão inteira.

    Criar e destruir vários ``Tk()`` no mesmo processo é instável: do segundo
    em diante a janela às vezes nem mapeia, e é a mesma regra que o app segue
    (veja o modelo de threads em ``corretor.interface``).
    """
    try:
        janela = tk.Tk()
    except tk.TclError as erro:  # pragma: no cover - máquina sem display
        pytest.skip(f"sem display: {erro}")
    janela.geometry("460x300+40+40")
    janela.update()
    yield janela
    try:
        janela.destroy()
    except tk.TclError:  # pragma: no cover
        pass


@pytest.fixture
def raiz(_interpretador):
    """O root da sessão, limpo de widgets no fim de cada teste.

    Precisa estar mapeado: o ``event_generate`` de tecla não entrega nada
    para janela escondida, e é justamente o teclado que estes testes exercem.
    """
    yield _interpretador
    for filho in _interpretador.winfo_children():
        try:
            filho.destroy()
        except tk.TclError:  # pragma: no cover
            pass
    _interpretador.update()


def _gravador(raiz, valor="<ctrl>+<alt>+c", validar=None):
    from corretor.interface.componentes import GravadorDeAtalho

    estilo = Estilo(raiz, "claro")
    campo = GravadorDeAtalho(raiz, estilo, valor, validar=validar)
    campo.pack()
    raiz.update()
    campo.iniciar()
    raiz.update()
    return campo


def _tecla(keysym: str) -> tk.Event:
    evento = tk.Event()
    evento.keysym = keysym
    evento.char = keysym if len(keysym) == 1 else ""
    return evento


def _teclar(campo, *keysyms):
    """Aperta e solta as teclas, chamando os tratadores direto.

    ``event_generate`` só entrega evento de teclado quando a janela está
    mapeada E com o foco do Windows — rodando na suíte inteira o terminal
    rouba o foco e o teste vira loteria. Chamar o tratador exercita a mesma
    lógica (tradução do keysym, validação, gravação) sem depender de quem
    está em primeiro plano. O caminho de ponta a ponta com janela de verdade
    está coberto por ``test_gravador_ponta_a_ponta``.
    """
    for keysym in keysyms[:-1]:
        campo._ao_apertar(_tecla(keysym))
    campo._ao_apertar(_tecla(keysyms[-1]))
    campo._ao_soltar(_tecla(keysyms[-1]))


@pytest.mark.gui
def test_gravador_produz_string_do_pynput(raiz) -> None:
    campo = _gravador(raiz)
    _teclar(campo, "Control_L", "Alt_L", "k")
    assert campo.valor == "<ctrl>+<alt>+k"
    assert not campo.gravando


@pytest.mark.gui
def test_gravador_grava_tecla_nomeada(raiz) -> None:
    campo = _gravador(raiz)
    # Duas teclas não chegam ao teto de três, então quem fecha a gravação é o
    # Enter — é a saída documentada para combinações curtas.
    _teclar(campo, "Control_L", "F9", "Return")
    assert campo.valor == "<ctrl>+<f9>"


@pytest.mark.gui
def test_gravador_recusa_sem_modificador_e_mantem_o_anterior(raiz) -> None:
    campo = _gravador(raiz)
    _teclar(campo, "k", "Return")
    assert campo.valor == "<ctrl>+<alt>+c"
    assert campo._erro is not None
    assert "Ctrl" in campo._erro


@pytest.mark.gui
def test_gravador_recusa_combinacao_reservada(raiz) -> None:
    def validar(combinacao: str) -> str | None:
        if normalizar_atalho(combinacao) in ATALHOS_PROIBIDOS:
            return f"O Windows já usa {atalho_legivel(combinacao)}."
        return None

    campo = _gravador(raiz, validar=validar)
    _teclar(campo, "Alt_L", "Tab", "Return")
    assert campo.valor == "<ctrl>+<alt>+c"
    assert campo._erro == "O Windows já usa Alt+Tab."


@pytest.mark.gui
def test_esc_cancela_a_gravacao(raiz) -> None:
    campo = _gravador(raiz)
    campo._ao_apertar(_tecla("Control_L"))
    campo._ao_apertar(_tecla("Escape"))
    assert not campo.gravando
    assert campo.valor == "<ctrl>+<alt>+c"


@pytest.mark.gui
def test_interruptor_alterna_e_avisa(raiz) -> None:
    from corretor.interface.componentes import Interruptor

    vistos: list[bool] = []
    switch = Interruptor(raiz, Estilo(raiz, "escuro"), False, vistos.append)
    switch.pack()
    raiz.update()
    switch.alternar()
    assert switch.valor is True
    assert vistos == [True]


@pytest.mark.gui
def test_controle_segmentado_troca_valor(raiz) -> None:
    from corretor.interface.componentes import ControleSegmentado

    escolhido: list[str] = []
    controle = ControleSegmentado(
        raiz,
        Estilo(raiz, "claro"),
        [("Claro", "claro"), ("Escuro", "escuro"), ("Sistema", "sistema")],
        "claro",
        escolhido.append,
    )
    controle.pack()
    raiz.update()
    assert controle.valor == "claro"
    controle.definir("sistema", avisar=True)
    assert controle.valor == "sistema"
    assert escolhido == ["sistema"]


@pytest.mark.gui
def test_janela_config_salva_os_tres_atalhos(raiz, tmp_path, monkeypatch) -> None:
    from collections import Counter

    import corretor.config as modulo_config
    from corretor.config import Config, Preferencias
    from corretor.interface.janela_config import JanelaConfig

    monkeypatch.setattr(modulo_config, "pasta_de_dados", lambda: tmp_path)
    config = Config(tema="escuro")
    salvou: list[bool] = []
    janela = JanelaConfig(
        raiz, config, Preferencias({"a": Counter({"á": 1})}), lambda: salvou.append(True)
    )
    raiz.update()

    janela._atalhos["corrigir"] = "<ctrl>+<shift>+e"
    janela._salvar()

    # Salvar não fecha mais a janela: quem acabou de gravar em geral quer
    # conferir o que gravou. A confirmação mora no próprio botão.
    continua_aberta = bool(janela.janela.winfo_exists())
    janela.fechar()

    assert continua_aberta
    assert config.atalho_corrigir == "<ctrl>+<shift>+e"
    assert config.atalho_ultima_palavra == "<ctrl>+<alt>+d"
    assert config.atalho_sugestoes == "<ctrl>+<alt>+s"
    assert salvou == [True]


@pytest.mark.gui
def test_janela_config_bloqueia_atalho_duplicado(raiz, tmp_path, monkeypatch) -> None:
    import corretor.config as modulo_config
    from corretor.config import Config, Preferencias
    from corretor.interface.janela_config import JanelaConfig

    monkeypatch.setattr(modulo_config, "pasta_de_dados", lambda: tmp_path)
    config = Config()
    janela = JanelaConfig(raiz, config, Preferencias(), lambda: None)
    raiz.update()

    janela._atalhos["sugestoes"] = janela._atalhos["corrigir"]
    janela._salvar()

    # Nada foi salvo, e o primeiro campo do par conflitante mostra por quê,
    # nomeando o outro — sem messagebox nenhuma.
    assert config.atalho_sugestoes != config.atalho_corrigir
    erros = {
        chave: gravador._erro
        for chave, gravador in janela._gravadores.items()
        if gravador._erro
    }
    assert erros, "o conflito precisa aparecer em algum campo"
    assert "Ver alternativas" in erros["corrigir"]
    janela.fechar()


@pytest.mark.gui
def test_popup_mostra_e_escolhe(raiz) -> None:
    from corretor.interface.popup import PopupSugestoes
    from corretor.tipos import Sugestao

    escolhidas: list[Sugestao] = []
    popup = PopupSugestoes(raiz, tema="escuro")
    popup.mostrar([Sugestao("você", 0.8), Sugestao("voce", 0.2)], escolhidas.append)
    raiz.update()
    assert popup.visivel
    popup._escolher(1)
    raiz.update()
    assert not popup.visivel
    popup.destruir()


def _fila_de_duvidas():
    from corretor.tipos import Duvida, Sugestao

    return [
        Duvida(0, "pao ", " queijo", (Sugestao("e", 0.7), Sugestao("é", 0.3))),
        Duvida(2, "isso ", " bom", (Sugestao("é", 0.9), Sugestao("e", 0.1))),
    ]


@pytest.mark.gui
def test_popup_percorre_a_fila_sem_fechar_no_meio(raiz) -> None:
    """A janela só some no fim: fechar entre perguntas devolveria o foco."""
    from corretor.interface.popup import PopupSugestoes

    respostas: list[dict[int, str]] = []
    popup = PopupSugestoes(raiz, tema="claro")
    popup.perguntar(_fila_de_duvidas(), respostas.append)
    raiz.update()

    assert popup.visivel
    popup._escolher(0)  # "e" para a primeira
    raiz.update()
    assert popup.visivel, "a janela não pode fechar entre uma pergunta e outra"
    assert not respostas

    popup._escolher(1)  # "e" para a segunda, contrariando o automático
    raiz.update()
    assert not popup.visivel
    raiz.after(120, raiz.quit)
    raiz.mainloop()
    assert respostas == [{0: "e", 2: "e"}]
    popup.destruir()


@pytest.mark.gui
def test_esc_no_meio_da_fila_entrega_o_que_ja_foi_respondido(raiz) -> None:
    """Desistir não perde a correção: o resto fica com a grafia automática."""
    from corretor.interface.popup import PopupSugestoes

    respostas: list[dict[int, str]] = []
    popup = PopupSugestoes(raiz, tema="claro")
    popup.perguntar(_fila_de_duvidas(), respostas.append)
    raiz.update()
    popup._escolher(1)  # responde a primeira
    raiz.update()
    popup._cancelar()  # e desiste da segunda
    raiz.update()

    assert not popup.visivel
    raiz.after(120, raiz.quit)
    raiz.mainloop()
    assert respostas == [{0: "é"}]
    popup.destruir()


@pytest.mark.gui
def test_popup_com_fila_vazia_conclui_sem_abrir(raiz) -> None:
    from corretor.interface.popup import PopupSugestoes

    respostas: list[dict[int, str]] = []
    popup = PopupSugestoes(raiz)
    popup.perguntar([], respostas.append)
    assert not popup.visivel
    assert respostas == [{}]


@pytest.mark.gui
def test_popup_com_lista_vazia_cancela(raiz) -> None:
    from corretor.interface.popup import PopupSugestoes

    cancelou: list[bool] = []
    popup = PopupSugestoes(raiz)
    popup.mostrar([], lambda _s: None, lambda: cancelou.append(True))
    assert not popup.visivel
    assert cancelou == [True]


@pytest.mark.gui
def test_gravador_ponta_a_ponta_com_teclado_de_verdade(raiz) -> None:
    """O caminho completo: tecla do Windows -> binding do Tk -> string do pynput.

    Depende do foco do sistema, então só afirma quando os eventos chegaram
    mesmo; se o terminal roubou o primeiro plano, não há o que verificar.
    """
    campo = _gravador(raiz)
    raiz.focus_force()
    for sequencia in (
        "<KeyPress-Control_L>",
        "<KeyPress-Alt_L>",
        "<KeyPress-j>",
        "<KeyRelease-j>",
    ):
        campo._tela.event_generate(sequencia)
    if campo.gravando:
        pytest.skip("o Windows não entregou as teclas: outra janela está em foco")
    assert campo.valor == "<ctrl>+<alt>+j"
