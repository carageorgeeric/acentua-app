"""Configuração do Acentua e memória das escolhas do usuário.

Tudo mora em ``%APPDATA%/Acentua`` para que atualizar ou reinstalar o programa
não apague as preferências de quem usa.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from corretor import NOME_APP

ATALHO_CORRIGIR_PADRAO = "<ctrl>+<alt>+c"
ATALHO_SUGESTOES_PADRAO = "<ctrl>+<alt>+s"
#: ``Ctrl+Alt+D`` não repete dedo: mindinho no Ctrl, polegar no Alt e o dedo
#: médio no D, que já é a casa dele. É o atalho apertado no meio da digitação,
#: então é o que mais precisa ser confortável.
ATALHO_ULTIMA_PALAVRA_PADRAO = "<ctrl>+<alt>+d"

#: Combinações que o Acentua se recusa a registrar, com o motivo.
#:
#: Um atalho global é registrado para o Windows INTEIRO e nós engolimos a tecla
#: antes de qualquer programa ver. Registrar ``Ctrl+C`` aqui não daria um atalho
#: ao Acentua: tiraria o Copiar de todos os programas da máquina enquanto ele
#: estivesse aberto. As duas primeiras famílias existem por isso; as reservadas
#: do sistema nem chegam até nós, ou chegam duplicadas.
ATALHOS_PROIBIDOS: dict[str, str] = {
    # Edição — quebrar qualquer uma destas inutiliza o computador.
    "<ctrl>+c": "Copiar",
    "<ctrl>+v": "Colar",
    "<ctrl>+x": "Recortar",
    "<ctrl>+z": "Desfazer",
    "<ctrl>+y": "Refazer",
    "<ctrl>+a": "Selecionar tudo",
    # Arquivo e navegação — usadas em praticamente todo programa.
    "<ctrl>+s": "Salvar",
    "<ctrl>+p": "Imprimir",
    "<ctrl>+f": "Localizar",
    "<ctrl>+n": "Novo",
    "<ctrl>+o": "Abrir",
    "<ctrl>+w": "Fechar a aba",
    "<ctrl>+t": "Nova aba",
    # Reservadas do Windows — não chegam até nós, ou disparam duplicado.
    "<alt>+<space>": "menu da janela",
    "<ctrl>+<alt>+<space>": "menu da janela",
    "<ctrl>+<alt>+<delete>": "tela de segurança do Windows",
    "<ctrl>+<shift>+<esc>": "Gerenciador de Tarefas",
    "<ctrl>+<esc>": "menu Iniciar",
    "<alt>+<tab>": "troca de janela",
    "<alt>+<f4>": "fechar o programa",
}


def motivo_para_recusar(combinacao: str) -> str | None:
    """Por que este atalho não pode ser usado, ou ``None`` se puder."""
    uso = ATALHOS_PROIBIDOS.get(combinacao.strip().lower())
    return f"O Windows já usa essa combinação para {uso}." if uso else None


def pasta_de_dados() -> Path:
    """Onde guardamos config e preferências, criada na primeira chamada."""
    raiz = os.environ.get("APPDATA") or str(Path.home())
    pasta = Path(raiz) / NOME_APP
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _gravar_json(caminho: Path, dados: Any) -> None:
    """Grava de forma atômica: um crash no meio não corrompe o arquivo."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=caminho.parent,
        prefix=caminho.name,
        suffix=".tmp",
        delete=False,
    ) as tmp:
        json.dump(dados, tmp, ensure_ascii=False, indent=2)
        temporario = Path(tmp.name)
    temporario.replace(caminho)


def _ler_json(caminho: Path) -> Any | None:
    try:
        with caminho.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@dataclass(slots=True)
