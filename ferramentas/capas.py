#!/usr/bin/env python3
"""
capas.py: o robô de capas do Acervo Literário.

Roda sozinho no GitHub (ver .github/workflows/publicar.yml) a cada vez que o
site é publicado. Para cada anúncio do acervo.js que tem capa (campo `img`) e
para cada imagem sugerida (campo `sug`):

  1. baixa a imagem direto do servidor de origem;
  2. tira o fundo quando ele é liso (foto de caixa ou de livro em fundo branco),
     deixando o fundo transparente, e tira junto a SOMBRA que a foto trazia
     (o site desenha uma sombra nova, igual para todas); capa de livro
     "justa" fica como está, e capa com moldura branca em volta é cortada
     rente, sem virar recorte;
  3. guarda uma cópia leve dentro do próprio site, em capas/<slug>.webp;
  4. escreve capas/capas.js, que o site lê para usar a cópia guardada;
  5. escreve capas/relatorio.json com o que deu certo e o que precisa de
     atenção, e as folhas de conferência em capas/conferencia/.

Imagem que já foi tratada e cuja URL não mudou não é baixada de novo.

Sombra e recortes difíceis: quando há recorte a fazer, o robô tenta usar
uma IA de recorte (rembg, modelo isnet-general-use), instalada por ele mesmo
na primeira vez que precisa. Ela serve para separar a sombra do objeto e
devolver partes claras da caixa que o fundo branco engoliu (lombada branca).
Se a IA discordar demais do recorte por cor, ou não puder ser instalada, o
robô segue só com o recorte por cor e uma limpeza de sombra por cor e
textura. Nada disso muda o site: só a qualidade da cópia em capas/.

Papel de cada imagem (versão 4):
  • livro avulso: a capa sai RETA e ocupa o quadro inteiro, como uma capa
    escaneada. Foto de livro em 3D, em pé, com lombada, páginas, sombra ou
    fundo branco vira só a frente da capa, cortada rente. Se não der para
    achar a frente com segurança, fica o recorte sobre o fundo do site;
  • box (campo `box`): a caixa sai recortada, sem fundo, sem a sombra e sem
    o "chão" claro que a foto trazia embaixo dela;
  • coleção: as imagens dos volumes são tratadas como avulsos.

Qualidade: antes de tratar, o robô tenta a versão maior da MESMA imagem
(Amazon sem o tamanho no nome, Mercado Livre 2X, WordPress sem o -300x450,
Estante Virtual sem o redimensionamento). A versão maior só é usada se for
mesmo maior e tiver o mesmo desenho e o mesmo formato da original. Imagem
pequena é ampliada com cuidado e ganha um leve reforço de nitidez.

Foto própria: um `img` sem http (ex.: "fotos/contos-de-grimm.jpg") é uma foto
tirada pelo vendedor e guardada no site, na pasta `fotos/`. O robô lê direto do
repositório e trata como qualquer outra.

Formato: WebP com transparência. É a mesma transparência do PNG com uma
fração do peso, e todos os navegadores atuais abrem. Para gerar PNG, mude
FORMATO abaixo para "png" (os arquivos ficam umas cinco vezes maiores).
"""
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage

VERSAO = 4                  # mude para reprocessar tudo depois de alterar o tratamento
                            # 3: sombra original tirada, moldura branca cortada, IA de recorte
                            # 4: avulso vira capa reta, box sem chão, versão maior da imagem
FORMATO = "webp"            # "webp" ou "png"
LADO_MAX = 900              # maior lado da imagem guardada, em pixels
LADO_MIN = 720              # imagem menor que isso é ampliada (com reforço de nitidez)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(RAIZ, "capas")
PASTA_SUG = os.path.join(PASTA, "sug")
PASTA_CONF = os.path.join(PASTA, "conferencia")
AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# tipos gravados no manifesto
CAPA, RECORTE, FOTO, FALHOU = "c", "r", "f", "x"
NOME_TIPO = {CAPA: "capa", RECORTE: "fundo removido", FOTO: "foto com cenário", FALHOU: "não baixou"}


# ----------------------------------------------------------------- site completo?
# Arquivos sem os quais o site publicado quebra. O robô roda antes da
# publicação: se faltar algum, ele para aqui e nada vai para o ar, e o site
# que já está publicado continua como estava.
ESSENCIAIS = ("acervo.js", "base.js", "loja.js", "index.html", "bookstore.html",
              "qrcodes.html", "admin.html", "capas.html")


def conferir_site():
    faltam = [f for f in ESSENCIAIS if not os.path.isfile(os.path.join(RAIZ, f))]
    if faltam:
        print("::error::Faltam arquivos do site no repositório: " + ", ".join(faltam)
              + ". Envie o pacote completo do site. Nada foi publicado; o site no ar continua como estava.")
        sys.exit(1)


# ----------------------------------------------------------------- catálogo
def ler_acervo(caminho):
    if not os.path.isfile(caminho):
        print(f"::error::Não achei {os.path.basename(caminho)} na raiz do repositório. "
              "Envie o pacote completo do site.")
        sys.exit(1)
    src = open(caminho, encoding="utf-8").read()
    i = src.index("window.ACERVO_RAW")
    ini = src.index("[", i)
    d, dentro, esc = 0, False, False
    for k in range(ini, len(src)):
        c = src[k]
        if dentro:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': dentro = False
        elif c == '"': dentro = True
        elif c == "[": d += 1
        elif c == "]":
            d -= 1
            if d == 0:
                return json.loads(src[ini:k + 1])
    raise ValueError("não achei o fim de ACERVO_RAW")


def marca(url):
    """FNV-1a de 32 bits sobre as unidades UTF-16 da URL: o site calcula a
    mesma coisa em JavaScript para saber se a cópia guardada é desta URL."""
    h = 2166136261
    dados = url.encode("utf-16-le")
    for k in range(0, len(dados), 2):
        h ^= dados[k] | (dados[k + 1] << 8)
        h = (h * 16777619) & 0xFFFFFFFF
    return format(h, "08x")


# ----------------------------------------------------------------- download
def baixar(url, tentativas=2):
    """Baixa a imagem. Endereço sem http (ex.: fotos/meu-livro.jpg) é uma
    foto do próprio vendedor, guardada no site: lê direto do repositório."""
    if not url.lower().startswith(("http://", "https://")):
        caminho = os.path.normpath(os.path.join(RAIZ, url.split("?")[0]))
        if not caminho.startswith(RAIZ + os.sep):
            raise ValueError("endereço fora do site: " + url)
        with open(caminho, "rb") as f:
            return f.read()
    ultimo = None
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": AGENTE,
                "Accept": "image/avif,image/webp,image/png,image/*;q=0.8,*/*;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — qualquer falha vira "não baixou"
            ultimo = e
            time.sleep(1.5 * (t + 1))
    raise ultimo


