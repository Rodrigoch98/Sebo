#!/usr/bin/env python3
"""
pesquisa.py: pesquisa das edições brasileiras de cada livro do acervo.

Roda no GitHub depois da publicação (ver .github/workflows/publicar.yml) e
NÃO muda o site: só junta material para a escolha das capas.

Para cada anúncio que é um livro (ou um box fechado):
  1. procura as edições no Google Books e na Open Library;
  2. fica só com as edições brasileiras (ISBN 978-85 ou 978-65);
  3. ordena da mais antiga para a mais nova;
  4. baixa a capa de cada edição (Amazon pelo ISBN, Google Books, Open Library);
  5. monta folhas de comparação: a capa atual do site ao lado das candidatas,
     cada uma com ano e editora, em pesquisa/folha-NN.jpg, com o índice em
     pesquisa/indice.txt e tudo em pesquisa/resultado.json.

O que já foi pesquisado fica guardado e não é refeito. Para refazer um livro
com outra busca, escreva em pesquisa/pedidos.txt uma linha:
    slug-do-livro | título para buscar | autor
"""
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capas as R  # noqa: E402  (reaproveita leitura do acervo, download e tratamento)

PASTA = os.path.join(R.RAIZ, "pesquisa")
RESULTADO = os.path.join(PASTA, "resultado.json")
PEDIDOS = os.path.join(PASTA, "pedidos.txt")
MAX_CAND = 5                                      # candidatas por livro na folha
CHAVE = os.environ.get("GOOGLE_BOOKS_KEY", "")    # opcional: segredo do repositório
MINUTOS = float(os.environ.get("PESQUISA_MINUTOS", "25"))
VERSAO = 1


# ----------------------------------------------------------------- textos
def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def titulo_base(b):
    t = b.get("tm") or b["t"]
    t = re.split(r"\s+[—–-]\s+", t)[0]
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"^(box|cole[cç][aã]o|kit|dupla|trilogia|saga)\s+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def autor_base(b):
    a = b.get("a") or ""
    return re.split(r"\s+e\s+|,|&|/", a)[0].strip()


def dicas(b):
    """O que a descrição diz sobre a edição: ajuda a escolher a candidata certa."""
    d = norm(b.get("d", "") + " " + b.get("t", ""))
    achou = [p for p in ("capa dura", "luxo", "edicao especial", "bolso", "pocket", "box",
                         "darkside", "10 anos", "ilustrad", "colecionador") if p in d]
    for ed in ("rocco", "intrinseca", "galera", "record", "nova fronteira", "harpercollins", "l pm",
               "globo", "arqueiro", "sextante", "suma", "companhia", "seguinte", "aleph", "leya",
               "plataforma 21", "novo conceito", "martin claret", "principis", "martins fontes", "zahar"):
        if re.search(r"\b" + ed + r"\b", d):
            achou.append(ed)
    if b.get("conf"):
        achou.append("conferido")
    return ", ".join(dict.fromkeys(achou))


# ----------------------------------------------------------------- ISBN
def isbn10(i13):
    if not (len(i13) == 13 and i13.startswith("978")):
        return None
    core = i13[3:12]
    s = sum((10 - k) * int(c) for k, c in enumerate(core))
    d = (11 - s % 11) % 11
    return core + ("X" if d == 10 else str(d))


def isbn13(i10):
    core = "978" + i10[:9]
    s = sum(int(c) * (1 if k % 2 == 0 else 3) for k, c in enumerate(core))
    return core + str((10 - s % 10) % 10)


def brasileiro(i):
    return (len(i) == 13 and i[:5] in ("97885", "97865")) or (len(i) == 10 and i.startswith("85"))


# ----------------------------------------------------------------- rede
def pegar_json(url, tentativas=4):
    espera = 4
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": R.AGENTE, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and t < tentativas - 1:
                time.sleep(espera)
                espera *= 2
                continue
            raise
        except Exception:  # noqa: BLE001
            if t == tentativas - 1:
                raise
            time.sleep(2)


