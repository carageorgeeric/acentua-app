# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado

- **Revisão da frase antes de colar.** Selecione um texto inteiro, aperte
  `Ctrl+Alt+C` e, nas palavras em que a acentuação é ambígua (`e`/`é`,
  `a`/`à`, `esta`/`está`), o popup pergunta uma por vez mostrando a frase com
  a opção destacada no lugar — a frase muda embaixo do olho conforme você
  navega com as setas. Responda com `1`/`2`/`3`, `Enter` ou o mouse; `Esc`
  encerra a fila e cola o resto com a grafia automática, sem perder nada. O
  texto sai colado uma vez só, então `Ctrl+Z` desfaz tudo de uma vez.
  Desligável em Configurações → "Revisar a frase antes de colar".
- Limite de 6 perguntas por correção: um parágrafo cheio de `e` e `a` viraria
  uma fila de popups mais cansativa do que corrigir duas palavras na mão.
- O aprendizado agora anota só as grafias que você **contraria**, nunca as que
  apenas confirma com `Enter` — confirmar `é` três vezes em "isso é bom"
  gravava `é` como preferência de `e` e passava a estragar "pão e queijo".

### Corrigido

- Disparar o atalho com o popup aberto injetava o `Ctrl+C` da leitura dentro
  do próprio popup: nada era lido, a fila morria no meio e nada era colado.
- A janela de configurações aparecia vazia no canto da tela, era remontada
  para caber e só então pulava para o lugar certo. Agora ela é montada oculta
  e aparece uma vez só, já pronta e no lugar.
- A barra de tarefas mostrava o ícone do Python no lugar do ícone do Acentua.

## [1.1.0] - 2026-07-30

### Adicionado

- **Corrigir a palavra em que o caret está, com `Ctrl+Alt+W`** — sem selecionar
  nada e sem tirar a mão do teclado. Acerta o alvo com o caret no fim, no meio
  ou colado antes da palavra. Se a palavra já estiver certa, a seleção interna
  é desfeita, de modo que a próxima tecla digitada não apaga nada.
- **Janela de configurações redesenhada**: gravador de atalho (clique no campo
  e aperte a combinação), interruptores no lugar de caixas de seleção e tema
  claro/escuro/sistema.

### Corrigido

- As setas não carregavam o flag de tecla estendida, então o
  `Ctrl+Shift+Esquerda` podia virar o `4` do teclado numérico com o NumLock
  ligado.
- `root.after` chamado de uma thread durante o encerramento derrubava a
  correção em voo com um traceback.

## [1.0.0] - 2026-07-30

Primeira versão pública.

### Adicionado

- Correção de acentuação do texto selecionado em qualquer programa, com
  `Ctrl+Alt+C`. O texto é lido da seleção e devolvido no lugar.
- Popup de sugestões com `Ctrl+Alt+S`: escolha com `1`/`2`/`3`, com as setas ou
  com o mouse; `Esc` fecha sem mudar nada.
- Dicionário offline do português brasileiro com 138.462 palavras em 109.550
  grupos de ambiguidade, ordenados por frequência real de uso.
- Desempate por contexto para os pares que a frequência erra (`e`/`é`,
  `esta`/`está`, `a`/`à`), com tabela declarativa de regras conservadoras.
- Aprendizado das escolhas do usuário: o que você seleciona no popup vira
  preferência nas próximas correções.
- Ícone na bandeja do sistema, com pausar/despausar e janela de configurações.
- Atalhos globais configuráveis.
- Instalador de 1 clique (`INSTALAR.bat`) e equivalente em Python
  (`scripts/instalar.py`), ambos idempotentes.
- Criação de atalho na área de trabalho sem depender de pywin32, com opção
  `--iniciar-com-windows`.

### Notas

- Só funciona no Windows. O motor de correção é portável, mas o atalho global, a
  área de transferência e o envio de teclas usam APIs do Windows.
- Configuração e aprendizado ficam em `%APPDATA%\Acentua`, então atualizar ou
  reinstalar o programa não apaga nada.

[Não lançado]: https://github.com/eric/acentua/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/eric/acentua/releases/tag/v1.0.0
