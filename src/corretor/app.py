"""Orquestrador do Acentua: liga atalho global, clipboard, motor e interface.

## Modelo de threads

Este é o ponto mais frágil do programa, então está tudo concentrado aqui:

- **Thread principal — tkinter.** Um ``Tk()`` invisível vive durante todo o
  processo e é dono de qualquer widget. Popup, aviso e janela de configurações
  nascem dele.
- **Thread do pynput — atalhos.** Nunca toca em tkinter: entrega os callbacks
  via ``root.after(0, ...)``, que é a única chamada de tkinter segura entre
  threads.
- **Thread do pystray — bandeja.** Idem, despacha tudo com ``root.after``.
- **Threads efêmeras — clipboard.** Ler a seleção envolve injetar Ctrl+C e
  esperar o programa de destino responder (dezenas a centenas de milissegundos).
  Fazer isso na thread da interface travaria a tela, então cada correção roda em
  uma thread descartável que volta para a interface com ``root.after``.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import tkinter as tk
from typing import Callable

from corretor import DADOS, NOME_APP, VERSAO
from corretor.config import Config, Preferencias
from corretor.interface import ativar_ciencia_de_dpi, definir_identidade_no_windows
from corretor.interface.bandeja import Bandeja
from corretor.interface.popup import PopupSugestoes
from corretor.interface.toast import mostrar_toast
from corretor.nucleo import revisao
from corretor.nucleo.corretor import CorretorOffline
from corretor.nucleo.dicionario import Dicionario
from corretor.nucleo.normalizacao import chave, tokenizar
from corretor.sistema.area_transferencia import ler_selecao, substituir_selecao
from corretor.sistema.atalhos import GerenciadorAtalhos
from corretor.tipos import MotorDeCorrecao, Resultado


def _ja_esta_rodando() -> bool:
    """Impede uma segunda cópia.

    Dois processos disputando o mesmo atalho global fazem a correção acontecer
    duas vezes — a segunda em cima do texto já corrigido. Um mutex nomeado do
    Windows resolve: o segundo processo descobre no ato que perdeu a corrida.
    """
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    # ``Local\`` e não ``Global\``: criar um objeto no namespace global exige
    # o privilégio SeCreateGlobalPrivilege, e onde ele falta o CreateMutexW
    # devolve ACCESS_DENIED em vez de ALREADY_EXISTS — a trava passava batido e
    # subia uma segunda cópia. Duas cópias disputam o mesmo atalho e corrigem
    # o texto duas vezes, a segunda por cima do que a primeira já arrumou.
    # ``Local\`` é por sessão de logon, que é exatamente o escopo que queremos.
    handle = kernel32.CreateMutexW(None, False, f"Local\\{NOME_APP}-instancia-unica")
    if not handle:
        return False  # sem conseguir criar a trava, é melhor abrir do que travar
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


class Aplicacao:
    def __init__(self) -> None:
        self.config = Config.carregar()
        self.preferencias = Preferencias.carregar()

        dicionario = Dicionario.carregar()
        self.motor: MotorDeCorrecao = CorretorOffline(dicionario, self.preferencias)

        # Os dois antes do Tk(), obrigatoriamente. Sem ciência de DPI, num
        # monitor a 125%/150% o Windows entrega coordenadas virtualizadas e o
        # popup abriria longe do cursor; sem identidade própria, a barra de
        # tarefas etiqueta as janelas como "Python".
        ativar_ciencia_de_dpi()
        definir_identidade_no_windows(f"{NOME_APP}.{NOME_APP}")

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(NOME_APP)
        try:
            # ``default``: vale para toda janela do app, não só para esta. O
            # root vive oculto — quem aparece na barra de tarefas é a janela
            # de configurações, e ela nasce depois.
            self.root.iconbitmap(default=str(DADOS / "icone.ico"))
        except tk.TclError:
            pass  # sem ícone é feio, não é fatal

        self.popup = PopupSugestoes(self.root)
        self.atalhos = GerenciadorAtalhos(self.root)
        self.bandeja = Bandeja(self.root, self._acoes_da_bandeja(), self.estado)

        self._ocupado = False

    # ------------------------------------------------------------------ setup

    def _acoes_da_bandeja(self) -> dict[str, Callable[[], None]]:
        return {
            "pausar": self.alternar_pausa,
            "configuracoes": self.abrir_configuracoes,
            "ajuda": self.abrir_ajuda,
            "sair": self.encerrar,
        }

    def estado(self) -> dict:
        return {
            "nome": NOME_APP,
            "versao": VERSAO,
            "pausado": self.config.pausado,
            "atalho_corrigir": self.config.atalho_corrigir,
            "atalho_ultima_palavra": self.config.atalho_ultima_palavra,
            "atalho_sugestoes": self.config.atalho_sugestoes,
        }

    def executar(self) -> None:
        for combinacao, acao in self._atalhos_desejados().items():
            self.atalhos.registrar(combinacao, acao)
        self.atalhos.iniciar()
        self.bandeja.iniciar()
        self.root.after(
            600,
            lambda: self._aviso(
                f"{NOME_APP} ativo — selecione um texto e aperte "
                f"{_legivel(self.config.atalho_corrigir)}"
            ),
        )
        self.root.mainloop()

    # --------------------------------------------------------------- correção

    def corrigir_selecao(self) -> None:
        self._com_a_selecao(self._aplicar_correcao)

    def sugerir_selecao(self) -> None:
        self._com_a_selecao(self._oferecer_alternativas)

    def corrigir_ultima_palavra(self) -> None:
        """Corrige a palavra que o caret está encostando, sem seleção prévia.

        É o atalho para usar no meio da digitação: escreveu ``coracao``,
        apertou, virou ``coração``, seguiu escrevendo. O caret é a barrinha
        piscando do texto — nada a ver com o ponteiro do mouse. Selecionamos a
        palavra por trás dos panos, corrigimos e colamos por cima.
        """
        if not self._pode_comecar():
            return
        self._ocupado = True

        def trabalhar() -> None:
            # Import tardio: o módulo toca no Win32 e só é necessário aqui.
            from corretor.sistema.selecao import selecionar_palavra_do_caret

            texto: str | None
            try:
                texto = selecionar_palavra_do_caret()
            except Exception:
                texto = None
            self._na_interface(concluir, texto)

        def concluir(texto: str | None) -> None:
            self._ocupado = False
            if not texto or not texto.strip():
                self._aviso("Nenhuma palavra aqui para corrigir")
                return

            resultado = self.motor.corrigir(texto)
            if not resultado.houve_mudanca:
                # Deixamos uma seleção que o usuário não pediu. Se ela ficar
                # ativa, a próxima tecla que ele digitar APAGA a palavra.
                self._soltar_selecao()
                self._aviso("Já está acentuado")
                return

            self._escrever(resultado.texto, total=resultado.total)

        threading.Thread(target=trabalhar, daemon=True).start()

    def _soltar_selecao(self) -> None:
        """Colapsa a seleção que abrimos, devolvendo o cursor ao fim da palavra."""

        def trabalhar() -> None:
            from corretor.sistema.selecao import desfazer_selecao

            try:
                desfazer_selecao()
            except Exception:
                pass

        threading.Thread(target=trabalhar, daemon=True).start()

    def _pode_comecar(self) -> bool:
        """Falso quando disparar o atalho agora só faria estrago.

        O popup é a razão de a checagem existir. Ele está COM O FOCO enquanto
        pergunta, então um segundo ``Ctrl+Alt+C`` injetaria o ``Ctrl+C`` de
        ``ler_selecao`` dentro do próprio popup: leitura vazia, popup morto no
        meio da fila e nada colado.
        """
        return not (self.config.pausado or self._ocupado or self.popup.visivel)

    def _com_a_selecao(self, quando_pronto: Callable[[str], None]) -> None:
        """Lê a seleção fora da thread da interface e devolve o texto para ela."""
        if not self._pode_comecar():
            return
        self._ocupado = True

        def trabalhar() -> None:
            texto: str | None
            try:
                texto = ler_selecao()
            except Exception:
                texto = None
            self._na_interface(concluir, texto)

        def concluir(texto: str | None) -> None:
            self._ocupado = False
            if not texto or not texto.strip():
                self._aviso("Nada selecionado")
                return
            quando_pronto(texto)

        threading.Thread(target=trabalhar, daemon=True).start()

    def _aplicar_correcao(self, texto: str) -> None:
        resultado = self.motor.corrigir(texto)

        if self.config.popup_em_palavra_unica and _e_palavra_unica(texto):
            alternativas = self.motor.sugestoes(
                texto.strip(), limite=self.config.max_sugestoes
            )
            if len(alternativas) > 1:
                self.popup.mostrar(alternativas, self._escolher(texto))
                return

        if not resultado.houve_mudanca:
            self._aviso("Já está acentuado")
            return

        if self.config.revisar_frase:
            duvidas = revisao.duvidas(
                texto, resultado, self.motor, self.config.max_sugestoes
            )
            if duvidas:
                self.popup.perguntar(
                    duvidas,
                    lambda escolhas: self._concluir_revisao(texto, resultado, escolhas),
                )
                return

        self._escrever(resultado.texto, total=resultado.total)

    def _concluir_revisao(
        self, texto: str, resultado: Resultado, escolhas: dict[int, str]
    ) -> None:
        """Cola a frase inteira depois que o usuário respondeu (ou desistiu)."""
        final = revisao.aplicar(texto, resultado, escolhas)
        self._aprender_da_revisao(resultado, escolhas)

        if final == texto:
            # Só acontece se o usuário escolheu de volta tudo o que tinha
            # digitado. Colar o texto idêntico gastaria um passo de Ctrl+Z à
            # toa e piscaria a seleção sem motivo.
            self._aviso("Nada mudou")
            return

        self._escrever(final, total=revisao.total_de_mudancas(resultado, escolhas))

    def _aprender_da_revisao(
        self, resultado: Resultado, escolhas: dict[int, str]
    ) -> None:
        """Anota só o que o usuário CONTRARIOU, nunca o que ele apenas confirmou.

        Aprender de um Enter seria veneno: a preferência tem prioridade sobre a
        regra de contexto, então confirmar três vezes o `é` de "isso é bom"
        gravaria `é` como a grafia preferida de `e` e passaria a estragar
        "pão e queijo". Contrariar é o único sinal que significa alguma coisa.
        """
        if not self.config.aprender_escolhas:
            return
        aprendeu = False
        for indice, palavra in escolhas.items():
            alteracao = resultado.alteracoes[indice]
            if palavra != alteracao.corrigida:
                self.preferencias.registrar(chave(alteracao.original), palavra)
                aprendeu = True
        if aprendeu:
            self.preferencias.salvar()

    def _oferecer_alternativas(self, texto: str) -> None:
        alvo = texto.strip()
        alternativas = self.motor.sugestoes(alvo, limite=self.config.max_sugestoes)
        if not alternativas:
            self._aviso("Nenhuma alternativa para esta palavra")
            return
        self.popup.mostrar(alternativas, self._escolher(texto))

    def _escolher(self, original: str):
        """Monta o callback que o popup chama quando o usuário decide."""

        def ao_escolher(sugestao) -> None:
            self._escrever(_preservar_espacos(original, sugestao.palavra))
            if self.config.aprender_escolhas:
                self.preferencias.registrar(chave(original.strip()), sugestao.palavra)
                self.preferencias.salvar()

        return ao_escolher

    def _escrever(self, texto: str, total: int | None = None) -> None:
        """Cola o texto e só depois avisa — a ordem aqui é proposital.

        O aviso é uma janela. Se ela aparecesse enquanto o Ctrl+V ainda está a
        caminho, poderia tirar o foco do programa do usuário e o texto seria
        colado no lugar errado. Só avisamos com a colagem confirmada, e
        ``substituir_selecao`` diz se ela funcionou de verdade: em janela aberta
        como administrador o Windows bloqueia a injeção, e mentir "corrigido!"
        nesse caso seria pior que ficar calado.
        """

        def trabalhar() -> None:
            try:
                colou = substituir_selecao(texto)
            except Exception:
                colou = False
            self._na_interface(concluir, colou)

        def concluir(colou: bool) -> None:
            if not colou:
                self._aviso("Não consegui colar aqui — a janela pode estar como administrador")
            elif total is not None:
                plural = "s" if total != 1 else ""
                self._aviso(f"{total} palavra{plural} corrigida{plural} — Ctrl+Z desfaz")

        threading.Thread(target=trabalhar, daemon=True).start()

    def _aviso(self, mensagem: str) -> None:
        if self.config.mostrar_aviso:
            mostrar_toast(self.root, mensagem)

    def _na_interface(self, funcao: Callable[..., None], *args: object) -> None:
        """Agenda ``funcao`` na thread do tkinter, tolerando o app fechando.

        As threads de clipboard voltam por aqui. Se o usuário sair pelo menu
        enquanto uma correção está no ar, o Tk já foi destruído e ``after``
        levanta ``RuntimeError`` — não há mais interface para atualizar, e
        deixar a exceção subir só sujaria a saída com um traceback inútil.
        """
        try:
            self.root.after(0, funcao, *args)
        except (RuntimeError, tk.TclError):
            pass

    # ------------------------------------------------------------------ menu

    def alternar_pausa(self) -> None:
        self.config.pausado = not self.config.pausado
        self.config.salvar()
        self.bandeja.atualizar()
        self._aviso("Pausado" if self.config.pausado else "Ativo novamente")

    def abrir_configuracoes(self) -> None:
        """Abre as configurações com os atalhos globais suspensos.

        Suspender é obrigatório, não é zelo. O gravador de atalho precisa
        RECEBER a combinação para gravá-la, e o gancho de teclado engole a
        tecla antes de ela chegar em qualquer janela — inclusive na nossa. Com
        o listener ativo, tentar gravar ``Ctrl+Alt+C`` trava nos dois
        modificadores (a terceira tecla nunca chega) e ainda dispara uma
        correção por baixo, no programa que estava atrás.
        """
        from corretor.interface.janela_config import JanelaConfig

        self.atalhos.parar()
        configuracoes = JanelaConfig(
            self.root, self.config, self.preferencias, self._recarregar
        )

        def ao_fechar(evento: tk.Event) -> None:
            # <Destroy> sobe de cada widget filho; só o da própria janela conta.
            if evento.widget is configuracoes.janela:
                self.atalhos.iniciar()

        configuracoes.janela.bind("<Destroy>", ao_fechar, add="+")

    def abrir_ajuda(self) -> None:
        import webbrowser

        webbrowser.open("https://github.com/eric/acentua#readme")

    def _atalhos_desejados(self) -> dict[str, Callable[[], None]]:
        """Mapa atalho -> ação, montado a partir da configuração atual.

        Um dicionário descarta duplicatas sozinho: se o usuário apontar dois
        atalhos para a mesma tecla, o último vence em vez de o registro quebrar.
        """
        return {
            self.config.atalho_corrigir: self.corrigir_selecao,
            self.config.atalho_ultima_palavra: self.corrigir_ultima_palavra,
            self.config.atalho_sugestoes: self.sugerir_selecao,
        }

    def _recarregar(self) -> None:
        """Aplica configurações novas sem reiniciar o programa."""
        self.config.salvar()
        self.atalhos.recarregar(self._atalhos_desejados())
        self.bandeja.atualizar()

    def encerrar(self) -> None:
        self.preferencias.salvar()
        self.atalhos.parar()
        self.bandeja.parar()
        self.root.quit()
        self.root.destroy()


def _e_palavra_unica(texto: str) -> bool:
    return len([t for t in tokenizar(texto) if t.e_palavra]) == 1


def _preservar_espacos(original: str, palavra: str) -> str:
    """Devolve a palavra escolhida com os espaços que vieram na seleção.

    Selecionar por duplo clique costuma incluir o espaço seguinte; sem isso a
    substituição gruda a palavra na próxima.
    """
    esquerda = original[: len(original) - len(original.lstrip())]
    direita = original[len(original.rstrip()) :]
    return f"{esquerda}{palavra}{direita}"


def _legivel(combinacao: str) -> str:
    return combinacao.replace("<", "").replace(">", "").replace("+", "+").title()


def main() -> int:
    if _ja_esta_rodando():
        return 0
    Aplicacao().executar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
