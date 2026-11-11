#!/usr/bin/env python3
"""
capas.py: o robô de capas do Acervo Literário.

Roda sozinho no GitHub (ver .github/workflows/publicar.yml) a cada vez que o
site é publicado. Para cada anúncio do acervo.js que tem capa (campo `img`) e
para cada imagem sugerida (campo `sug`):

  1. baixa a imagem direto do servidor de origem;
  2. tira o fundo quando ele é liso (foto de caixa ou de livro em fundo branco),
     deixando o fundo transparente; capa de livro "justa", sem moldura, fica
     como está, porque não tem fundo para tirar;
  3. guarda uma cópia leve dentro do próprio site, em capas/<slug>.webp;
  4. escreve capas/capas.js, que o site lê para usar a cópia guardada;
  5. escreve capas/relatorio.json com o que deu certo e o que precisa de
     atenção, e as folhas de conferência em capas/conferencia/.

Imagem que já foi tratada e cuja URL não mudou não é baixada de novo.

Formato: WebP com transparência. É a mesma transparência do PNG com uma
fração do peso, e todos os navegadores atuais abrem. Para gerar PNG, mude
FORMATO abaixo para "png" (os arquivos ficam umas cinco vezes maiores).
"""
import io
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage

VERSAO = 1                  # mude para reprocessar tudo depois de alterar o tratamento
FORMATO = "webp"            # "webp" ou "png"
LADO_MAX = 720              # maior lado da imagem guardada, em pixels
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


# ----------------------------------------------------------------- tratamento
def _anel(rgb, k=3):
    return np.concatenate([rgb[:k].reshape(-1, 3), rgb[-k:].reshape(-1, 3),
                           rgb[:, :k].reshape(-1, 3), rgb[:, -k:].reshape(-1, 3)])


def _caixa(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def tratar(dados):
    """Devolve (imagem RGBA ou RGB, tipo, motivo).

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

    # 1) já veio recortada (PNG/WebP com transparência)
    alfa = a[..., 3]
    if (alfa < 245).mean() > 0.02:
        cx = _caixa(alfa > 16)
        if cx is None:
            raise ValueError("imagem toda transparente")
        return _folga(rgba.crop(cx)), RECORTE, "já veio sem fundo"

    # 2) formato de capa (de 0,58 a 0,78): é a própria capa, e a borda dela,
    #    mesmo branca ou lisa, faz parte do desenho. Não se recorta.
    r0 = W / H
    if 0.58 <= r0 <= 0.78:
        return rgba.convert("RGB"), CAPA, "capa"

    # 3) outros formatos (quadrado, deitado): foto de caixa, de kit ou de pilha.
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
        return rgba.convert("RGB"), FOTO, "foto com cenário: o fundo não é liso"

    # só sai o fundo encostado na borda: o branco DENTRO da caixa fica
    rot, _ = ndimage.label(cand)
    na_borda = np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))
    tirar = np.isin(rot, na_borda[na_borda > 0])

    # o fundo precisa formar moldura em pelo menos dois lados opostos
    lados = [tirar[0].mean(), tirar[-1].mean(), tirar[:, 0].mean(), tirar[:, -1].mean()]
    if not ((lados[0] >= 0.9 and lados[1] >= 0.9) or (lados[2] >= 0.9 and lados[3] >= 0.9)):
        return rgba.convert("RGB"), FOTO, "o fundo não envolve o objeto: mantida como veio"

    frente = ~tirar
    cx = _caixa(frente)
    if cx is None or frente.mean() < 0.06:
        return rgba.convert("RGB"), FOTO, "não achei o objeto no meio do fundo"
    x0, y0, x1, y1 = cx
    # o objeto precisa ser cheio (caixa, livro, pilha); se o que sobrou é
    # espalhado, o "fundo" era parte do desenho e não se mexe
    if ndimage.binary_fill_holes(frente[y0:y1, x0:x1]).mean() < 0.72:
        return rgba.convert("RGB"), FOTO, "o fundo se confunde com a imagem: mantida como veio"

    duro = ndimage.binary_opening(frente, iterations=1)       # tira poeira solta do fundo
    duro = ndimage.binary_erosion(duro, iterations=1)         # 1 px para dentro: some o halo branco
    suave = ndimage.gaussian_filter(duro.astype(np.float32), 0.8)
    alfa_novo = (np.clip(suave * 1.25, 0, 1) * 255).astype(np.uint8)
    out = np.dstack([a[..., :3], alfa_novo])
    img = Image.fromarray(out, "RGBA").crop(cx)
    return _folga(img), RECORTE, "fundo removido"


def _folga(img, f=0.03):
    """Respiro transparente em volta do recorte, para a sombra não cortar."""
    W, H = img.size
    p = max(2, int(max(W, H) * f))
    nova = Image.new("RGBA", (W + 2 * p, H + 2 * p), (0, 0, 0, 0))
    nova.paste(img, (p, p), img if img.mode == "RGBA" else None)
    return nova


def reduzir(img):
    W, H = img.size
    k = LADO_MAX / max(W, H)
    if k < 1:
        img = img.resize((max(1, round(W * k)), max(1, round(H * k))), Image.LANCZOS)
    return img


def gravar(img, caminho):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    if FORMATO == "png":
        img.save(caminho, "PNG", optimize=True)
    elif img.mode == "RGBA":
        img.save(caminho, "WEBP", quality=84, alpha_quality=90, method=6)
    else:
        img.save(caminho, "WEBP", quality=82, method=6)


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
    base = Image.new("RGB", (w, h), (236, 232, 224))
    d = ImageDraw.Draw(base)
    for y in range(0, h, q):
        for x in range(0, w, q):
            if (x // q + y // q) % 2:
                d.rectangle([x, y, x + q - 1, y + q - 1], fill=(214, 208, 198))
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

    tarefas = []           # (chave, url, caminho, grupo)
    for b in livros:
        if b.get("img"):
            tarefas.append((b["slug"], b["img"], os.path.join(PASTA, b["slug"] + ext), "itens"))
        for s in b.get("sug", []) or []:
            h = marca(s["u"])
            tarefas.append((h, s["u"], os.path.join(PASTA_SUG, h + ext), "sug"))
    vistos = set()
    tarefas = [t for t in tarefas if not (t[0] in vistos or vistos.add(t[0]))]

    def fazer(t):
        chave, url, cam, grupo = t
        h = marca(url)
        velho = (ant_itens if grupo == "itens" else ant_sug).get(chave)
        if velho and velho.get("h") == h and velho.get("t") != FALHOU and os.path.exists(cam):
            return chave, grupo, dict(velho, novo=False)
        try:
            dados = baixador(url)
            img, tipo, motivo = tratar(dados)
            img = reduzir(img)
            gravar(img, cam)
            return chave, grupo, {"h": h, "t": tipo, "r": round(img.width / img.height, 3),
                                  "w": img.width, "a": img.height, "kb": round(os.path.getsize(cam) / 1024),
                                  "motivo": motivo, "url": url, "novo": True}
        except Exception as e:  # noqa: BLE001
            if os.path.exists(cam):
                os.remove(cam)
            return chave, grupo, {"h": h, "t": FALHOU, "motivo": str(e)[:180], "url": url, "novo": True}

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