# ----------------------------------------------------------------- versão maior
def variantes(url):
    """Endereços da MESMA imagem em tamanho maior, do mais provável ao menos.
    Nenhum deles é usado sem conferir (ver baixar_melhor)."""
    import re
    v = []
    m = re.match(r"(https://m\.media-amazon\.com/images/I/[^.]+)\.[^/]*_\.(jpg|png|jpeg)$", url)
    if m:                                   # Amazon: tira o _SY522_ e vem a original
        v.append(f"{m.group(1)}.{m.group(2)}")
    m = re.match(r"(https://m\.media-amazon\.com/images/P/[0-9X]{10})\.01\._SCLZZZZZZZ_\.jpg$", url)
    if m:
        v += [m.group(1) + ".01._SL1200_.jpg", m.group(1) + ".01.LZZZZZZZ.jpg"]
    m = re.match(r"(https://http2\.mlstatic\.com/)D_(?:Q|NQ)_NP_(?:2X_)?(.+?)-[A-Z]{1,2}\.(webp|jpg)$", url)
    if m:                                   # Mercado Livre: a versão 2X
        alvo = f"{m.group(1)}D_NQ_NP_2X_{m.group(2)}-F.{m.group(3)}"
        if alvo != url:
            v.append(alvo)
    m = re.match(r"(.+/wp-content/uploads/.+?)-\d{2,4}x\d{2,4}(\.(?:jpg|jpeg|png|webp))$", url)
    if m:                                   # WordPress: sem o -300x450
        v.append(m.group(1) + m.group(2))
    m = re.match(r"https://static\.skeelo\.com/remote/\d+/\d+/\d+/(https?://.+)$", url)
    if m:                                   # Skoob atrás do redimensionador
        v.append(m.group(1))
    if "static.estantevirtual.com.br" in url and "?" in url:
        v.append(url.split("?")[0])
    m = re.match(r"(https://covers\.openlibrary\.org/b/.+)-M(\.jpg.*)$", url)
    if m:
        v.append(m.group(1) + "-L" + m.group(2))
    return [x for k, x in enumerate(v) if x != url and x not in v[:k]]


def _assinatura(dados):
    """Miniatura cinza 24x36 e proporção, para comparar duas imagens."""
    im = Image.open(io.BytesIO(dados))
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = ImageOps.exif_transpose(im)
    W, H = im.size
    fundo = Image.new("RGBA", im.size, (255, 255, 255, 255))
    fundo.alpha_composite(im.convert("RGBA"))
    p = np.asarray(fundo.convert("L").resize((24, 36), Image.BILINEAR), dtype=np.float32)
    return W, H, p


def parecidas(a, b):
    """True se as duas são a mesma imagem (proporção e desenho iguais)."""
    try:
        wa, ha, pa = _assinatura(a)
        wb, hb, pb = _assinatura(b)
    except Exception:  # noqa: BLE001
        return False
    if abs((wa / ha) / (wb / hb) - 1) > 0.04:
        return False
    return float(np.abs(pa - pb).mean()) <= 16 and float(np.corrcoef(pa.ravel(), pb.ravel())[0, 1]) >= 0.9


def baixar_melhor(url, baixador):
    """Baixa a imagem e, se houver, uma versão maior DELA MESMA.
    Devolve (bytes, url_usada)."""
    dados = baixador(url)
    try:
        w0, h0, _ = _assinatura(dados)
    except Exception:  # noqa: BLE001
        return dados, url
    for alt in variantes(url):
        try:
            d2 = baixador(alt)
            w2, h2, _ = _assinatura(d2)
        except Exception:  # noqa: BLE001
            continue
        if max(w2, h2) >= 1.15 * max(w0, h0) and parecidas(dados, d2):
            return d2, alt
    return dados, url


# ----------------------------------------------------------------- tratamento
def _anel(rgb, k=3):
    return np.concatenate([rgb[:k].reshape(-1, 3), rgb[-k:].reshape(-1, 3),
                           rgb[:, :k].reshape(-1, 3), rgb[:, -k:].reshape(-1, 3)])


def _caixa(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


# ---------------------------------------------------------------- IA de recorte
_IA = {"sessao": None, "tentou": False}
_IA_TRAVA = threading.Lock()
_IA_VEZ = threading.Semaphore(2)        # duas de cada vez: a IA já usa vários núcleos


def _ia_sessao():
    """Carrega a IA de recorte uma vez só. Se não der (sem rede, sem pip),
    devolve None e o robô segue só com o recorte por cor."""
    with _IA_TRAVA:
        if _IA["tentou"]:
            return _IA["sessao"]
        _IA["tentou"] = True
        if os.environ.get("CAPAS_SEM_IA"):
            return None
        try:
            try:
                from rembg import new_session
            except ImportError:
                print("Instalando a IA de recorte (rembg)...")
                subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "rembg[cpu]"],
                               check=True, timeout=900)
                from rembg import new_session
            _IA["sessao"] = new_session("isnet-general-use")
            print("IA de recorte pronta.")
        except Exception as e:  # noqa: BLE001
            print(f"::warning::IA de recorte indisponível ({str(e)[:120]}); seguindo só com o recorte por cor.")
        return _IA["sessao"]


def _ia_mascara(rgb):
    """Máscara 0..1 do objeto segundo a IA, ou None."""
    sessao = _ia_sessao()
    if sessao is None:
        return None
    try:
        from rembg import remove
        with _IA_VEZ:
            m = remove(Image.fromarray(rgb.astype(np.uint8), "RGB"), session=sessao,
                       only_mask=True, post_process_mask=False)
        m = np.asarray(m.convert("L"), dtype=np.float32) / 255.0
        return m if m.shape == rgb.shape[:2] else None
    except Exception as e:  # noqa: BLE001
        print(f"  IA falhou nesta imagem: {str(e)[:90]}")
        return None


# ---------------------------------------------------------------- tratamento
def _neutro_liso(rgb, vazio, croma=24, textura=5.0):
    """Pixel cinza (sem cor) e liso (sem desenho em volta): cara de sombra.
    A textura só conta os vizinhos que não são vazio."""
    rgbf = rgb.astype(np.float32)
    lum = rgbf.mean(axis=2)
    cro = rgbf.max(axis=2) - rgbf.min(axis=2)
    w = (~vazio).astype(np.float32)
    sw = ndimage.uniform_filter(w, 5) + 1e-6
    m = ndimage.uniform_filter(lum * w, 5) / sw
    m2 = ndimage.uniform_filter(lum * lum * w, 5) / sw
    dp = np.sqrt(np.clip(m2 - m * m, 0, None))
    return (cro <= croma) & (dp <= textura), lum


