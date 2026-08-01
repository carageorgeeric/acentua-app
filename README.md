<!--
  ANTES DE PUBLICAR NO GITHUB: troque `eric/acentua` por `SEU-USUARIO/SEU-REPO`
  neste arquivo (busca e substitui). São os links dos badges e das seções de
  instalação. Nada mais precisa mudar.
-->

<h1 align="center">Acentua</h1>

<p align="center">
  <strong>Digite sem acento. Configure um comando para acentuar suas frases e pronto!</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licença MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img alt="Windows" src="https://img.shields.io/badge/plataforma-Windows-0078D6.svg">
  <a href="https://github.com/eric/acentua/actions/workflows/testes.yml"><img alt="Testes" src="https://github.com/eric/acentua/actions/workflows/testes.yml/badge.svg"></a>
  <img alt="100% offline" src="https://img.shields.io/badge/dados-100%25%20offline-success.svg">
</p>

---

## O problema

Teclados compactos (60%, 65%, 68%) e layouts US são ótimos para quase tudo — menos
para escrever em português. O `ç` some, o `~` vira ginástica de dedo e as teclas
mortas de `´` e `^` simplesmente não existem.

O resultado é sempre o mesmo: você digita rápido e sem acento nenhum, e depois
volta para consertar palavra por palavra.

O Acentua acaba com a segunda parte.

## Como funciona

1. Digite normalmente, **sem acento nenhum**, em qualquer programa.
2. **Selecione** o texto — uma palavra, uma frase ou o parágrafo inteiro.
3. Aperte **`Ctrl+Alt+C`** (ou a combinação de teclas que você escolher). O texto é substituído já acentuado.

Quando alguma palavra da frase é genuinamente ambígua — o `e` de "isso e bom"
pode ser `e` ou `é` —, o Acentua pergunta antes de colar, uma palavra por vez:

```
┌──────────────────────────────────────┐
│  o café da manhã é ótimo e a …  1/2  │  ← a frase, com a opção no lugar
├──────────────────────────────────────┤
│  1   é                          38%  │  ← Enter aceita esta
│  2   e                          62%  │
└──────────────────────────────────────┘
```

As setas trocam a palavra destacada **dentro da frase**, então dá para ler o
resultado antes de decidir. `Esc` encerra as perguntas e cola o resto com a
grafia automática — desistir nunca perde a correção. O texto é colado uma vez
só no fim, então um `Ctrl+Z` desfaz tudo.

Ou, sem parar de digitar: escreva `coracao`, aperte **`Ctrl+Alt+D`** e só a
palavra em que você está vira `coração`. Não precisa selecionar, não precisa
mirar — funciona com o caret no fim, no meio ou colado antes da palavra.

O app fica na bandeja do sistema, ao lado do relógio. Sem janela, sem barulho.

## Instalação

### Caminho de 1 clique

