"""Testes de ``corretor.sistema.selecao``.

Três camadas, da mais barata para a mais cara:

* **Lógica pura** — :func:`_precisa_estender` decide sozinha se vale gastar
  outra injeção. Sem Win32, roda no CI.
* **Orquestração com dublês** — o encadeamento "estende, lê, estende de novo,
  desiste" é testado trocando a injeção e a leitura de clipboard por funções
  de mentira. É onde moram os bugs que corrompem texto do usuário (devolver
  texto velho para uma seleção que cresceu, deixar seleção viva ao desistir),
  e nada disso precisa de teclado real. Também roda no CI.
* **Notepad de verdade** (``gui`` + ``sistema``) — abre o Bloco de Notas, digita,
  aperta e confere o documento lendo o controle de edição com ``EM_GETSEL`` /
  ``WM_GETTEXT``. Fora do CI: precisa de sessão gráfica e mexe no teclado da
  máquina inteira.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="A camada de sistema é toda Win32."
)

if sys.platform == "win32":
    from corretor.sistema import selecao, teclado


# ---------------------------------------------------------------------------
# Lógica pura — roda no CI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selecionado",
    [
        ".",
        ",",
        "...",
        "!?",
        " ",
        "   ",
        "\r\n",
        "\n",
        " \r\n",
        "",
        "—",
    ],
    ids=repr,
)
def test_pontuacao_e_espaco_pedem_outra_extensao(selecionado: str) -> None:
    """Foi o que o Notepad devolveu para ``coracao.|``: só o ponto.

    Sem reestender, quem chamou colaria ``coração.`` por cima de ``.`` e o
    documento viraria ``coracaocoração.`` — medido, não hipotético.
    """
    assert selecao._precisa_estender(selecionado) is True


@pytest.mark.parametrize(
    "selecionado",
    [
        "coracao",
        "coracao ",
        "coracao.",
        "coração",
        "ímã",
        "a",
        "2024",
        "R$ 10",
        "\r\ncoracao",
    ],
    ids=repr,
)
def test_selecao_com_conteudo_para_de_estender(selecionado: str) -> None:
    assert selecao._precisa_estender(selecionado) is False


def test_digito_conta_como_conteudo() -> None:
    """Se o usuário acabou de digitar ``2024``, estender de novo pegaria a
    palavra anterior junto e a correção seria colada por cima de um trecho
    maior do que devia."""
    assert selecao._precisa_estender("2024") is False


def test_teto_de_extensoes_extra() -> None:
    """Duas cobre pontuação e quebra de linha. Mais engoliria a palavra
    anterior à que o usuário quis corrigir."""
    assert selecao._MAXIMO_DE_EXTENSOES_EXTRA == 2


def test_setas_sao_teclas_estendidas() -> None:
    """Sem o flag de estendida o Windows entrega a seta do teclado numérico."""
    for vk in (teclado.VK_LEFT, teclado.VK_RIGHT):
        assert teclado._evento(vk, soltar=False).ki.dwFlags & 0x0001, hex(vk)


# ---------------------------------------------------------------------------
# Orquestração com dublês — roda no CI
# ---------------------------------------------------------------------------


class _Alvo:
    """Dublê de app de destino: guarda o que cada leitura deve devolver."""

    def __init__(self, leituras: list[str | None]) -> None:
        self.leituras = list(leituras)
        self.extensoes = 0
        self.desfazeres = 0

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(selecao, "_estender_selecao", self._estender)
        monkeypatch.setattr(selecao, "desfazer_selecao", self._desfazer)
        monkeypatch.setattr(selecao.area_transferencia, "ler_selecao", self._ler)

    def _estender(self) -> None:
        self.extensoes += 1

    def _desfazer(self) -> None:
        self.desfazeres += 1

    def _ler(self, timeout: float = 0.6) -> str | None:
        assert self.leituras, "leu mais vezes do que o teste previu"
        return self.leituras.pop(0)


def test_palavra_limpa_gasta_uma_injecao_so(monkeypatch: pytest.MonkeyPatch) -> None:
    alvo = _Alvo(["coracao"])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() == "coracao"
    assert alvo.extensoes == 1
    assert alvo.desfazeres == 0, "a seleção tem que ficar ATIVA para colarem por cima"


def test_espaco_no_fim_vem_junto_e_nao_reestende(monkeypatch: pytest.MonkeyPatch) -> None:
    """``coracao `` já tem conteúdo; reestender comeria a palavra anterior."""
    alvo = _Alvo(["coracao "])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() == "coracao "
    assert alvo.extensoes == 1


def test_pontuacao_dispara_a_segunda_extensao(monkeypatch: pytest.MonkeyPatch) -> None:
    alvo = _Alvo([".", "coracao."])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() == "coracao."
    assert alvo.extensoes == 2
    assert alvo.desfazeres == 0


def test_quebra_de_linha_dispara_a_segunda_extensao(monkeypatch: pytest.MonkeyPatch) -> None:
    alvo = _Alvo(["\r\n", "coracao\r\n"])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() == "coracao\r\n"
    assert alvo.extensoes == 2


def test_para_no_teto_mesmo_sem_achar_letra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Documento só de pontuação: não pode virar laço infinito nem estender
    para sempre. Três injeções no total, e devolve o que houver."""
    alvo = _Alvo([".", "..", "..."])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() == "..."
    assert alvo.extensoes == 1 + selecao._MAXIMO_DE_EXTENSOES_EXTRA


