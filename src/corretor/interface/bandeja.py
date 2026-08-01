"""Ícone de bandeja (pystray).

O Acentua não tem janela principal: a bandeja é a única forma de o usuário
saber que ele está rodando e de pausá-lo ou fechá-lo.

O ``pystray`` roda o loop do ícone numa thread própria (``run_detached``), e
os callbacks de menu chegam nessa thread. Nenhum deles toca em tkinter
diretamente: tudo passa por ``root.after(0, ...)``.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

import pystray
from PIL import Image, ImageDraw

from .. import DADOS, NOME_APP, VERSAO

#: Chaves aceitas em ``acoes``. Uma chave ausente vira item desabilitado, para
#: a bandeja continuar utilizável enquanto o resto do app não está pronto.
ACAO_PAUSA = "alternar_pausa"
ACAO_CONFIGURACOES = "configuracoes"
ACAO_AJUDA = "ajuda"
ACAO_SAIR = "sair"

_ARQUIVO_ICONE = "icone.png"
_ARQUIVO_ICONE_PAUSADO = "icone_pausado.png"


def _icone_reserva(pausado: bool) -> Image.Image:
    """Ícone gerado na hora, caso o .png do pacote não exista.

    A bandeja sem imagem levanta exceção no pystray e derruba a thread — um
    quadrado feio é melhor que um app que some.
    """
    cor = (110, 110, 130, 255) if pausado else (79, 70, 229, 255)
    imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((2, 2, 61, 61), radius=14, fill=cor)
    desenho.text((22, 18), "a", fill=(255, 255, 255, 255))
    return imagem


def _carregar_icone(pausado: bool) -> Image.Image:
    caminho = DADOS / (_ARQUIVO_ICONE_PAUSADO if pausado else _ARQUIVO_ICONE)
    try:
        with Image.open(caminho) as arquivo:
            return arquivo.convert("RGBA").copy()
    except (OSError, ValueError):
        return _icone_reserva(pausado)


class Bandeja:
    """Ícone e menu na bandeja do Windows.

    Parameters
    ----------
    root:
        O ``Tk`` da aplicação. Só é usado para despachar callbacks com
        ``after`` — a bandeja não cria widget nenhum.
    acoes:
        Mapa de ``ACAO_*`` para função sem argumentos. Executadas na thread
        do tkinter.
    obter_estado:
        Chamada a cada abertura de menu. Deve devolver um dict com
        ``{"pausado": bool}``; a chave opcional ``"resumo"`` (str) vira o
        tooltip do ícone.
    """

    def __init__(
        self,
        root: tk.Tk,
        acoes: dict[str, Callable[[], None]],
        obter_estado: Callable[[], dict],
    ) -> None:
        self._raiz = root
        self._acoes = dict(acoes)
        self._obter_estado = obter_estado
        self._pausado_cache = self._pausado()
        self._icone = pystray.Icon(
            name=NOME_APP.lower(),
            icon=_carregar_icone(self._pausado_cache),
            title=self._tooltip(),
            menu=self._montar_menu(),
        )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        """Sobe o ícone em thread própria e devolve o controle na hora."""
        self._icone.run_detached()

    def parar(self) -> None:
        self._icone.visible = False
        self._icone.stop()

    def atualizar(self) -> None:
        """Relê o estado e reflete no ícone, no tooltip e no menu.

        Chame depois de pausar/retomar. Trocar ``icon`` é o que dessatura o
        desenho na bandeja.
        """
        self._pausado_cache = self._pausado()
        self._icone.icon = _carregar_icone(self._pausado_cache)
        self._icone.title = self._tooltip()
        self._icone.update_menu()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _estado(self) -> dict[str, Any]:
        try:
            return dict(self._obter_estado() or {})
        except Exception:  # noqa: BLE001 - callback de terceiro, não pode derrubar a bandeja
            return {}

    def _pausado(self) -> bool:
        return bool(self._estado().get("pausado", False))

    def _tooltip(self) -> str:
        estado = self._estado()
        resumo = estado.get("resumo")
        if resumo:
            return f"{NOME_APP} {VERSAO} — {resumo}"
        return f"{NOME_APP} {VERSAO} — " + (
            "pausado" if estado.get("pausado") else "ativo"
        )

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _despachar(self, chave: str) -> Callable[..., None]:
        def disparar(_icone: object = None, _item: object = None) -> None:
            acao = self._acoes.get(chave)
            if acao is None:
                return
            try:
                self._raiz.after(0, acao)
            except RuntimeError:
                pass
            if chave == ACAO_PAUSA:
                # O estado só muda depois que a ação roda na thread da UI;
                # a folga garante que já pegamos o valor novo.
                self._raiz.after(30, self.atualizar)

        return disparar

    def _tem(self, chave: str) -> bool:
        return chave in self._acoes

    def _montar_menu(self) -> pystray.Menu:
        item = pystray.MenuItem
        return pystray.Menu(
            item(f"{NOME_APP} {VERSAO}", None, enabled=False),
            # ``text`` e ``checked`` são reavaliados toda vez que o menu abre,
            # então consultam o estado real em vez do cache do ícone.
            item(
                lambda _i: "Retomar" if self._pausado() else "Pausar",
                self._despachar(ACAO_PAUSA),
                checked=lambda _i: self._pausado(),
                enabled=self._tem(ACAO_PAUSA),
            ),
            item(
                "Configurações",
                self._despachar(ACAO_CONFIGURACOES),
                default=True,
                enabled=self._tem(ACAO_CONFIGURACOES),
            ),
            item("Ajuda", self._despachar(ACAO_AJUDA), enabled=self._tem(ACAO_AJUDA)),
            pystray.Menu.SEPARATOR,
            item("Sair", self._despachar(ACAO_SAIR), enabled=self._tem(ACAO_SAIR)),
        )


__all__ = [
    "ACAO_AJUDA",
    "ACAO_CONFIGURACOES",
    "ACAO_PAUSA",
    "ACAO_SAIR",
    "Bandeja",
]