def parecido(titulo, achado):
    """O título achado precisa conter quase todas as palavras do nosso."""
    nossas = [w for w in norm(titulo).split() if len(w) > 2] or norm(titulo).split()
    deles = set(norm(achado).split())
    return nossas and sum(w in deles for w in nossas) / len(nossas) >= 0.7


def edicoes(titulo, autor):
    eds = {}
    # Google Books: é a fonte com mais edições brasileiras e com ano e editora
    for q in ([f'intitle:"{titulo}"' + (f' inauthor:"{autor}"' if autor else ""),
               f"intitle:{titulo}" + (f" inauthor:{autor}" if autor else "")]):
        p = {"q": q, "langRestrict": "pt", "maxResults": "40", "printType": "books",
             "fields": "items(id,volumeInfo(title,subtitle,publisher,publishedDate,industryIdentifiers,imageLinks))"}
        if CHAVE:
            p["key"] = CHAVE
        try:
            dados = pegar_json("https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(p))
        except Exception as e:  # noqa: BLE001
            print(f"   google falhou: {e}")
            dados = {}
        for it in dados.get("items", []) or []:
            v = it.get("volumeInfo", {})
            if not parecido(titulo, (v.get("title", "") + " " + v.get("subtitle", ""))):
                continue
            ids = {x.get("type"): x.get("identifier", "").replace("-", "") for x in v.get("industryIdentifiers", [])}
            i13 = ids.get("ISBN_13") or (isbn13(ids["ISBN_10"]) if ids.get("ISBN_10", "")[:9].isdigit() else None)
            if not i13 or not brasileiro(i13):
                continue
            ano = (v.get("publishedDate") or "")[:4]
            eds.setdefault(i13, {"isbn": i13, "ano": int(ano) if ano.isdigit() else None,
                                 "editora": v.get("publisher", ""), "gid": it.get("id"),
                                 "titulo": v.get("title", "")})
        if eds:
            break
        time.sleep(0.6)
    # Open Library: completa com ISBNs brasileiros que o Google não trouxe
    try:
        p = {"title": titulo, "fields": "title,isbn,publisher", "limit": "5"}
        if autor:
            p["author"] = autor
        dados = pegar_json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(p))
        for doc in dados.get("docs", []) or []:
            if not parecido(titulo, doc.get("title", "")):
                continue
            for i in doc.get("isbn", []) or []:
                i = i.replace("-", "")
                i13 = i if len(i) == 13 else (isbn13(i) if len(i) == 10 and i[:9].isdigit() else None)
                if i13 and brasileiro(i13) and i13 not in eds:
                    eds[i13] = {"isbn": i13, "ano": None, "editora": "", "gid": None, "titulo": doc.get("title", "")}
    except Exception as e:  # noqa: BLE001
        print(f"   open library falhou: {e}")
    # mais antiga primeiro; sem ano vai para o fim
    return sorted(eds.values(), key=lambda e: (e["ano"] is None, e["ano"] or 0, e["isbn"]))


# ----------------------------------------------------------------- capas das edições
def fontes_da_capa(e):
    urls = []
    i10 = isbn10(e["isbn"])
    if i10:
        urls.append(f"https://m.media-amazon.com/images/P/{i10}.01._SCLZZZZZZZ_.jpg")
    if e.get("gid"):
        urls.append(f"https://books.google.com/books/publisher/content/images/frontcover/{e['gid']}?fife=w600-h900")
        urls.append(f"https://books.google.com/books/content?id={e['gid']}&printsec=frontcover&img=1&zoom=1")
    urls.append(f"https://covers.openlibrary.org/b/isbn/{e['isbn']}-L.jpg?default=false")
    return urls


def assinatura(img):
    """Média 8x8 em cinza: duas edições com a mesma capa não aparecem duas vezes."""
    p = np.asarray(img.convert("L").resize((8, 8), Image.BILINEAR), dtype=np.float32)
    return "".join("1" if v > p.mean() else "0" for v in p.flatten())