def test_sem_nada_a_esquerda_devolve_none_e_colapsa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cursor no início do documento.

    Colapsar aqui custa o cursor andar um caractere; não colapsar custaria o
    usuário perder a palavra num terminal, onde Ctrl+C interrompe em vez de
    copiar e a seleção fica viva sem a gente saber.
    """
    alvo = _Alvo([None])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() is None
    assert alvo.extensoes == 1
    assert alvo.desfazeres == 1


def test_leitura_que_falha_no_meio_nao_devolve_texto_velho(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O bug que comeria texto do usuário.

    A primeira leitura trouxe ``.``; estendemos de novo e a segunda leitura
    falhou. A seleção agora é MAIOR que ``.`` e não sabemos por quanto.
    Devolver ``.`` faria quem chamou colar uma correção de um caractere por
    cima da palavra inteira. Desistimos e colapsamos.
    """
    alvo = _Alvo([".", None])
    alvo.instalar(monkeypatch)
    assert selecao.selecionar_palavra_anterior() is None
    assert alvo.desfazeres == 1


def test_timeout_chega_em_todas_as_leituras(monkeypatch: pytest.MonkeyPatch) -> None:
    recebidos: list[float] = []

    def ler(timeout: float = 0.6) -> str | None:
        recebidos.append(timeout)
        return "." if len(recebidos) == 1 else "coracao."

    monkeypatch.setattr(selecao, "_estender_selecao", lambda: None)
    monkeypatch.setattr(selecao.area_transferencia, "ler_selecao", ler)
    selecao.selecionar_palavra_anterior(timeout=0.25)
    assert recebidos == [0.25, 0.25]


def test_falha_ao_injetar_sobe_para_quem_chamou(monkeypatch: pytest.MonkeyPatch) -> None:
    """Janela elevada (UIPI) bloqueia o SendInput. Engolir viraria um atalho
    que não faz nada e não explica por quê."""

    def estourar() -> None:
        raise teclado.FalhaAoEnviarTeclas("janela elevada")

    monkeypatch.setattr(selecao, "_estender_selecao", estourar)
    with pytest.raises(teclado.FalhaAoEnviarTeclas):
        selecao.selecionar_palavra_anterior()


# ---------------------------------------------------------------------------
# Notepad de verdade — fora do CI
# ---------------------------------------------------------------------------

_WM_SETTEXT, _WM_GETTEXT, _WM_GETTEXTLENGTH = 0x000C, 0x000D, 0x000E
_EM_GETSEL, _EM_SETSEL = 0x00B0, 0x00B1