def _pecas(mask, minimo=0.02):
    """Fica só com as peças grandes (tira poeira e sobras soltas)."""
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    tam = ndimage.sum(mask, lab, range(1, n + 1))
    grandes = [k + 1 for k, v in enumerate(tam) if v >= minimo * tam.max()]
    return np.isin(lab, grandes)


def _limpa_sombra(rgb, alfa, passos=40, degrau=6, teto=0.12):
    """Sem IA: tira a sombra que a foto trazia, por cor e textura.
    A) sombra semitransparente a mais de 2 px do objeto sólido;
    B) faixa cinza e lisa colada no vazio, seguida passo a passo enquanto o
       degradê for suave (a borda do objeto é um degrau e para o avanço).
       Se a faixa passar de 12% do objeto, era parte dele: não mexe."""
    al = alfa.astype(np.float32)
    solido = al >= 200
    if solido.sum() < 50:
        return alfa
    dist = ndimage.distance_transform_edt(~solido)
    al = np.where((al < 200) & (dist > 2), 0, al)
    vazio = al < 40
    liso, lum = _neutro_liso(rgb, vazio, croma=20, textura=3.5)
    cand = liso & ~vazio
    est = np.ones((3, 3), bool)
    t = ndimage.binary_dilation(vazio, est) & cand
    if t.any():
        for _ in range(passos):
            vmin = ndimage.minimum_filter(np.where(t, lum, 1e4), 3)
            vmax = ndimage.maximum_filter(np.where(t, lum, -1e4), 3)
            ok = ndimage.binary_dilation(t, est) & cand & ~t & (lum >= vmin - degrau) & (lum <= vmax + degrau)
            if not ok.any():
                break
            t |= ok
        if t.sum() <= teto * max(1, (al >= 200).sum()):
            al = np.where(t, 0, al)
    f = _pecas(ndimage.binary_opening(al >= 128, iterations=1))
    al = np.where(ndimage.binary_dilation(f, est, iterations=2), al, 0)
    return al.astype(np.uint8)


def _refina(rgb, frente, alfa):
    """Tira a sombra original do recorte por cor. Com a IA: o que a IA diz
    que não é objeto e tem cara de sombra (cinza e liso) sai; o que ela diz
    que é objeto e o fundo branco tinha comido (lombada branca) volta.
    Só vale se a IA concordar com pelo menos 85% do recorte por cor."""
    ml = _ia_mascara(rgb)
    if ml is not None:
        mf = ml >= 0.5
        acordo = (mf & frente).sum() / max(1, frente.sum())
        if acordo >= 0.85:
            liso, _ = _neutro_liso(rgb, ~frente)
            sombra = frente & ~mf & liso
            volta = mf & ~frente & ndimage.binary_dilation(frente, iterations=3)
            novo = alfa.astype(np.float32)
            novo[sombra] = 0
            novo = np.maximum(novo, np.where(volta, ml * 255, 0))
            f = _pecas(novo >= 128)
            novo = np.where(ndimage.binary_dilation(f, iterations=2), novo, 0)
            return novo.astype(np.uint8), "fundo e sombra removidos"
    return _limpa_sombra(rgb, alfa), "fundo e sombra removidos (por cor)"


def _so_ia(rgba, cru=False):
    """Recorte só pela IA, para foto de caixa em que o fundo não é liso.
    Só aceita se a máscara for de um objeto inteiro e plausível.
    cru=True devolve (rgb, alfa, caixa) em vez da imagem pronta."""
    a = np.asarray(rgba)
    ml = _ia_mascara(a[..., :3].astype(np.int16))
    if ml is None:
        return None
    mf = _pecas(ml >= 0.5, 0.15)
    area = mf.mean()
    cx = _caixa(mf)
    if cx is None or not (0.2 <= area <= 0.97):
        return None
    x0, y0, x1, y1 = cx
    if (x1 - x0) * (y1 - y0) < 0.3 * mf.size:
        return None
    if ndimage.binary_fill_holes(mf[y0:y1, x0:x1]).mean() < 0.6:
        return None
    # a máscara precisa cobrir quase tudo que não é fundo claro: se ela
    # ficou só com a lombada de uma caixa branca, a IA errou
    rgb = a[..., :3].astype(np.int16)
    escuro = rgb.min(axis=2) < 225
    if escuro.sum() and (mf & escuro).sum() / escuro.sum() < 0.7:
        return None
    alfa = np.where(ndimage.binary_dilation(mf, iterations=2), ml * 255, 0).astype(np.uint8)
    if cru:
        return a[..., :3], alfa, cx
    out = Image.fromarray(np.dstack([a[..., :3], alfa]), "RGBA").crop(cx)
    return _folga(out)


# ---------------------------------------------------------------- avulso: capa reta
def _ret_interno(mask, alvo=0.985):
    """Maior retângulo "cheio" dentro do objeto: vai tirando o lado mais
    vazio até todos os lados terem pelo menos 98,5% de objeto. Num livro em
    3D isso sobra com a frente da capa (e às vezes a lombada)."""
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    while y1 - y0 > 20 and x1 - x0 > 20:
        c = (mask[y0, x0:x1].mean(), mask[y1 - 1, x0:x1].mean(),
             mask[y0:y1, x0].mean(), mask[y0:y1, x1 - 1].mean())
        k = int(np.argmin(c))
        if c[k] >= alvo:
            break
        if k == 0: y0 += 1
        elif k == 1: y1 -= 1
        elif k == 2: x0 += 1
        else: x1 -= 1
    return x0, y0, x1, y1