def capa_de(e):
    """Primeira capa boa entre as fontes da edição, ou None."""
    melhor = None
    for u in fontes_da_capa(e):
        try:
            img, tipo, _ = R.tratar(R.baixar(u, tentativas=1))
        except Exception:  # noqa: BLE001
            continue
        if np.asarray(img.convert("L"), dtype=np.float32).std() < 12:
            continue          # "imagem indisponível" das lojas: cinza liso
        if img.height >= 300:
            return u, img
        if melhor is None or img.height > melhor[1].height:
            melhor = (u, img)
    return melhor


# ----------------------------------------------------------------- folhas
def folhas(linhas):
    """linhas: lista de (num, slug, dica, atual_img, [(rotulo, img), ...])."""
    for velho in os.listdir(PASTA):
        if velho.startswith("folha-") and velho.endswith(".jpg"):
            os.remove(os.path.join(PASTA, velho))
    por_folha, cols = 6, 1 + MAX_CAND
    cw, iw, ih, lh = 172, 150, 225, 316
    f_cab, f_txt = R._fonte(15), R._fonte(12)
    total = (len(linhas) + por_folha - 1) // por_folha
    for p in range(total):
        bloco = linhas[p * por_folha:(p + 1) * por_folha]
        folha = Image.new("RGB", (cols * cw + 24, len(bloco) * lh + 50), (250, 247, 242))
        d = ImageDraw.Draw(folha)
        d.text((12, 12), f"Edições brasileiras · folha {p + 1} de {total} · ATUAL = a capa do site hoje",
               fill=(30, 24, 18), font=R._fonte(19))
        for k, (num, slug, dica, atual, cands) in enumerate(bloco):
            y = 46 + k * lh
            d.text((12, y), f"L{num:03d}  {slug[:70]}", fill=(30, 24, 18), font=f_cab)
            if dica:
                d.text((12, y + 18), dica[:110], fill=(138, 90, 36), font=f_txt)
            celulas = [("ATUAL", atual)] + cands
            for c, (rot, img) in enumerate(celulas):
                x = 12 + c * cw
                cel = R._xadrez(iw, ih)
                if img is not None:
                    im = img.convert("RGBA")
                    im.thumbnail((iw, ih))
                    cel.paste(im, ((iw - im.width) // 2, (ih - im.height) // 2), im)
                else:
                    ImageDraw.Draw(cel).text((14, ih // 2 - 8), "sem imagem", fill=(138, 47, 63), font=f_txt)
                folha.paste(cel, (x, y + 40))
                if c == 0:
                    d.rectangle([x, y + 40, x + iw - 1, y + 40 + ih - 1], outline=(44, 95, 138), width=3)
                d.text((x, y + 40 + ih + 4), rot[:24], fill=(44, 95, 138) if c == 0 else (60, 50, 40), font=f_txt)
        folha.save(os.path.join(PASTA, f"folha-{p + 1:02d}.jpg"), "JPEG", quality=80)


# ----------------------------------------------------------------- principal
def main(acervo=os.path.join(R.RAIZ, "acervo.js")):
    os.makedirs(PASTA, exist_ok=True)
    livros = R.ler_acervo(acervo)
    BY = {b["slug"]: b for b in livros}
    res = {}
    if os.path.exists(RESULTADO):
        try:
            res = json.load(open(RESULTADO, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            res = {}
    if res.get("versao") != VERSAO:
        res = {"versao": VERSAO, "livros": {}}
    feitos = res["livros"]

    pedidos = {}
    if os.path.exists(PEDIDOS):
        for linha in open(PEDIDOS, encoding="utf-8"):
            partes = [x.strip() for x in linha.split("|")]
            if len(partes) >= 2 and not partes[0].startswith("#") and partes[0] in BY:
                pedidos[partes[0]] = (partes[1], partes[2] if len(partes) > 2 else autor_base(BY[partes[0]]))

    # livros avulsos (box e coleção não têm edição única para procurar)
    alvos = [b for b in livros if not b.get("parts") and b.get("badge") != "kit"]
    inicio, novos = time.time(), 0
    for b in alvos:
        titulo, autor = pedidos.get(b["slug"], (titulo_base(b), autor_base(b)))
        consulta = f"{titulo} | {autor}"
        if b["slug"] in feitos and feitos[b["slug"]].get("consulta") == consulta:
            continue
        if (time.time() - inicio) / 60 > MINUTOS:
            print("Tempo da passada esgotado: o resto fica para a próxima publicação.")
            break
        print(f"pesquisando {b['slug']}  ({consulta})")
        eds = edicoes(titulo, autor)
        cands, vistas = [], set()
        with ThreadPoolExecutor(max_workers=4) as ex:
            achadas = list(ex.map(capa_de, eds[:MAX_CAND * 2]))
        for e, ac in zip(eds[:MAX_CAND * 2], achadas):
            if not ac or len(cands) >= MAX_CAND:
                continue
            u, img = ac
            sig = assinatura(img)
            if sig in vistas:
                continue
            vistas.add(sig)
            cands.append({"isbn": e["isbn"], "ano": e["ano"], "editora": e["editora"], "url": u})
        feitos[b["slug"]] = {"consulta": consulta, "edicoes": len(eds), "candidatas": cands,
                             "todas": [{k: e[k] for k in ("isbn", "ano", "editora")} for e in eds[:15]]}
        novos += 1
        time.sleep(0.4)

    with open(RESULTADO, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    if not novos and os.path.exists(os.path.join(PASTA, "indice.txt")):
        print("Nada novo para pesquisar.")
        return res

    # folhas e índice: na ordem do acervo
    linhas, txt, num = [], [], 0
    sem = []
    cache_img = {}

    def abre(u):
        if u not in cache_img:
            try:
                cache_img[u] = R.tratar(R.baixar(u, tentativas=1))[0]
            except Exception:  # noqa: BLE001
                cache_img[u] = None
        return cache_img[u]

    def atual_de(b):
        cam = os.path.join(R.PASTA, b["slug"] + "." + R.FORMATO)
        if os.path.exists(cam):
            return Image.open(cam)
        return abre(b["img"]) if b.get("img") else None

    pend = []
    for b in alvos:
        r = feitos.get(b["slug"])
        if not r:
            continue
        if not r["candidatas"]:
            sem.append(b["slug"])
            continue
        num += 1
        pend.append((num, b, r))
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda t: [abre(c["url"]) for c in t[2]["candidatas"]], pend))
    for num, b, r in pend:
        cands = [(f"{i + 1} · {c['ano'] or '?'} · {c['editora'][:12]}", abre(c["url"]))
                 for i, c in enumerate(r["candidatas"])]
        linhas.append((num, b["slug"], dicas(b), atual_de(b), cands))
        txt.append(f"L{num:03d}  {b['slug']}  [{dicas(b)}]\n      ATUAL  {b.get('img', '')}\n"
                   + "".join(f"      {i + 1}  {c['ano'] or '?'}  {c['editora']}  ISBN {c['isbn']}  {c['url']}\n"
                             for i, c in enumerate(r["candidatas"])))
    folhas(linhas)
    with open(os.path.join(PASTA, "indice.txt"), "w", encoding="utf-8") as f:
        f.write("Pesquisa de edições brasileiras (ISBN 978-85 / 978-65), da mais antiga para a mais nova.\n")
        f.write("Cada linha L### corresponde a uma linha das folhas folha-NN.jpg.\n\n")
        f.write("".join(txt))
        f.write(f"\n== sem edição brasileira com capa encontrada ({len(sem)}) ==\n")
        f.write("".join(f"      {s}\n" for s in sem))
    print(f"{novos} livros pesquisados agora · {num} com candidatas · {len(sem)} sem edição brasileira com capa")
    return res


if __name__ == "__main__":
    main(*sys.argv[1:2])
