"""Tipos compartilhados entre as camadas do Corretor.

Este módulo é o contrato entre o núcleo (correção), o sistema (integração com
o Windows) e a interface (popup, toast, bandeja). Ele não importa nenhuma
outra parte do pacote, então pode ser usado de qualquer lugar sem risco de
import circular.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Candidato:
    """Uma grafia possível para uma palavra, com sua frequência no corpus."""

    palavra: str
    frequencia: int


@dataclass(frozen=True, slots=True)
class Sugestao:
    """Uma opção oferecida ao usuário no popup.

    ``confianca`` vai de 0 a 1 e é a fatia de frequência que esta grafia tem
    dentro do seu grupo de ambiguidade.
    """

    palavra: str
    confianca: float


@dataclass(frozen=True, slots=True)
class Alteracao:
    """Uma palavra que o corretor trocou dentro do texto.

    ``inicio`` e ``fim`` são índices no texto ORIGINAL, para que a interface
    consiga destacar ou desfazer uma troca específica.
    """

    original: str
    corrigida: str
    inicio: int
    fim: int
    alternativas: tuple[str, ...] = ()
    confianca: float = 1.0

    @property
    def ambigua(self) -> bool:
        return bool(self.alternativas)


@dataclass(frozen=True, slots=True)
class Duvida:
    """Uma pergunta sobre UMA palavra dentro de um texto já corrigido.

    É o que o popup precisa para perguntar "nesta frase, qual das grafias?"
    sem conhecer nem o motor nem o texto original: o trecho da frase que vem
    antes e depois da palavra (para o usuário saber de qual palavra estamos
    falando) e as grafias possíveis, a automática em primeiro lugar.

    ``indice`` é a posição em ``Resultado.alteracoes``, e é por ele que a
    escolha volta para o texto.
    """

    indice: int
    antes: str
    depois: str
    sugestoes: tuple[Sugestao, ...]

    @property
    def automatica(self) -> str:
        """A grafia que o motor escolheu sozinho — o padrão desta pergunta."""
        return self.sugestoes[0].palavra


@dataclass(frozen=True, slots=True)
class Resultado:
    """Saída de uma correção de texto completo."""

    texto: str
    alteracoes: tuple[Alteracao, ...] = ()

    @property
    def houve_mudanca(self) -> bool:
        return bool(self.alteracoes)

    @property
    def total(self) -> int:
        return len(self.alteracoes)

    @property
    def ambiguas(self) -> tuple[Alteracao, ...]:
        return tuple(a for a in self.alteracoes if a.ambigua)


class MotorDeCorrecao(Protocol):
    """O que a camada de aplicação espera de qualquer motor de correção.

    Existe para que a aplicação dependa do contrato, e não da implementação:
    trocar o motor é trocar o objeto, e os testes passam um dublê.
    """

    def corrigir(self, texto: str) -> Resultado: ...

    def sugestoes(
        self,
        palavra: str,
        anterior: str | None = None,
        seguinte: str | None = None,
        limite: int = 3,
    ) -> list[Sugestao]: ...


class FonteDePreferencias(Protocol):
    """Memória das escolhas do usuário, consultada pelo motor ao desempatar."""

    def preferida(self, chave: str) -> str | None: ...

    def registrar(self, chave: str, escolha: str) -> None: ...
