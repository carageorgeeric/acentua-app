"""O motor offline: recebe texto sem acento, devolve texto acentuado.

A ordem de decisão para cada palavra é sempre a mesma, e é o que torna o
comportamento previsível para quem usa:

1. preferência que o usuário já ensinou para aquela chave;
2. regra de contexto;
3. frequência do corpus.

Fora dessa ordem, só existem freios: URL, e-mail, código e número nunca são
tocados, e uma palavra que já veio acentuada corretamente fica como está.
"""

from __future__ import annotations

from dataclasses import dataclass

from corretor.nucleo import contexto
from corretor.nucleo.dicionario import Dicionario
from corretor.nucleo.normalizacao import (
    Token,
    aplicar_capitalizacao,
    chave,
    deve_ignorar,
    partes_compostas,
    tem_acento,
    tokenizar,
)
from corretor.tipos import Alteracao, Candidato, FonteDePreferencias, Resultado, Sugestao

__all__ = ["CorretorOffline", "vizinhancas"]

#: Uma segunda grafia só vira alternativa de popup se tiver ao menos esta fatia
#: da frequência da grafia líder. Sem o corte, todo `o` viraria "ou `ó`?".
LIMIAR_ALTERNATIVA = 0.05

#: Quantas alternativas acompanham uma alteração (o popup mostra 3 opções).
MAX_ALTERNATIVAS = 2

#: Pontuação que encerra frase — depois dela, a próxima palavra começa do zero.
_FIM_DE_FRASE = ".!?…\n\r;"


def _inicio_de_frase(tokens: list[Token], indice: int) -> bool:
    """Verdadeiro no começo do texto ou logo depois de pontuação final."""
    for anterior in reversed(tokens[:indice]):
        if anterior.e_palavra:
            return False
        if any(c in _FIM_DE_FRASE for c in anterior.texto):
            return True
    return True


def vizinhancas(tokens: list[Token]) -> dict[int, tuple[str | None, str | None, bool]]:
    """Para cada token corrigível, ``(anterior, seguinte, abre_frase)``.

    Só entram os tokens que são palavra e que não caem em ``deve_ignorar``;
    quem não está no mapa é separador, URL, código ou número, e nem chega a
    ser considerado. Os vizinhos pulam esses buracos: em "vou a (mesmo!) casa"
    o anterior de ``casa`` é ``mesmo``, não a parêntese.

    Vive aqui fora da classe porque a revisão de frase precisa exatamente da
    mesma vizinhança para reperguntar ao motor sobre uma palavra específica.
    Duas cópias desta lógica divergiriam, e aí o popup mostraria uma ordem de
    opções diferente da que a correção automática usou.
    """
    indices = [i for i, t in enumerate(tokens) if t.e_palavra and not deve_ignorar(t.texto)]
    mapa: dict[int, tuple[str | None, str | None, bool]] = {}
    for posicao, i in enumerate(indices):
        abre_frase = _inicio_de_frase(tokens, i)
        anterior = None
        if not abre_frase and posicao > 0:
            anterior = tokens[indices[posicao - 1]].texto
        seguinte = (
            tokens[indices[posicao + 1]].texto if posicao + 1 < len(indices) else None
        )
        mapa[i] = (anterior, seguinte, abre_frase)
    return mapa


@dataclass(frozen=True, slots=True)
class _Escolha:
    """Resultado interno da decisão sobre uma palavra."""

    palavra: str
    alternativas: tuple[str, ...]
    confianca: float