if sys.platform == "win32":
    _u = ctypes.WinDLL("user32", use_last_error=True)
    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _u.GetForegroundWindow.restype = wintypes.HWND
    _u.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    _u.FindWindowW.restype = wintypes.HWND
    _u.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.c_void_p)
    _u.GetWindowThreadProcessId.restype = wintypes.DWORD
    _u.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    _u.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    _u.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p)
    _u.SendMessageW.restype = ctypes.c_ssize_t
    _PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _u.EnumChildWindows.argtypes = (wintypes.HWND, _PROC, wintypes.LPARAM)
    #: EM_GETSEL/EM_SETSEL trocam posições por VALOR (o retorno traz
    #: início e fim empacotados). Ponteiro não serviria: o Windows não
    #: marshala esses ponteiros entre processos.
    _enviar_valor = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
    )(("SendMessageW", _u))


def _editor_do_notepad() -> int:
    """HWND do controle de edição.

    No Windows 11 ele é NETO da janela de topo — fica dentro de um
    ``DesktopChildSiteBridge`` do WinUI. ``FindWindowEx``, que só enxerga
    filhos diretos, devolve 0 e todo ``SendMessage`` seguinte vira lixo
    silencioso. Enumeramos a árvore inteira.
    """
    pai = _u.FindWindowW("Notepad", None)
    if not pai:
        return 0
    achado = 0

    def visitar(hwnd, _):
        nonlocal achado
        buf = ctypes.create_unicode_buffer(256)
        _u.GetClassNameW(hwnd, buf, 256)
        if buf.value in ("RichEditD2DPT", "RICHEDIT50W", "Edit"):
            achado = hwnd
            return False
        return True

    _u.EnumChildWindows(pai, _PROC(visitar), 0)
    return achado


def _classe_em_foco() -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u.GetClassNameW(_u.GetForegroundWindow(), buf, 256)
    return buf.value


def _forcar_foco(hwnd: int) -> None:
    atual = _k.GetCurrentThreadId()
    outro = _u.GetWindowThreadProcessId(_u.GetForegroundWindow(), None)
    anexou = bool(_u.AttachThreadInput(atual, outro, True)) if outro != atual else False
    try:
        _u.ShowWindow(hwnd, 9)
        _u.BringWindowToTop(hwnd)
        _u.SetForegroundWindow(hwnd)
    finally:
        if anexou:
            _u.AttachThreadInput(atual, outro, False)