| Passo | O que fazer |
| :---: | ----------- |
| 1 | Baixe o projeto: **[Code → Download ZIP](https://github.com/eric/acentua/archive/refs/heads/main.zip)** |
| 2 | Extraia o `.zip` em qualquer pasta (ex.: `C:\Acentua`) |
| 3 | Clique duas vezes em **`INSTALAR.bat`** e espere terminar |
| 4 | Abra o atalho **Acentua** que apareceu na área de trabalho |

O instalador cuida de tudo: acha o Python, monta um ambiente isolado, instala as
dependências e cria o atalho. Se algo faltar, ele diz exatamente o que fazer.

> **Precisa do Python 3.11 ou mais novo.** Se você não tiver, baixe em
> [python.org/downloads](https://www.python.org/downloads/) e **marque a caixinha
> "Add python.exe to PATH"** na primeira tela do instalador.

Para o Acentua abrir junto com o Windows:

```
.venv\Scripts\python.exe scripts\criar_atalho.py --iniciar-com-windows
```

### Caminho do desenvolvedor

```bash
git clone https://github.com/eric/acentua.git
cd acentua
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m corretor
```

Ou, se preferir o instalador em Python em vez do `.bat`:

```bash
py -3 scripts/instalar.py
```

## Atalhos

| Atalho | O que faz |
| ------ | --------- |
| `Ctrl+Alt+C` | Corrige a acentuação do texto selecionado |
| `Ctrl+Alt+D` | Corrige a palavra em que o caret está — sem selecionar nada |
| `Ctrl+Alt+S` | Abre o popup de sugestões em vez de trocar direto |
| `1` `2` `3` | Escolhe a opção correspondente no popup |
| `↑` `↓` `Enter` | Navega e confirma no popup |
| `Esc` | Fecha o popup; numa revisão de frase, cola o resto sem perguntar |
| `Ctrl+Z` | Desfaz a troca, como em qualquer programa |

Os dois atalhos globais podem ser trocados na janela de configurações
(clique com o botão direito no ícone da bandeja).

## Como ele escolhe a acentuação

O Acentua nunca "adivinha". Ele decide em três camadas, nesta ordem:

**1. Dicionário com frequência real.**
São **138 mil palavras** do português brasileiro agrupadas em **109 mil grupos de
ambiguidade** — cada grupo junta as grafias que viram a mesma coisa quando você
tira os acentos. Para `saude`, o grupo é `{saúde, saudé}`; como `saúde` aparece
milhares de vezes mais no corpus, é ela que ganha. Isso sozinho resolve a grande
maioria das palavras.

**2. Regras de contexto para os casos que a frequência erra.**
Alguns pares são frequentes dos dois lados e a estatística não ajuda: `e`/`é`,
`esta`/`está`, `a`/`à`. Aí entram regras declarativas que olham a palavra
anterior e a seguinte:

| Você digitou | Vira | Por quê |
| ------------ | ---- | ------- |
| `isso e bom` | `isso **é** bom` | pronome + adjetivo pede o verbo |
| `pao e queijo` | `pão **e** queijo` | dois substantivos pedem a conjunção |
| `esta casa` | `**esta** casa` | antes de substantivo é o demonstrativo |
| `ele esta bem` | `ele **está** bem` | depois de pronome é o verbo |
| `vou a praia` | `vou **à** praia` | verbo que rege `a` + palavra feminina |

A tabela é conservadora de propósito: **uma regra só existe para contrariar a
frequência**. Quando duas regras discordam, nenhuma vale e a frequência decide.
Regra errada é pior que regra nenhuma, porque quebra a previsibilidade.

**3. Ele aprende com você.**
Toda vez que você escolhe uma opção no popup (`Ctrl+Alt+S`), a escolha é anotada
e passa a ter preferência da próxima vez que aquela mesma palavra aparecer. Seus
nomes próprios, jargão de trabalho e manias de escrita entram no sistema sozinhos.

Na revisão de frase o critério é mais estrito: só entra no aprendizado a grafia
que você **contraria**, nunca a que você apenas confirma com `Enter`. Preferência
tem prioridade sobre regra de contexto, e confirmar o `é` de "isso é bom" três
vezes gravaria `é` como a grafia preferida de `e` — o que estragaria
"pão e queijo" para sempre.

O aprendizado fica em `%APPDATA%\Acentua`, fora da pasta do programa — reinstalar
ou atualizar não apaga nada.

## Perguntas frequentes

<details>
<summary><strong>Ele manda meu texto para algum servidor?</strong></summary>

Não. O Acentua é 100% offline: o dicionário fica no seu disco e a correção acontece
no seu computador. Não há telemetria, conta de usuário, IA nem conexão de rede.
</details>

<details>
<summary><strong>Funciona em qual programa?</strong></summary>

Em qualquer um que aceite copiar e colar: Word, Chrome, WhatsApp Web, Discord,
Slack, Bloco de Notas, VS Code, campos de formulário no navegador. O Acentua usa a
área de transferência, então se `Ctrl+C` e `Ctrl+V` funcionam ali, ele funciona.
</details>

<details>
<summary><strong>E se ele errar?</strong></summary>

`Ctrl+Z` desfaz, como em qualquer programa — o texto volta exatamente como estava.

Se uma palavra específica vive errando, use `Ctrl+Alt+S` em vez de `Ctrl+Alt+C`:
o popup mostra as opções e a sua escolha vira preferência dali em diante.
</details>

<details>
<summary><strong>Consome muita memória?</strong></summary>

O dicionário comprimido tem menos de 1 MB em disco. Em execução, o app fica na
casa de algumas dezenas de MB de RAM e usa 0% de CPU parado — ele só acorda quando
você aperta o atalho.
</details>

<details>
<summary><strong>Funciona no Mac ou no Linux?</strong></summary>

Hoje não. O motor de correção é Python puro e portável, mas a captura do atalho
global, o acesso à área de transferência e o envio de teclas usam APIs do Windows.
Portar é possível e contribuições são bem-vindas.
</details>

<details>
<summary><strong>Posso desligar sem fechar?</strong></summary>

Sim. Clique com o botão direito no ícone da bandeja e escolha pausar. O ícone
muda de aparência e os atalhos param de responder até você despausar.
</details>

## Como contribuir

O jeito mais útil de ajudar é ensinar palavras novas ao Acentua — não precisa
saber programar para isso. Veja **[CONTRIBUINDO.md](CONTRIBUINDO.md)**.

## Licença

[MIT](LICENSE) — use, modifique e distribua à vontade.