class CorretorOffline:
    """Motor de correção baseado em dicionário. Implementa `MotorDeCorrecao`."""

    __slots__ = ("dicionario", "preferencias")

    def __init__(
        self,
        dicionario: Dicionario,
        preferencias: FonteDePreferencias | None = None,
    ) -> None:
        self.dicionario = dicionario
        self.preferencias = preferencias

    # -- API pública -------------------------------------------------------

    def corrigir(self, texto: str) -> Resultado:
        if not texto:
            return Resultado(texto)

        tokens = tokenizar(texto)
        vizinhos = vizinhancas(tokens)

        pedacos: list[str] = []
        alteracoes: list[Alteracao] = []

        for i, token in enumerate(tokens):
            contexto_do_token = vizinhos.get(i)
            if contexto_do_token is None:
                pedacos.append(token.texto)
                continue

            anterior, seguinte, inicio = contexto_do_token
            escolha = self._decidir(token.texto, anterior, seguinte, inicio)
            pedacos.append(escolha.palavra)
            if escolha.palavra != token.texto:
                alteracoes.append(
                    Alteracao(
                        original=token.texto,
                        corrigida=escolha.palavra,
                        inicio=token.inicio,
                        fim=token.fim,
                        alternativas=escolha.alternativas,
                        confianca=escolha.confianca,
                    )
                )

        return Resultado("".join(pedacos), tuple(alteracoes))

    def sugestoes(
        self,
        palavra: str,
        anterior: str | None = None,
        seguinte: str | None = None,
        limite: int = 3,
    ) -> list[Sugestao]:
        """Opções ordenadas para o popup, incluindo o que o usuário digitou.

        A palavra original entra na lista sempre que for grafia válida, mesmo
        que fique em último: trocar de ideia tem que ser possível sem digitar.
        """
        if limite <= 0:
            return []

        candidatos = self._candidatos_ordenados(palavra, anterior, seguinte, False)
        if not candidatos:
            return [Sugestao(palavra, 1.0)]

        total = sum(c.frequencia for c in candidatos) or 1
        escolhidos = candidatos[:limite]

        baixa = palavra.lower()
        if limite > 1 and all(c.palavra != baixa for c in escolhidos):
            original = next((c for c in candidatos if c.palavra == baixa), None)
            if original is not None:
                escolhidos = escolhidos[: limite - 1] + [original]

        return [
            Sugestao(aplicar_capitalizacao(palavra, c.palavra), c.frequencia / total)
            for c in escolhidos
        ]

    # -- decisão -----------------------------------------------------------

    def _decidir(
        self,
        original: str,
        anterior: str | None,
        seguinte: str | None,
        inicio_de_frase: bool,
    ) -> _Escolha:
        candidatos = self.dicionario.candidatos(original)
        if not candidatos:
            return self._decidir_composta(original, anterior, seguinte, inicio_de_frase)

        # Quem já escreveu com acento sabia o que queria.
        baixa = original.lower()
        if tem_acento(original) and any(c.palavra == baixa for c in candidatos):
            return _Escolha(original, (), 1.0)

        ordenados = self._aplicar_prioridades(candidatos, original, anterior, seguinte, inicio_de_frase)
        vencedor = ordenados[0]
        total = sum(c.frequencia for c in candidatos) or 1
        corrigida = aplicar_capitalizacao(original, vencedor.palavra)

        if corrigida == original:
            return _Escolha(original, (), vencedor.frequencia / total)

        return _Escolha(
            corrigida,
            self._alternativas(ordenados, candidatos, original),
            vencedor.frequencia / total,
        )

    def _aplicar_prioridades(
        self,
        candidatos: list[Candidato],
        original: str,
        anterior: str | None,
        seguinte: str | None,
        inicio_de_frase: bool,
    ) -> list[Candidato]:
        k = chave(original)

        if self.preferencias is not None:
            preferida = self.preferencias.preferida(k)
            if preferida is not None:
                escolhida = next((c for c in candidatos if c.palavra == preferida), None)
                if escolhida is not None:
                    return [escolhida] + [c for c in candidatos if c is not escolhida]

        return contexto.reordenar(candidatos, k, anterior, seguinte, inicio_de_frase)

    def _candidatos_ordenados(
        self,
        palavra: str,
        anterior: str | None,
        seguinte: str | None,
        inicio_de_frase: bool,
    ) -> list[Candidato]:
        candidatos = self.dicionario.candidatos(palavra)
        if not candidatos:
            return []
        return self._aplicar_prioridades(candidatos, palavra, anterior, seguinte, inicio_de_frase)

    def _alternativas(
        self,
        ordenados: list[Candidato],
        candidatos: list[Candidato],
        original: str,
    ) -> tuple[str, ...]:
        """Só oferece alternativa quando a ambiguidade é real.

        O corte é sobre a grafia mais frequente do grupo, não sobre a escolhida:
        assim o popup mostra o mesmo conjunto de opções independentemente de
        qual regra de contexto disparou.
        """
        teto = max(c.frequencia for c in candidatos)
        piso = teto * LIMIAR_ALTERNATIVA
        sobrando = [c for c in ordenados[1:] if c.frequencia >= piso]
        return tuple(
            aplicar_capitalizacao(original, c.palavra) for c in sobrando[:MAX_ALTERNATIVAS]
        )

    # -- palavras compostas ------------------------------------------------

    def _decidir_composta(
        self,
        original: str,
        anterior: str | None,
        seguinte: str | None,
        inicio_de_frase: bool,
    ) -> _Escolha:
        """`nao-sei` e `d'agua` não estão no corpus; corrige parte por parte.

        O corpus tem só vinte compostos hifenizados, então a regra prática é:
        tenta o token inteiro (feito por quem chamou), e só então quebra.
        """
        partes = partes_compostas(original)
        if len(partes) < 3:
            return _Escolha(original, (), 1.0)

        palavras = partes[::2]
        novas: list[str] = []
        mudou = False
        for indice, parte in enumerate(palavras):
            antes = palavras[indice - 1] if indice > 0 else anterior
            depois = palavras[indice + 1] if indice + 1 < len(palavras) else seguinte
            escolha = self._decidir(parte, antes, depois, inicio_de_frase and indice == 0)
            novas.append(escolha.palavra)
            mudou = mudou or escolha.palavra != parte

        if not mudou:
            return _Escolha(original, (), 1.0)

        reconstruido = list(partes)
        reconstruido[::2] = novas
        return _Escolha("".join(reconstruido), (), 1.0)
