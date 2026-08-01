"""Testes da camada de sistema (área de transferência e injeção de teclas).

O arquivo tem duas metades:

* **Lógica pura** — cálculo dos flags de scancode, tamanho das structs do
  Win32 e validação de argumentos. Não abre o clipboard nem injeta tecla
  nenhuma, então roda no CI sem marcador.
* **Integração real** (``@pytest.mark.sistema``) — escreve no clipboard da
  máquina de verdade. Fica fora do CI: num runner compartilhado outro
  processo pode segurar o clipboard e derrubar o build por motivo que não é
  o código.

``ler_selecao`` e ``substituir_selecao`` dependem de uma janela em foco com
texto selecionado; são validados à mão contra o Notepad (roteiro em
``CONTRIBUINDO.md``).
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import textwrap
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="A camada de sistema é toda Win32."
)

if sys.platform == "win32":
    from corretor.sistema import area_transferencia as clip
    from corretor.sistema import teclado


# ---------------------------------------------------------------------------
# Lógica pura — roda no CI
# ---------------------------------------------------------------------------


def test_tamanho_da_struct_input() -> None:
    """``SendInput`` recusa (ERROR_INVALID_PARAMETER) um cbSize errado.

    40 bytes em x64, 28 em x86: DWORD + padding + a maior variante da união
    (MOUSEINPUT, com o ULONG_PTR alinhado).
    """
    esperado = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(teclado._Entrada) == esperado


def test_evento_usa_scancode_e_zera_o_vk() -> None:
    evento = teclado._evento(teclado.VK_C, soltar=False)
    assert evento.ki.dwFlags & 0x0008  # KEYEVENTF_SCANCODE
    assert evento.ki.wScan != 0
    assert evento.ki.wVk == 0, "com scancode o Windows ignora wVk; deixá-lo preenchido confunde"


def test_evento_marca_o_keyup() -> None:
    assert not teclado._evento(teclado.VK_C, soltar=False).ki.dwFlags & 0x0002
    assert teclado._evento(teclado.VK_C, soltar=True).ki.dwFlags & 0x0002


def test_modificadores_da_direita_sao_estendidos() -> None:
    """Sem o flag de estendida o keyup vai para a tecla ESQUERDA e a direita gruda."""
    for vk in (teclado.VK_RCONTROL, teclado.VK_RMENU, teclado.VK_LWIN, teclado.VK_RWIN):
        assert teclado._evento(vk, soltar=True).ki.dwFlags & 0x0001, hex(vk)
    for vk in (teclado.VK_LCONTROL, teclado.VK_LMENU, teclado.VK_C):
        assert not teclado._evento(vk, soltar=True).ki.dwFlags & 0x0001, hex(vk)


def test_eventos_levam_a_marca_do_acentua() -> None:
    """``dwExtraInfo`` distingue tecla nossa de tecla que o usuário digitou."""
    assert teclado._evento(teclado.VK_V, soltar=False).ki.dwExtraInfo == teclado.MARCA_ACENTUA


def test_combinacao_vazia_nao_faz_nada() -> None:
    teclado.enviar_combinacao()


def test_erro_de_clipboard_e_claro_e_nao_abre_nada() -> None:
    """Com zero tentativas nem chegamos a chamar ``OpenClipboard``."""
    with pytest.raises(clip.ClipboardIndisponivel, match="OpenClipboard"):
        with clip._clipboard_aberto(tentativas=0):
            pytest.fail("não deveria ter entrado no bloco")


# ---------------------------------------------------------------------------
# Integração com o clipboard real — fora do CI
# ---------------------------------------------------------------------------

TEXTOS = [
    "texto simples",
    "ação, coração, ímã, cç, ÀÉÎÕÜ",
    "com emoji \U0001f680 no meio",
    "linha 1\nlinha 2\r\nlinha 3",
    "  espaços  nas  pontas  ",
    "",
    "x" * 100_000,
]

#: Programa auxiliar: abre o clipboard num OUTRO processo e segura por um
#: tempo, para exercitar o retry do ``OpenClipboard``.
#:
#: Duas descobertas que este código embute:
#:
#: * Não adianta segurar de outra thread do MESMO processo: o Windows associa
#:   o clipboard à *tarefa*, e a nossa segunda thread abre sem conflito.
#: * Não adianta o outro processo abrir com ``hwnd = NULL``: sem uma janela
#:   associada ele não vira o "dono" e ninguém é bloqueado. Só um
#:   ``OpenClipboard`` com HWND de verdade bloqueia os demais (com
#:   ERROR_ACCESS_DENIED). Daí o Tk oculto aqui.
_SEGURADOR = textwrap.dedent(
    """
    import ctypes, sys, time, tkinter
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetParent.argtypes = (wintypes.HWND,)
    user32.GetParent.restype = wintypes.HWND

    raiz = tkinter.Tk()
    raiz.withdraw()
    raiz.update()
    interno = raiz.winfo_id()
    janela = user32.GetParent(interno) or interno

    if not user32.OpenClipboard(wintypes.HWND(janela)):
        sys.exit(2)
    print("pronto", flush=True)
    time.sleep(float(sys.argv[1]))
    user32.CloseClipboard()
    """
)


def _segurar_clipboard(segundos: float) -> subprocess.Popen[str]:
    """Sobe o processo auxiliar e só volta quando ele já está segurando."""
    processo = subprocess.Popen(
        [sys.executable, "-c", _SEGURADOR, str(segundos)],
        stdout=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert processo.stdout is not None
    if processo.stdout.readline().strip() != "pronto":
        processo.kill()
        pytest.skip("o processo auxiliar não conseguiu abrir o clipboard")
    return processo


@pytest.mark.sistema
class TestClipboardReal:
    """Toca na área de transferência da máquina. Sempre restaura o que achou."""

    @pytest.fixture(autouse=True)
    def _preservar_clipboard(self):
        try:
            original = clip.ler()
        except clip.ClipboardIndisponivel:
            original = None
        yield
        clip.restaurar(original)

    @pytest.mark.parametrize("texto", TEXTOS, ids=lambda t: f"{len(t)}c")
    def test_round_trip(self, texto: str) -> None:
        clip.escrever(texto)
        assert clip.ler() == texto

    def test_nao_normaliza_quebras_de_linha(self) -> None:
        """Word usa \\r, o resto usa \\r\\n. Mexer nisso quebraria a colagem."""
        texto = "a\rb\nc\r\nd"
        clip.escrever(texto)
        assert clip.ler() == texto

    def test_ler_sem_texto_devolve_none(self) -> None:
        clip.limpar()
        assert clip.ler() is None

    def test_numero_de_sequencia_muda_a_cada_escrita(self) -> None:
        clip.escrever("um")
        antes = clip.numero_de_sequencia()
        clip.escrever("dois")
        assert clip.numero_de_sequencia() != antes

    def test_numero_de_sequencia_muda_mesmo_com_texto_igual(self) -> None:
        """É disso que ``ler_selecao`` depende: recopiar o mesmo texto conta."""
        clip.escrever("igual")
        antes = clip.numero_de_sequencia()
        clip.escrever("igual")
        assert clip.numero_de_sequencia() != antes

    def test_preservando_restaura_o_conteudo(self) -> None:
        clip.escrever("conteúdo do usuário")
        with clip.preservando() as anterior:
            assert anterior == "conteúdo do usuário"
            clip.escrever("texto temporário do corretor")
            assert clip.ler() == "texto temporário do corretor"
        assert clip.ler() == "conteúdo do usuário"

    def test_preservando_restaura_mesmo_com_excecao(self) -> None:
        clip.escrever("intocável")
        with pytest.raises(ZeroDivisionError), clip.preservando():
            clip.escrever("lixo")
            _ = 1 / 0
        assert clip.ler() == "intocável"

    def test_restaurar_none_esvazia(self) -> None:
        clip.escrever("alguma coisa")
        assert clip.restaurar(None) is True
        assert clip.ler() is None

    def test_escrever_espera_o_clipboard_liberar(self) -> None:
        """Outro processo segura o clipboard; o retry tem que dar conta."""
        processo = _segurar_clipboard(0.12)
        try:
            inicio = time.perf_counter()
            clip.escrever("chegou depois da espera")
            decorrido = time.perf_counter() - inicio
            assert clip.ler() == "chegou depois da espera"
            assert decorrido >= 0.05, "o retry não chegou a ser exercitado"
        finally:
            processo.wait(timeout=5)

    def test_erro_claro_quando_o_retry_esgota(self) -> None:
        processo = _segurar_clipboard(1.0)
        try:
            with pytest.raises(clip.ClipboardIndisponivel):
                with clip._clipboard_aberto(tentativas=3, espera=0.02):
                    pass
        finally:
            processo.wait(timeout=5)

    def test_clipboard_continua_utilizavel_depois_de_uma_falha(self) -> None:
        """Um ``CloseClipboard`` esquecido travaria o Windows inteiro."""
        processo = _segurar_clipboard(0.3)
        try:
            with pytest.raises(clip.ClipboardIndisponivel):
                with clip._clipboard_aberto(tentativas=2, espera=0.01):
                    pass
        finally:
            processo.wait(timeout=5)
        clip.escrever("de volta ao normal")
        assert clip.ler() == "de volta ao normal"


@pytest.mark.sistema
def test_soltar_modificadores_sem_nada_preso() -> None:
    """Sem tecla presa é um no-op; com tecla presa injeta keyup (ver Notepad)."""
    assert teclado.modificadores_pressionados() <= {"ctrl", "alt", "shift", "win"}
    teclado.soltar_modificadores()
