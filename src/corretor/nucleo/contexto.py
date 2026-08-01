"""Desempate por contexto, quando a frequência do corpus não basta.

A frequência acerta a esmagadora maioria dos casos, mas erra feio em alguns
pares altíssimos de uso — `e`/`é` é o campeão: "isso e bom" quer `é`, "pao e
queijo" quer `e`. Aqui mora uma tabela declarativa de regras que olham apenas
a palavra anterior e a seguinte.

Duas decisões guiam a tabela inteira:

1. **Uma regra só existe para contrariar a frequência.** Se o candidato mais
   frequente já é o certo naquele contexto, não há regra — menos regra, menos
   jeito de errar. Por isso todas as regras de `esta` favorecem `esta` (o
   default é `está`), e todas as de `e` favorecem `é` (o default é `e`).
2. **Precisão acima de cobertura.** Uma regra errada é pior que regra nenhuma,
   porque o usuário deixa de conseguir prever o que o programa faz. Quando duas
   regras da mesma chave apontam para grafias diferentes, ninguém ganha e a
   ordem por frequência prevalece.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from corretor.nucleo.normalizacao import chave as normalizar
from corretor.tipos import Candidato

__all__ = ["REGRAS", "Regra", "parece_feminino", "parece_verbo_nos", "reordenar"]


# --------------------------------------------------------------------------
# Vocabulários
# --------------------------------------------------------------------------

#: Palavras que, antes de `e`, praticamente garantem o verbo `é`.
#:
#: Pronomes pessoais (`ele`, `ela`, `voce`) ficaram FORA de propósito: eles
#: coordenam sujeitos o tempo todo — "você e o João", "eu e a Maria" — e o
#: gatilho errava mais do que acertava. Quando há mesmo predicado, quem dispara
#: é a regra do que vem DEPOIS ("ele e legal", "ela e professora").
_SUJEITOS_DE_SER = frozenset(
    """
    isso isto aquilo quem tudo nada algo ninguem alguem que qual quais este
    esta esse essa aquele aquela aqueles aquelas nao ja nunca talvez tambem
    ainda so tampouco quando como onde porque quanto
    """.split()
)

_INTERROGATIVOS = frozenset(
    "onde como quando quem porque qual quais quanto quantos quanta quantas".split()
)

_ARTIGOS = frozenset("o a os as um uma uns umas".split())

_INTENSIDADE = frozenset(
    """
    muito muita muitos muitas mais menos bem tao super bastante quase realmente
    totalmente extremamente demais tudo so apenas praticamente sempre
    """.split()
)

#: Predicativos comuns. Depois de `e` puxam `é`; antes de `e` travam a regra,
#: porque "bom e barato" é coordenação de adjetivos, não predicado.
_ADJETIVOS = frozenset(
    """
    bom boa bons boas ruim ruins legal otimo otima otimos otimas pessimo pessima
    importante importantes possivel impossivel necessario necessaria preciso
    precisa verdade mentira melhor pior dificil facil faceis dificeis claro
    clara obvio obvia normal estranho estranha certo certa errado errada
    incrivel horrivel terrivel perfeito perfeita simples complicado complicada
    complexo complexa caro barato barata novo nova velho velha antigo antiga
    grande pequeno pequena rapido rapida lento lenta seguro segura util inutil
    engracado engracada triste feliz lindo linda bonito bonita feio feia
    interessante comum raro rara obrigatorio obrigatoria gratis gratuito
    gratuita real falso falsa justo injusto urgente chato chata divertido
    cansativo arriscado ideal essencial fundamental valido invalido correto
    incorreto suficiente insuficiente natural logico absurdo ridiculo serio
    seria exato exata oficial cedo tarde
    """.split()
)

#: Verbos e locuções que pedem complemento com preposição `a` — o gatilho
#: clássico da crase quando o que vem depois é feminino.
_REGEM_A = frozenset(
    """
    vou vamos vai vao ir fui foi foram iremos irei ira ia iam cheguei chegou
    chegamos chegaram chegar chega chegue levar levou levei leva levaram
    voltar voltei voltou voltamos volta volte ligar liguei ligou ligamos ligue
    recorrer recorri recorra retornar retornei retornou retorne entregar
    entreguei entregou entregue responder respondi respondeu responda respondam
    assistir assisti assistiu assista assistam obedecer obedeca pertence
    pertencem referente relativo relativamente devido gracas quanto respeito
    comparecer compareceu compareca dirigir dirigiu dirija encaminhar
    encaminhei encaminhou encaminhe enviar enviei enviou envie submeter
    destinado destinada destinados destinadas
    """.split()
)

#: Depois destes não há crase: são determinantes que já ocupam o lugar do artigo.
_BLOQUEIA_CRASE = frozenset(
    """
    um uma uns umas ela ele eles elas essa esse esta este aquela aquele minha
    meu sua seu tua teu nossa nosso vossa alguma algum outra outro toda todo
    qualquer cada muita muito pouca pouco mesma mesmo propria proprio voce
    voces mim ti si quem que se nos la ali aqui onde varias varios ambas
    """.split()
)

#: Substantivos femininos frequentes. Lista explícita de propósito: o atalho
#: "termina em -a" transformaria "vou a pé" e "fui a um lugar" em crase errada.
_FEMININOS = frozenset(
    """
    escola casa praia festa reuniao igreja loja padaria farmacia academia feira
    faculdade universidade biblioteca piscina cozinha sala rua cidade empresa
    aula aulas missa consulta entrevista prova viagem noite tarde manha mesa
    porta janela chuva familia policia delegacia prefeitura secretaria direcao
    gerencia equipe turma professora medica diretora mae avo irma amiga
    namorada esposa filha menina mulher pessoa verdade realidade pergunta
    resposta proposta oferta ideia historia musica danca teoria natureza saude
    internet televisao semana vez vezes hora horas questao situacao parte forma
    coisa area pagina tela lista conta ordem regra tarefa mensagem imagem
    versao opcao funcao materia disciplina reta conclusao decisao opiniao
    palavra frase linha coluna etapa fase meta chave porta janela luz agua
    comida bebida terra praca quadra estrada ponte rodovia clinica loteria
    """.split()
)

#: Terminações que garantem gênero feminino em português.
_SUFIXOS_FEMININOS = (
    "cao",
    "coes",
    "sao",
    "soes",
    "dade",
    "dades",
    "agem",
    "agens",
    "ncia",
    "ncias",
    "tude",
    "tudes",
    "eza",
    "ezas",
    "ura",
    "uras",
    "gem",
)

#: Substantivos que aparecem como predicado de "ser": "Joao e medico" -> "é".
#: Antes de `e` eles indicam coordenação ("pai e mae"), por isso servem também
#: de trava para a própria regra.
_PREDICATIVOS_NOMINAIS = frozenset(
    """
    medico medica professor professora advogado advogada engenheiro engenheira
    dentista enfermeiro enfermeira motorista estudante aluno aluna chefe dono
    dona autor autora culpado culpada responsavel brasileiro brasileira casado
    casada solteiro solteira amigo amiga irmao irma filho filha pai mae cliente
    usuario membro presidente diretor diretora gerente vendedor programador
    jornalista artista musico cantor cantora ator atriz escritor piloto
    policial bombeiro cozinheiro garcom vizinho vizinha namorado namorada
    esposa marido tio tia primo prima avo neto neta sobrinho colega socio
    """.split()
)

_ESPORTES = frozenset(
    """
    esporte esportes ioga yoga natacao futebol volei basquete exercicio
    exercicios atividade atividades musculacao meditacao boxe judo corrida
    crossfit pilates capoeira surfe skate ciclismo
    """.split()
)

#: Substantivos que, depois de "não dá", quase sempre significam "não da(quela)".
_APOS_DA_NAO_E_VERBO = frozenset(
    """
    forma maneira mesma gente casa minha sua nossa dele dela empresa escola
    cidade familia equipe noite manha tarde semana vida hora area sala turma
    """.split()
)


#: Clássicas exceções de crase: "vou a casa", "chegou a terra" não levam acento.
_SEM_CRASE = frozenset("casa terra".split())


#: Terminam em `-mos` mas não são verbo de primeira pessoa do plural.
_FALSOS_VERBOS_NOS = frozenset("termos ramos remos limos olmos timos gnomos cosmos atomos".split())


def parece_feminino(palavra: str) -> bool:
    """Heurística conservadora de gênero, usada só pelas regras de crase e `esta`.

    O corte de tamanho existe porque os sufixos femininos são curtos demais e
    pegariam masculinos: `cão` casa com `-ção`, `são` casa com `-são`.
    """
    k = normalizar(palavra)
    if k in _FEMININOS or (k.endswith("s") and k[:-1] in _FEMININOS):
        return True
    return len(k) >= 5 and k.endswith(_SUFIXOS_FEMININOS)


def parece_verbo_nos(palavra: str) -> bool:
    """Verbo conjugado em primeira pessoa do plural — o sujeito só pode ser `nós`."""
    k = normalizar(palavra)
    return len(k) >= 5 and k.endswith("mos") and k not in _FALSOS_VERBOS_NOS


# --------------------------------------------------------------------------
# Tabela de regras
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Regra:
    """Uma condição de vizinhança que empurra uma grafia para a frente.

    Conjunto vazio quer dizer "não checo isso". Todas as condições preenchidas
    precisam valer ao mesmo tempo.
    """

    chave: str
    favorece: str
    anterior_em: frozenset[str] = field(default_factory=frozenset)
    seguinte_em: frozenset[str] = field(default_factory=frozenset)
    anterior_fora: frozenset[str] = field(default_factory=frozenset)
    seguinte_fora: frozenset[str] = field(default_factory=frozenset)
    #: Trava de coordenação: se anterior E seguinte estão aqui, a palavra do
    #: meio está ligando dois termos ("bom e barato"), não predicando.
    coordenacao: frozenset[str] = field(default_factory=frozenset)
    seguinte_feminino: bool = False
    seguinte_verbo_nos: bool = False
    inicio_de_frase: bool | None = None
    peso: int = 1
    porque: str = ""

    def casa(self, anterior: str, seguinte: str, inicio_de_frase: bool) -> bool:
        if self.anterior_em and anterior not in self.anterior_em:
            return False
        if self.seguinte_em and seguinte not in self.seguinte_em:
            return False
        if anterior in self.anterior_fora:
            return False
        if seguinte in self.seguinte_fora:
            return False
        if anterior in self.coordenacao and seguinte in self.coordenacao:
            return False
        if self.seguinte_feminino and not parece_feminino(seguinte):
            return False
        if self.seguinte_verbo_nos and not parece_verbo_nos(seguinte):
            return False
        if self.inicio_de_frase is not None and self.inicio_de_frase is not inicio_de_frase:
            return False
        return True


#: Dois interrogativos seguidos coordenam entre si: "quando e onde", "como e
#: porque". O conjunto é curto de propósito — travar mais que isso custaria
#: "o que é isso" e "não é nada", que são muito mais frequentes.
_COORDENAVEIS_NEUTROS = _INTERROGATIVOS & _SUJEITOS_DE_SER

REGRAS: tuple[Regra, ...] = (
    # ---- e / é -----------------------------------------------------------
    Regra(
        chave="e",
        favorece="é",
        anterior_em=_SUJEITOS_DE_SER,
        coordenacao=_COORDENAVEIS_NEUTROS,
        porque="sujeito pronominal antes: 'isso e bom' -> 'isso é bom'; "
        "travado em 'quando e onde'",
    ),
    Regra(
        chave="e",
        favorece="é",
        seguinte_em=_ADJETIVOS,
        anterior_fora=_INTENSIDADE,
        coordenacao=_ADJETIVOS,
        porque="predicativo depois: 'o cafe e otimo'; travado em 'bom e barato'",
    ),
    Regra(
        chave="e",
        favorece="é",
        seguinte_em=_PREDICATIVOS_NOMINAIS,
        anterior_fora=_PREDICATIVOS_NOMINAIS | _INTENSIDADE | _ARTIGOS,
        porque="substantivo predicativo: 'meu irmao mais novo e medico'; "
        "travado em 'pai e mae'",
    ),
    # Não existe regra "artigo depois -> é". Ela acertava "isso e o problema" e
    # errava toda coordenação de dois substantivos ("você e o João", "o pai e a
    # mãe"), que é muito mais comum. Distinguir as duas exigiria enxergar duas
    # palavras à frente, que é justamente o que esta camada não faz.
    Regra(
        chave="e",
        favorece="é",
        seguinte_em=_INTENSIDADE,
        anterior_fora=_ADJETIVOS | _INTENSIDADE,
        porque="advérbio de intensidade depois: 'isso e muito caro'",
    ),
    # ---- a / à -----------------------------------------------------------
    Regra(
        chave="a",
        favorece="à",
        anterior_em=_REGEM_A,
        seguinte_fora=_BLOQUEIA_CRASE | _SEM_CRASE,
        seguinte_feminino=True,
        porque="verbo que rege 'a' + substantivo feminino: 'vou a escola'",
    ),
    Regra(
        chave="as",
        favorece="às",
        seguinte_em=frozenset({"vezes"}),
        porque="locução fixa 'às vezes'",
    ),
    Regra(
        chave="as",
        favorece="às",
        anterior_em=_REGEM_A,
        seguinte_fora=_BLOQUEIA_CRASE | _SEM_CRASE,
        seguinte_feminino=True,
        porque="crase no plural: 'respondeu as perguntas' -> 'às perguntas'",
    ),
    # ---- esta / está -----------------------------------------------------
    Regra(
        chave="esta",
        favorece="esta",
        seguinte_em=frozenset({"e"}),
        porque="'esta é a minha casa' — 'está é' não existe",
    ),
    Regra(
        chave="esta",
        favorece="esta",
        seguinte_feminino=True,
        seguinte_fora=frozenset({"tarde"}),
        porque="demonstrativo antes de substantivo feminino: 'esta semana'; "
        "'tarde' fica de fora porque 'ja esta tarde' é tão comum quanto 'esta tarde'",
    ),
    # ---- nos / nós -------------------------------------------------------
    Regra(
        chave="nos",
        favorece="nós",
        seguinte_verbo_nos=True,
        porque="verbo em primeira do plural depois: 'nos vamos', 'nos ficamos'",
    ),
    Regra(
        chave="nos",
        favorece="nós",
        anterior_em=frozenset({"entre"}),
        porque="'entre nós' nunca é o pronome átono",
    ),
    # ---- pais / país -----------------------------------------------------
    Regra(
        chave="pais",
        favorece="país",
        anterior_em=frozenset(
            """
            o do no ao um este esse aquele meu seu nosso teu pelo num qual cada
            outro mesmo proprio primeiro segundo terceiro melhor pior todo
            nenhum algum grande pequeno
            """.split()
        ),
        porque="determinante masculino singular: 'o pais' -> 'o país'",
    ),
    # ---- avo / avô / avó -------------------------------------------------
    Regra(
        chave="avo",
        favorece="avô",
        anterior_em=frozenset("meu o do ao um seu nosso teu pelo esse este aquele".split()),
        porque="determinante masculino: 'meu avo' -> 'meu avô'",
    ),
    # ---- sabia / sábia ---------------------------------------------------
    Regra(
        chave="sabia",
        favorece="sábia",
        anterior_em=frozenset("muito mais tao bem pouco menos uma bastante".split()),
        porque="advérbio de grau antes: 'foi muito sabia'",
    ),
    Regra(
        chave="sabia",
        favorece="sábia",
        seguinte_em=frozenset(
            "decisao escolha atitude mulher resposta palavra ideia conduta".split()
        ),
        porque="adjetivo antes do substantivo: 'sabia decisao'",
    ),
    # ---- secretaria / secretária -----------------------------------------
    Regra(
        chave="secretaria",
        favorece="secretaria",
        seguinte_em=frozenset("municipal estadual nacional escolar geral".split()),
        porque="órgão, não pessoa: 'secretaria municipal'",
    ),
    # ---- duvida / dúvida -------------------------------------------------
    Regra(
        chave="duvida",
        favorece="duvida",
        anterior_em=frozenset("ele ela voce quem ninguem alguem eu".split()),
        seguinte_em=frozenset("de da do dos das disso dele dela que muito sempre".split()),
        porque="sujeito + complemento preposicionado: 'ele duvida de mim'",
    ),
    # ---- pratica / prática -----------------------------------------------
    Regra(
        chave="pratica",
        favorece="pratica",
        anterior_em=frozenset("ele ela voce quem ninguem alguem eu".split()),
        porque="sujeito pronominal + verbo: 'ele pratica'",
    ),
    Regra(
        chave="pratica",
        favorece="pratica",
        seguinte_em=_ESPORTES,
        porque="objeto direto típico do verbo: 'pratica natacao'",
    ),
    # ---- publico / público -----------------------------------------------
    Regra(
        chave="publico",
        favorece="publico",
        anterior_em=frozenset({"eu"}),
        porque="'eu publico' é sempre verbo",
    ),
    # ---- da / dá ---------------------------------------------------------
    Regra(
        chave="da",
        favorece="dá",
        seguinte_em=frozenset(
            """
            certo errado pra tempo conta medo raiva nojo sorte azar vontade
            trabalho aula aulas nisso
            """.split()
        ),
        porque="expressões fixas com o verbo dar: 'da certo', 'da pra'",
    ),
    Regra(
        chave="da",
        favorece="dá",
        anterior_em=frozenset("nao me te lhe".split()),
        seguinte_fora=_APOS_DA_NAO_E_VERBO,
        porque="'nao da', 'me da' — travado em 'nao da forma que'",
    ),
    Regra(
        chave="da",
        favorece="dá",
        seguinte_em=frozenset("me te lhe nos lhes".split()),
        porque="pronome oblíquo depois só se liga a verbo: 'da-me' -> 'dá-me'",
    ),
)


_POR_CHAVE: dict[str, tuple[Regra, ...]] = {}
for _regra in REGRAS:
    _POR_CHAVE.setdefault(_regra.chave, ())
    _POR_CHAVE[_regra.chave] += (_regra,)


def reordenar(
    candidatos: list[Candidato],
    chave: str,
    anterior: str | None,
    seguinte: str | None,
    inicio_de_frase: bool,
) -> list[Candidato]:
    """Põe na frente a grafia que o contexto favorece, se alguma regra disparar.

    Devolve a lista intacta quando não há regra para a chave, quando nenhuma
    casa, ou quando duas regras empatam apontando para grafias diferentes.
    """
    regras = _POR_CHAVE.get(chave)
    if not regras or len(candidatos) < 2:
        return list(candidatos)

    ant = normalizar(anterior) if anterior else ""
    seg = normalizar(seguinte) if seguinte else ""
    disponiveis = {c.palavra for c in candidatos}

    pontos: dict[str, int] = defaultdict(int)
    for regra in regras:
        if regra.favorece in disponiveis and regra.casa(ant, seg, inicio_de_frase):
            pontos[regra.favorece] += regra.peso

    if not pontos:
        return list(candidatos)

    melhor = max(pontos.values())
    vencedores = [palavra for palavra, valor in pontos.items() if valor == melhor]
    if len(vencedores) != 1:
        return list(candidatos)

    escolhida = vencedores[0]
    return [c for c in candidatos if c.palavra == escolhida] + [
        c for c in candidatos if c.palavra != escolhida
    ]