def _linha_forte(gray, frac=0.10, incl=0.03, thr=16):
    """Na faixa da direita (frac da largura), a linha quase vertical mais
    forte: é a divisa capa/páginas ou capa/lombada. Devolve (x, nota 0..1)."""
    H, W = gray.shape
    gx = np.abs(np.diff(gray, axis=1))
    gx = ndimage.maximum_filter(gx, size=(1, 2))
    faixa = max(3, int(W * frac))
    d = max(1, int(W * incl))
    ys = np.arange(H)
    melhor = (None, 0.0)
    for xt in range(W - 1 - faixa, W - 2):
        for dx in range(-d, d + 1, max(1, d // 4)):
            xb = xt + dx
            if xb < 0 or xb >= W - 1:
                continue
            xs = np.round(np.linspace(xt, xb, H)).astype(int)
            sc = float((gx[ys, xs] > thr).mean())
            if sc > melhor[1]:
                melhor = (min(xt, xb), sc)
    return melhor


def _claro_neutro(rgb):
    rgbf = rgb.astype(np.float32)
    return (rgbf.min(axis=2) >= 200) & ((rgbf.max(axis=2) - rgbf.min(axis=2)) <= 22)


def _reta_robusta(a, b):
    """b = m*a + c, ajustada sem ligar para os pontos fora da linha"""
    m, c = np.polyfit(a, b, 1)
    for _ in range(3):
        res = np.abs(b - (m * a + c))
        ok = res <= max(1.5, 2.5 * float(np.median(res)))
        if ok.sum() < 12:
            break
        m, c = np.polyfit(a[ok], b[ok], 1)
    return float(m), float(c)


def _quadro(mask):
    """Os quatro cantos da frente do livro (que em foto 3D é um quadrilátero
    torto). Cada lado é uma reta ajustada no miolo daquele lado, longe dos
    cantos, onde a lombada e as páginas se juntam. None se não fechar."""
    ys, xs = np.nonzero(mask)
    X0, X1, Y0, Y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = X1 - X0, Y1 - Y0
    cols = np.arange(int(X0 + 0.22 * w), int(X1 - 0.22 * w))
    rows = np.arange(int(Y0 + 0.22 * h), int(Y1 - 0.22 * h))
    if len(cols) < 20 or len(rows) < 20:
        return None
    sub_c = mask[:, cols]
    tem_c = sub_c.any(axis=0)
    topo = np.argmax(sub_c, axis=0)
    base = mask.shape[0] - 1 - np.argmax(sub_c[::-1], axis=0)
    sub_r = mask[rows, :]
    tem_r = sub_r.any(axis=1)
    esq = np.argmax(sub_r, axis=1)
    dir_ = mask.shape[1] - 1 - np.argmax(sub_r[:, ::-1], axis=1)
    c, r = cols[tem_c].astype(float), rows[tem_r].astype(float)
    mt, ct = _reta_robusta(c, topo[tem_c].astype(float))
    mb, cb = _reta_robusta(c, base[tem_c].astype(float))
    ml, cl = _reta_robusta(r, esq[tem_r].astype(float))
    mr, cr = _reta_robusta(r, dir_[tem_r].astype(float))
    if max(abs(mt), abs(mb)) > 0.35 or max(abs(ml), abs(mr)) > 0.15:
        return None

    def cruza(m, c_, n, d):      # y = m x + c  com  x = n y + d
        x = (n * c_ + d) / (1 - n * m)
        return x, m * x + c_
    tl, tr = cruza(mt, ct, ml, cl), cruza(mt, ct, mr, cr)
    br, bl = cruza(mb, cb, mr, cr), cruza(mb, cb, ml, cl)
    q = np.array([tl, tr, br, bl])
    if (q[:, 0].min() < X0 - 0.05 * w or q[:, 0].max() > X1 + 0.05 * w
            or q[:, 1].min() < Y0 - 0.05 * h or q[:, 1].max() > Y1 + 0.05 * h):
        return None
    xq, yq = q[:, 0], q[:, 1]
    area_q = 0.5 * abs(np.dot(xq, np.roll(yq, 1)) - np.dot(yq, np.roll(xq, 1)))
    if not (0.85 <= area_q / mask.sum() <= 1.08):
        return None
    return q


def _endireita(rgb, q):
    """Leva o quadrilátero q (tl, tr, br, bl) para um retângulo reto."""
    (tl, tr, br, bl) = q
    w = int(round((np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2))
    h = int(round((np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2))
    dst = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (x, y), (u, v) in zip(dst, q):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    coef = np.linalg.solve(np.array(A, float), np.array(B, float))
    img = Image.fromarray(rgb.astype(np.uint8), "RGB")
    return img.transform((w, h), Image.PERSPECTIVE, tuple(coef), Image.BICUBIC)


def _plana(rgb, alfa):
    """Livro avulso: devolve a FRENTE da capa como imagem reta (RGB), ou
    None quando não dá para achar com segurança. A frente é endireitada
    (foto em 3D vira capa reta). Nunca corta o topo (é onde fica o título);
    lombada e páginas só saem pelos lados, chão claro só por baixo."""
    mask = alfa >= 128
    if mask.sum() < 2000:
        return None
    lab, n = ndimage.label(mask)
    if n > 1:
        tam = np.sort(ndimage.sum(mask, lab, range(1, n + 1)))[::-1]
        if tam[1] >= 0.35 * tam[0]:
            return None                  # mais de um livro na foto: não é avulso
        mask = lab == (int(np.argmax(ndimage.sum(mask, lab, range(1, n + 1)))) + 1)
    mask = ndimage.binary_fill_holes(mask)
    area = int(mask.sum())
    # transparente em volta ganha a cor do pixel de objeto mais próximo: os
    # cantos que sobrarem depois de endireitar não ficam pretos nem brancos
    _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    cheio = rgb[..., :3][iy, ix]
    x0, y0, x1, y1 = _ret_interno(mask)
    reto = (x1 - x0) * (y1 - y0) / area >= 0.97
    q = None if reto else _quadro(mask)
    if q is not None:
        img = _endireita(cheio, q)
        motivo = "endireitada"
    else:
        img = Image.fromarray(cheio[y0:y1, x0:x1].astype(np.uint8), "RGB")
        motivo = "recortada"
    a = np.asarray(img).astype(np.int16)
    H, W = a.shape[:2]
    if W < 60 or H < 90:
        return None
    X0, X1, Y0, Y1 = 0, W, 0, H
    # lombada (esquerda) ou páginas (direita): divisa vertical forte perto da
    # borda. Até 13% sempre que a foto não era um retângulo; até 25% quando a
    # imagem está larga demais para ser só a frente de uma capa.
    if not reto:
        gray = a.astype(np.float32).mean(axis=2)
        larga = W / H > 0.74
        for lado in ("r", "l"):
            g = gray[:, X0:X1] if lado == "r" else gray[:, X0:X1][:, ::-1]
            ww = X1 - X0
            pos, sc = _linha_forte(g, frac=0.25 if larga else 0.13, incl=0.03)
            if pos is None:
                continue
            corte = ww - 1 - pos
            if (sc >= 0.75 and corte <= 0.13 * ww and (ww - corte) / H >= 0.55) or (larga and sc >= 0.8 and corte <= 0.25 * ww
                                                       and 0.58 <= (ww - corte) / H <= 0.76):
                if lado == "r":
                    X1 = X0 + pos + 1
                else:
                    X0 = X0 + corte
                larga = (X1 - X0) / H > 0.74
    # sobras claras (páginas, chão, fundo) coladas na borda: lados e base
    cn = _claro_neutro(a)
    k = 0
    while k < 0.08 * H and cn[Y1 - 1, X0:X1].mean() >= 0.85:
        Y1 -= 1; k += 1
    k = 0
    while k < 0.05 * W and cn[Y0:Y1, X0].mean() >= 0.85:
        X0 += 1; k += 1
    k = 0
    while k < 0.05 * W and cn[Y0:Y1, X1 - 1].mean() >= 0.85:
        X1 -= 1; k += 1
    mx, my = max(1, int(0.006 * (X1 - X0))), max(1, int(0.006 * (Y1 - Y0)))
    X0, X1, Y0, Y1 = X0 + mx, X1 - mx, Y0 + my, Y1 - my
    w, h = X1 - X0, Y1 - Y0
    if not (0.55 <= w / h <= 0.82):
        return None
    if q is None and (x1 - x0) * (y1 - y0) < 0.55 * area:
        return None
    return img.crop((X0, Y0, X1, Y1))


def _apara_branco(img, teto=0.08):
    """Capa reta com faixa branca pura em volta (margem de loja): tira as
    linhas e colunas da borda que são quase só branco."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    branco = (a.min(axis=2) >= 240) & ((a.max(axis=2) - a.min(axis=2)) <= 10)
    H, W = branco.shape
    y0, y1, x0, x1 = 0, H, 0, W
    while y0 < teto * H and branco[y0, x0:x1].mean() >= 0.98: y0 += 1
    while H - y1 < teto * H and branco[y1 - 1, x0:x1].mean() >= 0.98: y1 -= 1
    while x0 < teto * W and branco[y0:y1, x0].mean() >= 0.98: x0 += 1
    while W - x1 < teto * W and branco[y0:y1, x1 - 1].mean() >= 0.98: x1 -= 1
    # só é margem se acabar numa divisa nítida; capa de fundo branco (o branco
    # vai sumindo aos poucos no desenho) fica como está
    if y0 and (y0 >= teto * H or branco[y0, x0:x1].mean() > 0.6): y0 = 0
    if y1 < H and (H - y1 >= teto * H or branco[y1 - 1, x0:x1].mean() > 0.6): y1 = H
    if x0 and (x0 >= teto * W or branco[y0:y1, x0].mean() > 0.6): x0 = 0
    if x1 < W and (W - x1 >= teto * W or branco[y0:y1, x1 - 1].mean() > 0.6): x1 = W
    if (y0, y1, x0, x1) == (0, H, 0, W):
        return img, False
    return img.crop((x0, y0, x1, y1)), True


# ---------------------------------------------------------------- box: sem chão
def _sem_chao(rgb, alfa, teto=0.12):
    """Tira o "chão" que a foto trazia embaixo da caixa: reflexo claro, filete
    branco, sombra clara. Só mexe na faixa de baixo (12% da altura) e só em
    pixel claro e sem cor que encosta no vazio de fora. Se isso der mais da
    metade da faixa, é a própria caixa (caixa branca) e nada sai."""
    m = alfa >= 128
    cx = _caixa(m)
    if cx is None:
        return alfa
    x0, y0, x1, y1 = cx
    altura = int(teto * (y1 - y0))
    if altura < 2:
        return alfa
    faixa = np.zeros_like(m)
    faixa[y1 - altura:y1, :] = True
    rgbf = rgb.astype(np.float32)
    lum = rgbf.mean(axis=2)
    cro = rgbf.max(axis=2) - rgbf.min(axis=2)
    cand = (((lum >= 135) & (cro <= 30)) | ((alfa > 0) & (alfa < 200))) & (alfa > 0) & faixa
    if not cand.any():
        return alfa
    vazio = alfa < 40
    lab, _ = ndimage.label(cand)
    ids = np.unique(lab[ndimage.binary_dilation(vazio, iterations=1) & cand])
    tira = np.isin(lab, ids[ids > 0])
    if tira.sum() == 0 or tira.sum() > 0.5 * max(1, (m & faixa).sum()):
        return alfa
    # só o que fica ABAIXO da caixa: em cada coluna, abaixo do último pixel
    # de objeto de verdade (lombada branca que desce até a base fica)
    solido = m & ~cand
    tem = solido.any(axis=0)
    fundo_col = np.where(tem, solido.shape[0] - 1 - np.argmax(solido[::-1], axis=0), -1)
    linhas = np.arange(m.shape[0])[:, None]
    tira &= linhas > fundo_col[None, :]
    novo = alfa.copy()
    novo[tira] = 0
    f = _pecas(novo >= 128)
    return np.where(ndimage.binary_dilation(f, iterations=2), novo, 0).astype(np.uint8)


def _casco(rgb, limiar=16):
    """Caixa (ou livro) clara sobre fundo claro: o recorte por cor não acha a
    borda. Mas caixa e livro são objetos convexos: o contorno é o "casco"
    de tudo que não é fundo (lombadas, dourado, letras, quinas). Devolve o
    alfa do casco ou None se não parecer um objeto só."""
    from scipy.spatial import ConvexHull
    anel = _anel(rgb)
    fundo = np.median(anel, axis=0)
    dif = np.abs(rgb - fundo).max(axis=2) > limiar
    dif = ndimage.binary_opening(dif, iterations=1)
    dif = _pecas(dif, 0.004)
    H, W = dif.shape
    if dif.sum() < 0.02 * H * W:
        return None
    ys, xs = np.nonzero(dif)
    try:
        casco = ConvexHull(np.column_stack([xs, ys]))
    except Exception:  # noqa: BLE001
        return None
    pts = [(float(xs[k]), float(ys[k])) for k in casco.vertices]
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    alfa = np.asarray(m.filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(0.8)))
    area = (alfa >= 128).mean()
    if not (0.15 <= area <= 0.93):
        return None
    if dif[alfa >= 128].mean() < 0.12:     # quase nada de objeto dentro: não confia
        return None
    return alfa.astype(np.uint8)


def tratar(dados, recorte="", papel="avulso"):
    """Devolve (imagem RGBA ou RGB, tipo, motivo).

    recorte: "" decide sozinho; "sim" força tirar o fundo (foto de caixa em
    pé, por exemplo); "nao" deixa a imagem como veio.
    papel: "avulso" (livro solto: a capa sai reta e ocupa o quadro),
    "box" (caixa: recortada, sem sombra e sem chão) ou "colecao".

    Regra de ouro: na dúvida, a imagem fica como veio. Um fundo branco que
    sobra é um defeito pequeno; uma capa furada ou cortada é um defeito grande.
    """
    im = Image.open(io.BytesIO(dados))
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = ImageOps.exif_transpose(im)
    W, H = im.size
    if W < 60 or H < 60:
        raise ValueError(f"imagem pequena demais ({W}x{H}): costuma ser o aviso de 'sem imagem' da loja")
    rgba = im.convert("RGBA")
    a = np.asarray(rgba)
    avulso = papel == "avulso"
    if papel == "box" and recorte != "nao":
        recorte = "sim"                     # caixa sempre sai recortada

    def reta(rgb, alfa, motivo):
        """avulso: tenta a frente da capa reta; se não der, fica o recorte"""
        if avulso:
            p = _plana(rgb, alfa)
            if p is not None:
                return p, CAPA, "capa endireitada (" + motivo + ")"
        return None

    # 1) já veio recortada (PNG/WebP com transparência): só sai a sombra
    #    semitransparente que a editora deixou embaixo do livro
    alfa = a[..., 3]
    if (alfa < 245).mean() > 0.02:
        cx = _caixa(alfa > 16)
        if cx is None:
            raise ValueError("imagem toda transparente")
        rgb0 = a[..., :3].astype(np.int16)
        limpo = _limpa_sombra(rgb0, alfa)
        if papel == "box":
            limpo = _sem_chao(rgb0, limpo)
        r = reta(a[..., :3], limpo, "veio sem fundo")
        if r:
            return r
        cx = _caixa(limpo > 16) or cx
        out = Image.fromarray(np.dstack([a[..., :3], limpo]), "RGBA").crop(cx)
        return _folga(out), RECORTE, "já veio sem fundo (sombra tirada)"

    r0 = W / H
    em_pe = 0.58 <= r0 <= 0.78
    if recorte == "nao":
        return rgba.convert("RGB"), (CAPA if em_pe else FOTO), "mantida como veio (pedido)"

    def como_veio(motivo):
        """capa em pé que fica como veio: sem a margem branca pura em volta"""
        img = rgba.convert("RGB")
        if avulso:
            img, aparou = _apara_branco(img)
            if aparou and 0.55 <= img.width / img.height <= 0.82:
                return img, CAPA, motivo + " (margem branca cortada)"
            img = rgba.convert("RGB")
        return img, CAPA, motivo

    def desiste(motivo_capa, motivo_foto):
        # sem fundo liso para tirar: foto de caixa (ou livro avulso fora do
        # formato de capa) ainda tenta pela IA; o resto fica como veio
        rgb_ = a[..., :3].astype(np.int16)
        anel_ = _anel(rgb_)
        claro_ = ((anel_.min(axis=1) >= 226) & ((anel_.max(axis=1) - anel_.min(axis=1)) <= 16)).mean()
        if claro_ >= 0.45 and (recorte == "sim" or not em_pe):
            # caixa branca em fundo branco: contorno pelo casco do objeto
            alfa_c = _casco(rgb_)
            if alfa_c is not None:
                if papel == "box":
                    alfa_c = _sem_chao(rgb_, alfa_c)
                r = reta(a[..., :3], alfa_c, "contorno")
                if r:
                    return r
                if recorte == "sim" or not avulso:
                    cx_c = _caixa(alfa_c > 16)
                    out = Image.fromarray(np.dstack([a[..., :3], alfa_c]), "RGBA").crop(cx_c)
                    return _folga(out), RECORTE, "fundo removido (contorno do objeto)"
        if recorte == "sim" or (avulso and not em_pe):
            ia = _so_ia(rgba, cru=True)
            if ia is not None:
                rgb_ia, alfa_ia, cx_ia = ia
                r = reta(rgb_ia, alfa_ia, "IA")
                if r:
                    return r
                if recorte == "sim" or not avulso:
                    out = Image.fromarray(np.dstack([rgb_ia, alfa_ia]), "RGBA").crop(cx_ia)
                    return _folga(out), RECORTE, "fundo removido (IA)"
        if em_pe:
            return como_veio(motivo_capa)
        return rgba.convert("RGB"), FOTO, motivo_foto

    # 2) fundo liso (branco de loja ou estúdio de outra cor)
    rgb = a[..., :3].astype(np.int16)
    anel = _anel(rgb)
    mediana = np.median(anel, axis=0)
    claro = (rgb.min(axis=2) >= 226) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 16)
    claro_anel = (anel.min(axis=1) >= 226) & ((anel.max(axis=1) - anel.min(axis=1)) <= 16)
    if claro_anel.mean() >= 0.6:
        # fundo de loja (branco ou quase): sombra suave e cinza bem claro também saem
        cand = claro | (np.abs(rgb - mediana).max(axis=2) <= 26)
    elif (np.abs(anel - mediana).max(axis=1) <= 10).mean() >= 0.95:
        # fundo liso de outra cor (estúdio)
        cand = np.abs(rgb - mediana).max(axis=2) <= 26
    else:
        return desiste("capa", "foto com cenário: o fundo não é liso")

    # só sai o fundo encostado na borda: o branco DENTRO da caixa fica
    rot, _ = ndimage.label(cand)
    na_borda = np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))
    tirar = np.isin(rot, na_borda[na_borda > 0])

    # o fundo precisa formar moldura em pelo menos dois lados opostos
    lados = [tirar[0].mean(), tirar[-1].mean(), tirar[:, 0].mean(), tirar[:, -1].mean()]
    if not ((lados[0] >= 0.9 and lados[1] >= 0.9) or (lados[2] >= 0.9 and lados[3] >= 0.9)):
        return desiste("capa", "o fundo não envolve o objeto: mantida como veio")

    frente = ~tirar
    cx = _caixa(frente)
    if cx is None or frente.mean() < 0.06:
        return desiste("capa", "não achei o objeto no meio do fundo")
    x0, y0, x1, y1 = cx
    # o objeto precisa ser cheio (caixa, livro, pilha); se o que sobrou é
    # espalhado, o "fundo" era parte do desenho e não se mexe
    cheio = ndimage.binary_fill_holes(frente[y0:y1, x0:x1]).mean()
    if cheio < 0.72:
        return desiste("capa", "o fundo se confunde com a imagem: mantida como veio")

    # imagem em pé: na dúvida é capa. Capa reta com moldura branca em volta
    # é cortada rente e continua capa (sem virar recorte). Só sai o fundo
    # quando é foto de objeto: fundo branco nos quatro lados, objeto cheio e
    # contorno que não é um retângulo (livro em 3D, caixa, pilha, sombra).
    # Livro avulso com fundo branco nos quatro lados também passa pelo
    # recorte, para sair dele a capa reta.
    so_reta = False
    if em_pe and recorte != "sim":
        quatro = min(lados) >= 0.97
        branco = mediana.min() >= 240
        margens = min(x0 / W, y0 / H, (W - x1) / W, (H - y1) / H) >= 0.015
        if quatro and margens and cheio >= 0.985 and 0.58 <= (x1 - x0) / max(1, y1 - y0) <= 0.8:
            return rgba.convert("RGB").crop(cx), CAPA, "capa (moldura branca cortada)"
        objeto = quatro and branco and margens and cheio >= 0.9 and cheio < 0.985
        # avulso: livro sólido sobre fundo branco (mesmo encostando no alto e
        # embaixo) também passa pelo recorte para sair a capa reta; capa de
        # desenho branco (o "objeto" vira um recorte vazado) não passa
        solido = (avulso and branco and cheio >= 0.93
                  and (x1 - x0) * (y1 - y0) >= 0.6 * W * H)
        if not (objeto or solido):
            return como_veio("capa")
        so_reta = solido and not objeto       # se não sair capa reta, fica como veio

    duro = ndimage.binary_opening(frente, iterations=1)       # tira poeira solta do fundo
    duro = ndimage.binary_erosion(duro, iterations=1)         # 1 px para dentro: some o halo branco
    suave = ndimage.gaussian_filter(duro.astype(np.float32), 0.8)
    alfa_novo = (np.clip(suave * 1.25, 0, 1) * 255).astype(np.uint8)
    alfa_novo, motivo = _refina(rgb, frente, alfa_novo)
    if papel == "box":
        alfa_novo = _sem_chao(rgb, alfa_novo)
        motivo += ", chão tirado"
    r = reta(a[..., :3], alfa_novo, motivo)
    if r:
        return r
    if em_pe and recorte != "sim" and so_reta:
        return como_veio("capa")
    cx2 = _caixa(alfa_novo > 16) or cx
    out = np.dstack([a[..., :3], alfa_novo])
    img = Image.fromarray(out, "RGBA").crop(cx2)
    return _folga(img), RECORTE, motivo


def _folga(img, f=0.03):
    """Respiro transparente em volta do recorte, para a sombra não cortar."""
    W, H = img.size
    p = max(2, int(max(W, H) * f))
    nova = Image.new("RGBA", (W + 2 * p, H + 2 * p), (0, 0, 0, 0))
    nova.paste(img, (p, p), img if img.mode == "RGBA" else None)
    return nova


def reduzir(img):
    """Grande demais: reduz. Pequena: amplia até LADO_MIN com reforço leve
    de nitidez (a ampliação do navegador é mais borrada que esta)."""
    from PIL import ImageFilter
    W, H = img.size
    k = LADO_MAX / max(W, H)
    if k < 1:
        return img.resize((max(1, round(W * k)), max(1, round(H * k))), Image.LANCZOS)
    if max(W, H) < LADO_MIN:
        k = min(LADO_MIN / max(W, H), 2.5)
        novo = img.resize((round(W * k), round(H * k)), Image.LANCZOS)
        if novo.mode == "RGBA":
            rgb = novo.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=2))
            rgb.putalpha(novo.getchannel("A"))
            return rgb
        return novo.filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=2))
    return img


def gravar(img, caminho):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    if FORMATO == "png":
        img.save(caminho, "PNG", optimize=True)
    elif img.mode == "RGBA":
        img.save(caminho, "WEBP", quality=86, alpha_quality=90, method=6)
    else:
        img.save(caminho, "WEBP", quality=86, method=6)


# ----------------------------------------------------------------- folhas de conferência
def _fonte(tam):
    for cam in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if os.path.exists(cam):
            return ImageFont.truetype(cam, tam)
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _xadrez(w, h, q=10):
    """Fundo escuro em xadrez, parecido com o fundo personalizado do site:
    sobra de fundo branco ou de sombra cinza aparece na hora."""
    base = Image.new("RGB", (w, h), (52, 44, 62))
    d = ImageDraw.Draw(base)
    for y in range(0, h, q):
        for x in range(0, w, q):
            if (x // q + y // q) % 2:
                d.rectangle([x, y, x + q - 1, y + q - 1], fill=(64, 55, 76))
    return base


COR_TIPO = {CAPA: (46, 120, 80), RECORTE: (44, 95, 138), FOTO: (185, 118, 31), FALHOU: (138, 47, 63)}


def folhas(itens, prefixo, titulo, por_folha=40, colunas=8):
    """itens: lista de (rotulo, caminho_da_imagem_ou_None, tipo, nota).
    Cada célula: a imagem tratada sobre xadrez (o xadrez aparece onde o fundo
    ficou transparente), o número, o rótulo e o tipo."""
    os.makedirs(PASTA_CONF, exist_ok=True)
    for velho in os.listdir(PASTA_CONF):
        if velho.startswith(prefixo + "-") and velho.endswith(".jpg"):
            os.remove(os.path.join(PASTA_CONF, velho))
    cw, ch, iw, ih = 190, 300, 170, 230
    f_num, f_txt = _fonte(15), _fonte(12)
    total = (len(itens) + por_folha - 1) // por_folha
    for p in range(total):
        bloco = itens[p * por_folha:(p + 1) * por_folha]
        linhas = (len(bloco) + colunas - 1) // colunas
        folha = Image.new("RGB", (colunas * cw + 20, linhas * ch + 60), (250, 247, 242))
        d = ImageDraw.Draw(folha)
        d.text((12, 14), f"{titulo} · folha {p + 1} de {total}", fill=(30, 24, 18), font=_fonte(20))
        for k, (rot, cam, tipo, nota) in enumerate(bloco):
            x = 10 + (k % colunas) * cw
            y = 50 + (k // colunas) * ch
            celula = _xadrez(iw, ih)
            if cam and os.path.exists(cam):
                im = Image.open(cam).convert("RGBA")
                im.thumbnail((iw, ih))
                celula.paste(im, ((iw - im.width) // 2, (ih - im.height) // 2), im)
            else:
                ImageDraw.Draw(celula).text((10, ih // 2 - 8), "NÃO BAIXOU", fill=(138, 47, 63), font=f_num)
            folha.paste(celula, (x + 10, y))
            d.rectangle([x + 10, y + ih, x + 10 + iw, y + ih + 5], fill=COR_TIPO.get(tipo, (120, 120, 120)))
            n = p * por_folha + k + 1
            d.text((x + 10, y + ih + 8), f"{n:03d}", fill=(30, 24, 18), font=f_num)
            d.text((x + 50, y + ih + 10), rot[:22], fill=(60, 50, 40), font=f_txt)
            d.text((x + 10, y + ih + 28), (NOME_TIPO.get(tipo, "") + (" · " + nota if nota else ""))[:28],
                   fill=COR_TIPO.get(tipo, (90, 90, 90)), font=f_txt)
        folha.save(os.path.join(PASTA_CONF, f"{prefixo}-{p + 1:02d}.jpg"), "JPEG", quality=80)


# ----------------------------------------------------------------- principal
def main(acervo=os.path.join(RAIZ, "acervo.js"), baixador=baixar):
    conferir_site()
    livros = ler_acervo(acervo)
    ext = "." + FORMATO
    os.makedirs(PASTA, exist_ok=True)
    rel_path = os.path.join(PASTA, "relatorio.json")
    antigo = {}
    if os.path.exists(rel_path):
        try:
            antigo = json.load(open(rel_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            antigo = {}
    ant_itens = antigo.get("itens", {}) if antigo.get("versao") == VERSAO and antigo.get("formato") == FORMATO else {}
    ant_sug = antigo.get("sug", {}) if ant_itens else {}

    tarefas = []           # (chave, [urls], caminho, grupo, recorte, papel)
    for b in livros:
        papel = "box" if b.get("box") else ("colecao" if b.get("parts") else "avulso")
        if b.get("img"):
            # "alt": outros endereços da MESMA capa, tentados em ordem se o
            # principal falhar; a cópia guardada vale para a URL principal
            urls = [b["img"]] + [u for u in (b.get("alt") or []) if u and u != b["img"]]
            tarefas.append((b["slug"], urls, os.path.join(PASTA, b["slug"] + ext), "itens",
                            b.get("recorte", ""), papel))
        for s in b.get("sug", []) or []:
            h = marca(s["u"])
            tarefas.append((h, [s["u"]], os.path.join(PASTA_SUG, h + ext), "sug", "", "avulso"))
    vistos = set()
    tarefas = [t for t in tarefas if not (t[0] in vistos or vistos.add(t[0]))]

    def fazer(t):
        chave, urls, cam, grupo, recorte, papel = t
        h = marca(urls[0])
        assin = marca("|".join(urls) + "#" + recorte + "#" + papel)   # muda se mudar alternativa, pedido ou papel
        velho = (ant_itens if grupo == "itens" else ant_sug).get(chave)
        if (velho and velho.get("h") == h and velho.get("s") == assin
                and velho.get("t") != FALHOU and os.path.exists(cam)):
            return chave, grupo, dict(velho, novo=False)
        erros = []
        for k, url in enumerate(urls):
            try:
                dados, usada = baixar_melhor(url, baixador)
                img, tipo, motivo = tratar(dados, recorte, papel)
                orig = (img.width, img.height)
                img = reduzir(img)
                gravar(img, cam)
                if k:
                    motivo += f" (pelo endereço alternativo {k})"
                if usada != url:
                    motivo += " · versão maior"
                if max(img.size) > max(orig) and max(orig) < LADO_MIN:
                    motivo += f" · ampliada de {orig[0]}x{orig[1]}"
                return chave, grupo, {"h": h, "s": assin, "t": tipo, "r": round(img.width / img.height, 3),
                                      "w": img.width, "a": img.height, "kb": round(os.path.getsize(cam) / 1024),
                                      "motivo": motivo, "url": url, "usada": usada, "fonte": k,
                                      "papel": papel, "novo": True}
            except Exception as e:  # noqa: BLE001
                erros.append(str(e)[:90])
        if os.path.exists(cam):
            os.remove(cam)
        return chave, grupo, {"h": h, "s": assin, "t": FALHOU, "motivo": " / ".join(erros)[:180],
                              "url": urls[0], "novo": True}

    with ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(fazer, tarefas))

    itens = {c: r for c, g, r in resultados if g == "itens"}
    sug = {c: r for c, g, r in resultados if g == "sug"}

    # arquivos que não pertencem mais a nenhum anúncio
    for pasta, validos in ((PASTA, set(itens)), (PASTA_SUG, set(sug))):
        if os.path.isdir(pasta):
            for f in os.listdir(pasta):
                if f.endswith(ext) and f[:-len(ext)] not in validos:
                    os.remove(os.path.join(pasta, f))

    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M")
    conta = {t: sum(1 for r in itens.values() if r["t"] == t) for t in (CAPA, RECORTE, FOTO, FALHOU)}

    # manifesto lido pelo site: só o necessário, para a página continuar leve
    manif = {
        "v": VERSAO, "ext": FORMATO, "gerado": agora,
        "itens": {c: {"h": r["h"], "t": r["t"], "r": r.get("r", 0)} for c, r in sorted(itens.items())},
        "sug": {c: {"h": r["h"], "t": r["t"], "r": r.get("r", 0)} for c, r in sorted(sug.items())},
        "conta": conta,
    }
    with open(os.path.join(PASTA, "capas.js"), "w", encoding="utf-8") as f:
        f.write("/* gerado por ferramentas/capas.py: não edite à mão */\n")
        f.write("window.ACERVO_CAPAS = " + json.dumps(manif, ensure_ascii=False, separators=(",", ":")) + ";\n")

    rel = {"versao": VERSAO, "formato": FORMATO, "gerado": agora, "conta": conta,
           "itens": {c: {k: v for k, v in r.items() if k != "novo"} for c, r in sorted(itens.items())},
           "sug": {c: {k: v for k, v in r.items() if k != "novo"} for c, r in sorted(sug.items())}}
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=1)

    # folhas: só refaz quando alguma imagem mudou (ou ainda não existem)
    mudou = any(r.get("novo") for _, _, r in resultados) or not os.path.isdir(PASTA_CONF)
    if mudou:
        ordem = [b["slug"] for b in livros if b["slug"] in itens]
        todas = [(s, os.path.join(PASTA, s + ext), itens[s]["t"], "") for s in ordem]
        folhas(todas, "capas", "Capas do acervo")
        problemas = [x for x in todas if x[2] in (FOTO, FALHOU)]
        folhas(problemas, "atencao", "Precisam de atenção (cenário ou não baixou)")
        alvos = {}
        for b in livros:
            for s in b.get("sug", []) or []:
                alvos.setdefault(marca(s["u"]), []).append(b["slug"])
        lista_sug = [(h + " " + ",".join(a)[:12], os.path.join(PASTA_SUG, h + ext), sug[h]["t"], "")
                     for h, a in alvos.items() if h in sug]
        folhas(lista_sug, "sugestoes", "Imagens sugeridas (campo sug)")
        with open(os.path.join(PASTA_CONF, "indice.txt"), "w", encoding="utf-8") as f:
            f.write(f"Folhas geradas em {agora}\n\n== capas ==\n")
            for n, (s, _, t, _) in enumerate(todas, 1):
                f.write(f"{n:03d}  {NOME_TIPO[t]:<17} {s}  {itens[s].get('motivo', '')}\n")
            f.write("\n== atencao ==\n")
            for n, (s, _, t, _) in enumerate(problemas, 1):
                f.write(f"{n:03d}  {NOME_TIPO[t]:<17} {s}  {itens[s].get('motivo', '')}  {itens[s].get('url', '')}\n")
            f.write("\n== sugestoes ==\n")
            for n, (rot, _, t, _) in enumerate(lista_sug, 1):
                h = rot.split(" ")[0]
                f.write(f"{n:03d}  {NOME_TIPO[t]:<17} {h} -> {', '.join(alvos[h])}  {sug[h].get('url', '')}\n")

    novos = sum(1 for _, _, r in resultados if r.get("novo"))
    print(f"{len(itens)} capas: {conta[CAPA]} capa, {conta[RECORTE]} fundo removido, "
          f"{conta[FOTO]} foto com cenário, {conta[FALHOU]} não baixaram · {len(sug)} sugestões · {novos} processadas agora")
    for c, r in itens.items():
        if r["t"] == FALHOU:
            print(f"  NÃO BAIXOU  {c}: {r['motivo']}")
    return rel


if __name__ == "__main__":
    main(*sys.argv[1:2])
