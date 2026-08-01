"""Gera os ícones do Acentua em ``src/corretor/dados/``.

Uso::

    python scripts/gerar_icone.py            # gera tudo
    python scripts/gerar_icone.py --conferir # só relata o que já existe

Direção de arte: quadrado de cantos arredondados, gradiente diagonal
índigo -> violeta, e um "á" branco bem grande. O acento agudo é o conceito do
produto inteiro, então ele não é deixado por conta da fonte: é desenhado à
mão, como uma barra grossa inclinada, com tamanho proporcional ao ícone.

Por que desenhar o acento em vez de escrever "á" e pronto: a 16px o acento
de qualquer fonte vira um pixel cinza e o ícone lê como um "a" qualquer.
Nos tamanhos pequenos também usamos um layout compacto — glifo maior, cantos
menos arredondados, acento mais grosso e mais separado — porque a mesma arte
reduzida vira borrão.
"""

from __future__ import annotations

import argparse
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "src" / "corretor" / "dados"

TAMANHOS_ICO = (16, 24, 32, 48, 64, 128, 256)
TAMANHO_PNG = 256

COR_INICIAL = (79, 70, 229)  # #4F46E5 índigo
COR_FINAL = (124, 58, 237)  # #7C3AED violeta
COR_GLIFO = (255, 255, 255, 255)

#: Abaixo disso o desenho normal some. Usa-se o layout compacto.
LIMITE_COMPACTO = 32

#: Todas as medidas são frações do lado do ícone. O layout compacto existe
#: porque a arte normal reduzida a 16px vira borrão: lá o glifo precisa ser
#: maior, o canto menos arredondado e o acento mais grosso e mais afastado,
#: para sobrarem pixels suficientes para o olho reconhecer o acento.
LAYOUT = {
    "normal": {
        "raio": 0.225,
        "glifo": 0.74,
        "descida": 0.08,
        "acento_largura": 0.26,
        "acento_espessura": 0.105,
        "acento_folga": 0.035,
    },
    "compacto": {
        "raio": 0.18,
        "glifo": 0.82,
        "descida": 0.115,
        "acento_largura": 0.32,
        "acento_espessura": 0.155,
        "acento_folga": 0.045,
    },
}

#: Supersampling: desenhamos grande e reduzimos com LANCZOS. Rasterizar
#: direto em 16px dá serrilhado em tudo (cantos, curva do "a", acento).
FATOR = 8

FONTES_CANDIDATAS = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "DejaVuSans-Bold.ttf",
)


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    for caminho in FONTES_CANDIDATAS:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except OSError:
            continue
    raise SystemExit(
        "Nenhuma fonte bold encontrada. Instale uma das: "
        + ", ".join(FONTES_CANDIDATAS)
    )


def _gradiente(lado: int) -> Image.Image:
    """Gradiente diagonal (canto superior esquerdo -> inferior direito).

    Calculado numa grade pequena e ampliado: para uma rampa de duas cores o
    resultado é idêntico ao cálculo por pixel e é ~1000x mais rápido.
    """
    grade = 64
    base = Image.new("RGB", (grade, grade))
    pixels = base.load()
    maximo = (grade - 1) * 2 or 1
    for y in range(grade):
        for x in range(grade):
            t = (x + y) / maximo
            pixels[x, y] = tuple(
                round(inicio + (fim - inicio) * t)
                for inicio, fim in zip(COR_INICIAL, COR_FINAL, strict=True)
            )
    return base.resize((lado, lado), Image.Resampling.BICUBIC)


def _brilho_superior(lado: int) -> Image.Image:
    """Véu branco muito leve na metade de cima, para o quadrado não ser chapado."""
    mascara = Image.new("L", (1, 64))
    pixels = mascara.load()
    for y in range(64):
        pixels[0, y] = max(0, round(38 * (1 - y / 26))) if y < 26 else 0
    return mascara.resize((lado, lado), Image.Resampling.BICUBIC)


def _acento(lado: int, medidas: dict[str, float]) -> Image.Image:
    """O acento agudo, desenhado à mão como barra inclinada de cantos redondos."""
    largura = round(lado * medidas["acento_largura"])
    espessura = round(lado * medidas["acento_espessura"])
    barra = Image.new("RGBA", (largura, espessura), (0, 0, 0, 0))
    ImageDraw.Draw(barra).rounded_rectangle(
        (0, 0, largura - 1, espessura - 1),
        radius=espessura // 2,
        fill=COR_GLIFO,
    )
    return barra.rotate(28, resample=Image.Resampling.BICUBIC, expand=True)