class Config:
    """Preferências de comportamento, editáveis pela janela de configurações."""

    atalho_corrigir: str = ATALHO_CORRIGIR_PADRAO
    atalho_sugestoes: str = ATALHO_SUGESTOES_PADRAO
    #: Corrige a palavra imediatamente antes do cursor, sem precisar selecionar.
    #: É o atalho para usar no meio da digitação, sem tirar a mão do teclado.
    atalho_ultima_palavra: str = ATALHO_ULTIMA_PALAVRA_PADRAO

    #: "claro", "escuro" ou "sistema" (segue o tema do Windows).
    tema: str = "sistema"

    #: Mostrar a confirmação discreta depois de corrigir.
    mostrar_aviso: bool = True
    #: Quando a seleção é uma palavra só e há dúvida, abrir o popup de escolhas.
    popup_em_palavra_unica: bool = True
    #: Ao corrigir uma frase inteira, perguntar palavra por palavra nas trocas
    #: que ficaram ambíguas antes de colar. Desligado, a frase sai direto com
    #: a grafia que o motor escolheu — o comportamento anterior à 1.2.
    revisar_frase: bool = True
    max_sugestoes: int = 3
    #: Lembrar da grafia escolhida quando o usuário decide no popup.
    aprender_escolhas: bool = True

    pausado: bool = False

    @property
    def caminho(self) -> Path:
        return pasta_de_dados() / "config.json"

    @classmethod
    def carregar(cls) -> Config:
        """Lê o disco ignorando chaves desconhecidas, para que uma versão
        antiga do arquivo nunca impeça o programa de abrir."""
        dados = _ler_json(pasta_de_dados() / "config.json")
        if not isinstance(dados, dict):
            return cls()
        conhecidos = {f.name for f in fields(cls)}
        config = cls(**{k: v for k, v in dados.items() if k in conhecidos})
        config._descartar_atalhos_perigosos()
        return config

    def _descartar_atalhos_perigosos(self) -> None:
        """Volta ao padrão qualquer atalho que sequestraria o sistema.

        O arquivo é texto e pode ter sido editado à mão, escrito por uma versão
        anterior sem esta checagem ou por um teste desastrado. Um ``Ctrl+C``
        gravado aqui tiraria o Copiar do computador inteiro no próximo boot, e
        o usuário não teria como ligar o programa para desfazer — o conserto
        tem que acontecer na leitura, não só na janela.
        """
        for campo, padrao in (
            ("atalho_corrigir", ATALHO_CORRIGIR_PADRAO),
            ("atalho_ultima_palavra", ATALHO_ULTIMA_PALAVRA_PADRAO),
            ("atalho_sugestoes", ATALHO_SUGESTOES_PADRAO),
        ):
            if motivo_para_recusar(getattr(self, campo)):
                setattr(self, campo, padrao)

    def salvar(self) -> None:
        _gravar_json(self.caminho, asdict(self))


class Preferencias:
    """Aprende a grafia que o usuário escolhe quando o corretor fica em dúvida.

    Guardamos contagens em vez da última escolha: um clique errado não desfaz
    um hábito, e a grafia mais escolhida vence naturalmente.
    """

    def __init__(self, escolhas: dict[str, Counter[str]] | None = None) -> None:
        self._escolhas: dict[str, Counter[str]] = escolhas or {}
        self._sujo = False

    @property
    def caminho(self) -> Path:
        return pasta_de_dados() / "preferencias.json"

    @classmethod
    def carregar(cls) -> Preferencias:
        dados = _ler_json(pasta_de_dados() / "preferencias.json")
        if not isinstance(dados, dict):
            return cls()
        escolhas = {
            chave: Counter(contagens)
            for chave, contagens in dados.items()
            if isinstance(contagens, dict)
        }
        return cls(escolhas)

    def preferida(self, chave: str) -> str | None:
        contagens = self._escolhas.get(chave)
        if not contagens:
            return None
        return contagens.most_common(1)[0][0]

    def registrar(self, chave: str, escolha: str) -> None:
        self._escolhas.setdefault(chave, Counter())[escolha] += 1
        self._sujo = True

    def esquecer(self, chave: str) -> None:
        if self._escolhas.pop(chave, None) is not None:
            self._sujo = True

    def limpar(self) -> None:
        if self._escolhas:
            self._escolhas.clear()
            self._sujo = True

    def salvar(self, forcar: bool = False) -> None:
        if not (self._sujo or forcar):
            return
        _gravar_json(
            self.caminho,
            {chave: dict(c) for chave, c in self._escolhas.items()},
        )
        self._sujo = False

    def __len__(self) -> int:
        return len(self._escolhas)