@pytest.mark.gui
@pytest.mark.sistema
class TestNotepadDeVerdade:
    """Abre o Bloco de Notas e mede o que o atalho faz no documento real.

    Toda injeção é precedida de uma checagem de foco. Se a janela em primeiro
    plano deixar de ser o Notepad — o usuário clicou em outra coisa — o teste
    pula em vez de digitar na janela dele.
    """

    @pytest.fixture
    def notepad(self):
        processo = subprocess.Popen(["notepad.exe"])
        try:
            for _ in range(40):
                time.sleep(0.25)
                janela = _u.FindWindowW("Notepad", None)
                if janela and _editor_do_notepad():
                    break
            else:
                pytest.skip("o Notepad não abriu a tempo")
            _forcar_foco(janela)
            time.sleep(0.6)
            if _classe_em_foco() != "Notepad":
                pytest.skip("não consegui trazer o Notepad para primeiro plano")
            yield
        finally:
            editor = _editor_do_notepad()
            if editor:
                _u.SendMessageW(editor, _WM_SETTEXT, 0, ctypes.c_wchar_p(""))
                time.sleep(0.2)
            subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
            processo.wait(timeout=10)

    # -- utilitários -------------------------------------------------------

    @staticmethod
    def _guardar_foco() -> None:
        if _classe_em_foco() != "Notepad":
            pytest.skip("o foco saiu do Notepad; abortando antes de injetar tecla")

    @staticmethod
    def _documento() -> str:
        editor = _editor_do_notepad()
        tamanho = _u.SendMessageW(editor, _WM_GETTEXTLENGTH, 0, None)
        buf = ctypes.create_unicode_buffer(int(tamanho) + 1)
        _u.SendMessageW(editor, _WM_GETTEXT, int(tamanho) + 1, ctypes.byref(buf))
        return buf.value

    @staticmethod
    def _intervalo_selecionado() -> tuple[int, int]:
        bruto = _enviar_valor(_editor_do_notepad(), _EM_GETSEL, 0, 0)
        return bruto & 0xFFFF, (bruto >> 16) & 0xFFFF

    def _preparar(self, conteudo: str, cursor: int | None = None) -> None:
        editor = _editor_do_notepad()
        _u.SendMessageW(editor, _WM_SETTEXT, 0, ctypes.c_wchar_p(conteudo))
        posicao = len(conteudo) if cursor is None else cursor
        _enviar_valor(editor, _EM_SETSEL, posicao, posicao)
        time.sleep(0.15)
        self._guardar_foco()

    # -- os cinco casos ----------------------------------------------------

    @pytest.mark.parametrize(
        ("documento", "esperado"),
        [
            ("nao consigo acentuar o coracao", "coracao"),
            ("nao consigo acentuar o coracao ", "coracao "),
            ("nao consigo acentuar o coracao.", "coracao."),
            ("nao consigo acentuar o coracao,", "coracao,"),
        ],
        ids=["fim-da-palavra", "espaco-no-fim", "ponto-no-fim", "virgula-no-fim"],
    )
    def test_seleciona_a_palavra_e_deixa_a_selecao_viva(
        self, notepad, documento: str, esperado: str
    ) -> None:
        self._preparar(documento)
        assert selecao.selecionar_palavra_anterior() == esperado
        inicio, fim = self._intervalo_selecionado()
        assert fim - inicio == len(esperado), "a seleção precisa ficar ATIVA para colarem por cima"

    def test_correcao_de_ponta_a_ponta(self, notepad) -> None:
        from corretor.sistema import area_transferencia

        self._preparar("nao consigo acentuar o coracao")
        assert selecao.selecionar_palavra_anterior() == "coracao"
        self._guardar_foco()
        assert area_transferencia.substituir_selecao("coração") is True
        time.sleep(0.35)
        assert self._documento() == "nao consigo acentuar o coração"

    def test_pontuacao_sobrevive_a_correcao(self, notepad) -> None:
        """Uma extensão só devolveria ``.`` e o documento viraria
        ``coracaocoração.``. Aconteceu de verdade antes do teto de extensões."""
        from corretor.sistema import area_transferencia

        self._preparar("nao consigo acentuar o coracao.")
        assert selecao.selecionar_palavra_anterior() == "coracao."
        self._guardar_foco()
        assert area_transferencia.substituir_selecao("coração.") is True
        time.sleep(0.35)
        assert self._documento() == "nao consigo acentuar o coração."

    def test_documento_vazio_devolve_none_sem_travar(self, notepad) -> None:
        self._preparar("")
        inicio = time.perf_counter()
        assert selecao.selecionar_palavra_anterior() is None
        assert time.perf_counter() - inicio < 3.0, "não pode ficar pendurado"
        assert self._intervalo_selecionado() == (0, 0)
        assert self._documento() == ""

    def test_inicio_do_documento_nao_estraga_nada(self, notepad) -> None:
        self._preparar("coracao", cursor=0)
        assert selecao.selecionar_palavra_anterior() is None
        assert self._documento() == "coracao"

    def test_desfazer_selecao_salva_a_palavra(self, notepad) -> None:
        """O caso "palavra já estava certa": sem colapsar, a próxima tecla do
        usuário apagaria a palavra inteira."""
        self._preparar("nao consigo acentuar o coracao")
        assert selecao.selecionar_palavra_anterior() == "coracao"

        self._guardar_foco()
        selecao.desfazer_selecao()
        time.sleep(0.2)
        assert self._intervalo_selecionado() == (30, 30), "colapsa para a ponta DIREITA"

        self._guardar_foco()
        with teclado.injetando():
            teclado.soltar_modificadores()
            teclado.enviar_combinacao(0x58)  # tecla X
        time.sleep(0.3)
        assert self._documento() == "nao consigo acentuar o coracaox"
