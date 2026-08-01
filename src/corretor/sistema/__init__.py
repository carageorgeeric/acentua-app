"""Camada de sistema: tudo que conversa diretamente com o Windows.

Três módulos, em ordem de dependência:

``teclado``
    Injeta teclas com ``SendInput`` (ctypes/user32) e sabe soltar os
    modificadores que o usuário está segurando fisicamente.
``area_transferencia``
    Clipboard Win32 puro. Usa ``teclado`` para disparar Ctrl+C / Ctrl+V.
``selecao``
    Seleciona a palavra que o usuário acabou de digitar, sem ele selecionar
    nada. Usa ``teclado`` para as setas e ``area_transferencia`` para ler o
    que ficou selecionado.
``atalhos``
    Atalho global via ``pynput``, entregando os callbacks na thread do tkinter.

Nada aqui importa a camada de interface: o fluxo é sempre interface -> sistema.
"""

from __future__ import annotations

__all__ = ["teclado", "area_transferencia", "selecao", "atalhos"]