def desenhar(lado: int) -> Image.Image:
    """Devolve o ícone em ``lado`` x ``lado`` px, RGBA, já antisserrilhado."""
    medidas = LAYOUT["compacto" if lado <= LIMITE_COMPACTO else "normal"]
    grande = lado * FATOR

    arte = _gradiente(grande).convert("RGBA")
    arte = Image.composite(
        Image.new("RGBA", arte.size, (255, 255, 255, 255)),
        arte,
        _brilho_superior(grande),
    )

    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, grande - 1, grande - 1),
        radius=round(grande * medidas["raio"]),
        fill=255,
    )
    icone = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    icone.paste(arte, (0, 0), mascara)

    # O "a" minúsculo sem acento; o acento entra depois, desenhado.
    fonte = _fonte(round(grande * medidas["glifo"]))
    desenho = ImageDraw.Draw(icone)
    caixa = desenho.textbbox((0, 0), "a", font=fonte)
    largura_a = caixa[2] - caixa[0]
    altura_a = caixa[3] - caixa[1]
    # Desce um pouco: o acento ocupa o topo.
    x = (grande - largura_a) // 2 - caixa[0]
    y = (grande - altura_a) // 2 - caixa[1] + round(grande * medidas["descida"])
    desenho.text((x, y), "a", font=fonte, fill=COR_GLIFO)

    acento = _acento(grande, medidas)
    ax = (grande - acento.width) // 2 + round(grande * 0.07)
    ay = max(
        round(grande * 0.05),
        y + caixa[1] - acento.height - round(grande * medidas["acento_folga"]),
    )
    icone.alpha_composite(acento, (ax, ay))

    return icone.resize((lado, lado), Image.Resampling.LANCZOS)


def dessaturar(imagem: Image.Image) -> Image.Image:
    """Variante do estado pausado: quase cinza e um pouco mais escura."""
    rgb = imagem.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(0.12)
    rgb = ImageEnhance.Brightness(rgb).enhance(0.78)
    saida = rgb.convert("RGBA")
    saida.putalpha(imagem.getchannel("A"))
    return saida


def _escrever_ico(caminho: Path, imagens: list[Image.Image]) -> None:
    """Escreve um .ico multi-resolução com PNG embutido em cada entrada.

    Feito à mão de propósito: o ``save(format="ICO")`` do Pillow reamostra
    UMA imagem para todos os tamanhos, o que jogaria fora o desenho compacto
    que fizemos justamente para 16/24/32 px.
    """
    blocos = []
    for imagem in imagens:
        buffer = BytesIO()
        imagem.save(buffer, format="PNG", optimize=True)
        blocos.append(buffer.getvalue())

    cabecalho = struct.pack("<HHH", 0, 1, len(blocos))
    deslocamento = len(cabecalho) + 16 * len(blocos)
    entradas = bytearray()
    for imagem, bloco in zip(imagens, blocos, strict=True):
        entradas += struct.pack(
            "<BBBBHHII",
            imagem.width if imagem.width < 256 else 0,
            imagem.height if imagem.height < 256 else 0,
            0,  # paleta
            0,  # reservado
            1,  # planos
            32,  # bits por pixel
            len(bloco),
            deslocamento,
        )
        deslocamento += len(bloco)

    caminho.write_bytes(cabecalho + bytes(entradas) + b"".join(blocos))


def gerar(destino: Path = DESTINO) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    normais = [desenhar(lado) for lado in TAMANHOS_ICO]
    pausados = [dessaturar(imagem) for imagem in normais]

    escritos = []
    for nome, imagens in (("icone", normais), ("icone_pausado", pausados)):
        ico = destino / f"{nome}.ico"
        _escrever_ico(ico, imagens)
        escritos.append(ico)

        png = destino / f"{nome}.png"
        maior = imagens[-1]
        if maior.width != TAMANHO_PNG:
            maior = maior.resize((TAMANHO_PNG, TAMANHO_PNG), Image.Resampling.LANCZOS)
        maior.save(png, format="PNG", optimize=True)
        escritos.append(png)
    return escritos


def conferir(destino: Path = DESTINO) -> int:
    """Reabre os .ico e confirma que todas as resoluções estão lá."""
    problemas = 0
    for nome in ("icone", "icone_pausado"):
        caminho = destino / f"{nome}.ico"
        if not caminho.exists():
            print(f"FALTA  {caminho}")
            problemas += 1
            continue
        with Image.open(caminho) as arquivo:
            tamanhos = sorted({t[0] for t in arquivo.ico.sizes()})
        esperados = sorted(TAMANHOS_ICO)
        marca = "OK   " if tamanhos == esperados else "ERRO "
        problemas += tamanhos != esperados
        print(f"{marca}{caminho.name}: {tamanhos}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description="Gera os ícones do Acentua.")
    analisador.add_argument(
        "--conferir",
        action="store_true",
        help="não gera nada, só valida os arquivos existentes",
    )
    argumentos = analisador.parse_args(argv)

    if argumentos.conferir:
        return conferir()

    for caminho in gerar():
        print(f"gerado {caminho.relative_to(RAIZ)}")
    return conferir()


if __name__ == "__main__":
    sys.exit(main())
