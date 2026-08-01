# Como contribuir

Obrigado por querer ajudar. Este projeto tem uma contribuição que vale mais que
todas as outras — e ela **não exige saber programar**. Está na seção "O que mais
ajuda", logo abaixo do setup.

## Montando o ambiente (3 minutos)

```bash
git clone https://github.com/eric/acentua.git
cd acentua
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Rodando o app durante o desenvolvimento:

```bash
python -m corretor
```

## Rodando os testes

```bash
pytest
```

Os testes rodam sem instalar o pacote (o `pyproject.toml` já põe `src/` no
`pythonpath`).

Marcadores disponíveis, para pular o que precisa de máquina de verdade:

| Marcador | O que ele marca | Como pular |
| -------- | --------------- | ---------- |
| `gui` | Precisa de janela/tela (tkinter de verdade) | `pytest -m "not gui"` |
| `sistema` | Mexe na área de transferência, no teclado ou no registro | `pytest -m "not sistema"` |
| `lento` | Carrega o dicionário inteiro | `pytest -m "not lento"` |

O CI do GitHub roda `pytest -m "not gui and not sistema"`, porque a máquina de
build não tem tela nem área de transferência. **Se o seu teste precisa de uma
janela ou do clipboard, marque-o** — senão ele quebra o CI de todo mundo:

```python
import pytest

@pytest.mark.gui
def test_popup_fecha_com_esc(): ...
```

## O que mais ajuda

### 1. Palavras que o Acentua erra → `src/corretor/dados/excecoes.json`

Achou uma palavra que sai errada? Este é o arquivo. Uma linha aqui resolve o
caso para sempre.

O formato é `"palavra sem acento": ["grafia certa", "segunda opção", ...]`. A
lista **substitui o grupo inteiro** daquela chave: a primeira é a que o Acentua
usa direto, as outras aparecem no popup do `Ctrl+Alt+S`, nessa ordem.

```json
{
  "acai": ["açaí"],
  "voce": ["você"],
  "so": ["só", "so"]
}
```

Substituir em vez de somar é de propósito. Quando a frequência do corpus erra,
quase sempre é porque ele conta uma grafia que ninguém escreve (`porem` como
verbo, `ate` como forma de atar). Deixar essa grafia no grupo faria o popup
oferecer lixo.

Regras rápidas:

- A chave vai **sem acento, em minúsculas** — é assim que o Acentua procura.
- Chaves começando com `_` são ignoradas: use para comentar.
- Se a palavra tem mais de uma grafia válida, liste todas, da mais comum para a
  menos comum. Se só uma serve, a lista tem um item só.
- Uma palavra por linha, para o diff ficar legível.
- Abra um PR com o título `excecoes: <a palavra>`. É um PR de uma linha e é a
  contribuição mais valiosa que existe aqui.

### 2. Casos que dependem de contexto → `src/corretor/nucleo/contexto.py`

Quando a mesma grafia está certa ou errada dependendo da frase (`e`/`é`,
`esta`/`está`, `a`/`à`), o `excecoes.json` não resolve: é preciso uma regra que
olhe a palavra anterior e a seguinte. Elas moram na tabela `REGRAS`.

Duas leis, e elas não são negociáveis:

1. **Uma regra só existe para contrariar a frequência.** Se o candidato mais
   comum já acerta naquele contexto, não escreva regra nenhuma. Menos regra,
   menos jeito de errar.
2. **Precisão acima de cobertura.** Uma regra errada é pior que regra nenhuma,
   porque o usuário deixa de conseguir prever o que o programa faz. Na dúvida,
   deixe a frequência decidir.

Toda regra nova precisa de teste: um caso que ela conserta **e** um caso vizinho
que ela não pode estragar.

## Abrindo um PR

1. Crie um branch a partir da `main`.
2. Rode `pytest -m "not gui and not sistema"` antes de enviar.
3. No texto do PR, escreva a frase de antes e a de depois. Exemplo:
   `"vou a praia"` → `"vou à praia"`.
4. Uma mudança por PR. PRs de uma linha são bem-vindos e revisados rápido.

## Estilo

- Python 3.11+, com type hints.
- Nomes e comentários em português.
- Mensagens de erro dizem **o que fazer**, não só o que quebrou.
- Sem dependências novas em runtime. As três atuais (`pynput`, `pystray`,
  `Pillow`) já são o teto: o app precisa continuar instalável em 1 clique.
