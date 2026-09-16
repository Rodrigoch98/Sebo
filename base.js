/* ==========================================================================
   base.js — o que as quatro páginas têm em comum: configuração, atalhos,
   formatação, o catálogo em memória e o sistema de capas em cascata.
   ========================================================================== */
"use strict";

const CFG = Object.assign({}, window.ACERVO_CFG);
CFG.catalogUrl = new URL(CFG.catalogoUrl || 'index.html', location.href).href;

const RAW = window.ACERVO_RAW || [];

/* Cada livro carrega a situação ao vivo (st/s/fora), que a Loja atualiza. */
const BOOKS = RAW.map(b => ({
  slug: b.slug, t: b.t, titleMain: b.tm, author: b.a || "", g: b.g || [],
  v: b.v, op: b.op || 0, cond: b.cond, q: b.q, d: b.d, sg: b.sg || "",
  badge: b.badge || "", img: b.img || "", setOf: b.setOf || 0,
  parts: b.parts || [],        // anúncios que esta coleção cobre
  estatico: !!b.s,             // vendido direto no cadastro
  s: !!b.s,                    // vendido (ao vivo)
  fora: false,                 // sumiu porque um anúncio sobreposto saiu
  st: b.s ? 'vendido' : 'livre',
  res: null, meu: false
}));

const BY = {};
BOOKS.forEach(b => { BY[b.slug] = b; });
window.BOOKS = BOOKS; window.BY = BY;

/* à venda agora: nem vendido, nem preso por um anúncio sobreposto */
const aVenda = b => !b.s && !b.fora;

/* ---------- storage seguro ---------- */
const St = {
  get(k, fb) { try { const v = localStorage.getItem(k); return v == null ? fb : JSON.parse(v); } catch (e) { return fb; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
};

/* ---------- helpers ---------- */
const $ = (s, c) => (c || document).querySelector(s);
const $$ = (s, c) => Array.from((c || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const money = n => 'R$ ' + Number(n).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const money2 = n => 'R$ ' + Number(n).toFixed(2).replace('.', ',');
const icon = (id, sz) => `<svg width="${sz || 16}" height="${sz || 16}"><use href="#${id}"/></svg>`;
const offOf = b => (b.op && b.op > b.v) ? Math.round((b.op - b.v) / b.op * 100) : 0;

const COND = {
  novo: { t: 'Como novo', c: 'novo' },
  otimo: { t: 'Ótimo estado', c: '' },
  bom: { t: 'Bom estado', c: '' }
};

/* ==================================================================
   CAPAS — resolução em cascata, nunca quebra
   1) URL curada no cadastro   2) cache local   3) Google Books
   4) Open Library             5) capa desenhada em SVG
   ================================================================== */
const Cover = {
  cache: St.get('acv_covers3', {}),
  bad: St.get('acv_bad3', {}),
  inflight: new Map(),

  save() { St.set('acv_covers3', this.cache); St.set('acv_bad3', this.bad); },

  /* paleta determinística a partir do texto */
  hash(s) { let h = 0; for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; } return Math.abs(h); },

  palette(b) {
    const sets = [
      ['#1e3a5f', '#2c5f8a', '#e8d5a8'], ['#4a1d2e', '#8a2f3f', '#f0d8c0'],
      ['#1f3d2f', '#2b7a55', '#e5e8c8'], ['#3d2a17', '#8a5a24', '#f2dfbb'],
      ['#2a2340', '#584a8a', '#ded8f0'], ['#42281c', '#8a4a2f', '#f5ddc8'],
      ['#14323a', '#2a6b75', '#d8ecec'], ['#3a1f2c', '#7a3050', '#f2d4e0'],
      ['#2e2e14', '#6b6b28', '#ecebc8'], ['#1a2438', '#3d5a80', '#dbe6f0']
    ];
    return sets[this.hash(b.sg || b.author || b.t) % sets.length];
  },

  /* capa desenhada: sempre funciona, mesmo offline */
  generated(b) {
    const [dark, mid, light] = this.palette(b);
    const seed = this.hash(b.t);
    const title = (b.titleMain || b.t).replace(/\s*\([^)]*\)\s*/g, '').trim();
    const words = title.split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
      if ((cur + ' ' + w).trim().length > 15 && cur) { lines.push(cur); cur = w; }
      else cur = (cur + ' ' + w).trim();
      if (lines.length >= 4) break;
    }
    if (cur && lines.length < 5) lines.push(cur);
    const shown = lines.slice(0, 5);
    const fs = shown.length > 3 ? 25 : shown.length > 2 ? 29 : 33;
    const startY = 168 - (shown.length - 1) * (fs * 0.62);
    const tspans = shown.map((l, i) =>
      `<text x="150" y="${startY + i * fs * 1.22}" font-family="Georgia,serif" font-size="${fs}" font-weight="700" fill="${light}" text-anchor="middle">${esc(l)}</text>`
    ).join('');
    const author = (b.author || '').split(/\s+e\s+|,/)[0].slice(0, 26);
    const saga = (b.sg || '').slice(0, 28);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 450" width="300" height="450">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="${dark}"/><stop offset="1" stop-color="${mid}"/></linearGradient>
<linearGradient id="sp" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="rgba(0,0,0,.45)"/><stop offset="1" stop-color="rgba(0,0,0,0)"/></linearGradient></defs>
<rect width="300" height="450" fill="url(#g)"/>
<circle cx="${40 + seed % 180}" cy="${330 + seed % 70}" r="${80 + seed % 60}" fill="${light}" opacity=".05"/>
<circle cx="${210 - seed % 120}" cy="${70 + seed % 40}" r="${50 + seed % 40}" fill="${light}" opacity=".045"/>
<rect x="0" y="0" width="15" height="450" fill="url(#sp)"/>
<rect x="26" y="26" width="248" height="398" fill="none" stroke="${light}" stroke-opacity=".28" stroke-width="1"/>
<rect x="31" y="31" width="238" height="388" fill="none" stroke="${light}" stroke-opacity=".13" stroke-width="1"/>
<path d="M150 74 l5 11 12 1.6 -8.7 8.4 2.1 12.1 -10.4-5.7 -10.4 5.7 2.1-12.1 -8.7-8.4 12-1.6z" fill="${light}" opacity=".5"/>
${tspans}
<line x1="105" y1="${startY + shown.length * fs * 1.22 + 8}" x2="195" y2="${startY + shown.length * fs * 1.22 + 8}" stroke="${light}" stroke-opacity=".4" stroke-width="1.2"/>
${author ? `<text x="150" y="${startY + shown.length * fs * 1.22 + 34}" font-family="Helvetica,Arial,sans-serif" font-size="15" fill="${light}" fill-opacity=".8" text-anchor="middle" letter-spacing="1.2">${esc(author.toUpperCase())}</text>` : ''}
${saga ? `<text x="150" y="404" font-family="Helvetica,Arial,sans-serif" font-size="10.5" fill="${light}" fill-opacity=".55" text-anchor="middle" letter-spacing="1.8">${esc(saga.toUpperCase())}</text>` : ''}
</svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  },

  /* ---------------------------------------------------------------
     Busca online. Regras aprendidas na marra:
     - no máximo 3 buscas ao mesmo tempo (o Google corta em 429
       quando a página abre 60 cards de uma vez);
     - toda busca tem prazo; nada pode ficar pendurado;
     - depois de 4 recusas seguidas do Google, para de insistir
       nele pelo resto da visita e vai direto para a Open Library.
     --------------------------------------------------------------- */
  fila: [], ativos: 0, MAX: 3, falhasGoogle: 0, googleFora: false,

  naFila(fn) {
    return new Promise(resolve => {
      this.fila.push({ fn, resolve });
      this.roda();
    });
  },
  roda() {
    while (this.ativos < this.MAX && this.fila.length) {
      const t = this.fila.shift();
      this.ativos++;
      Promise.resolve().then(t.fn).catch(() => null).then(v => {
        this.ativos--; t.resolve(v); this.roda();
      });
    }
  },

  /* fetch que desiste sozinho */
  async pega(url, ms) {
    const ac = ('AbortController' in window) ? new AbortController() : null;
    const t = setTimeout(() => ac && ac.abort(), ms || 7000);
    try {
      const r = await fetch(url, ac ? { signal: ac.signal } : undefined);
      clearTimeout(t);
      return r;
    } catch (e) { clearTimeout(t); return null; }
  },

  async lookup(b) {
    const key = b.slug;
    if (this.cache[key]) return this.cache[key];
    if (this.bad[key]) return null;
    if (this.inflight.has(key)) return this.inflight.get(key);

    const job = this.naFila(async () => {
      const q = encodeURIComponent(b.q || b.t);

      if (!this.googleFora) {
        const r = await this.pega(`https://www.googleapis.com/books/v1/volumes?q=${q}&maxResults=5&langRestrict=pt&country=BR`);
        if (r && r.status === 429) {
          if (++this.falhasGoogle >= 4) this.googleFora = true;
        } else if (r && r.ok) {
          this.falhasGoogle = 0;
          const d = await r.json().catch(() => null);
          if (d) {
            const want = norm(b.titleMain || b.t).split(/\s+/).filter(w => w.length > 3);
            let best = null;
            for (const it of (d.items || [])) {
              const li = it.volumeInfo && it.volumeInfo.imageLinks;
              if (!li) continue;
              const tt = norm(it.volumeInfo.title || '');
              const score = want.filter(w => tt.includes(w)).length;
              if (!best || score > best.s) best = { s: score, li };
              if (score >= Math.min(2, want.length)) break;
            }
            /* casamento fraco vira capa desenhada: melhor nenhuma capa
               do que a capa de outro livro */
            if (best && best.s >= Math.min(2, want.length)) {
              const u = (best.li.thumbnail || best.li.smallThumbnail)
                .replace(/^http:/, 'https:').replace('&edge=curl', '').replace('&zoom=1', '&zoom=2');
              this.cache[key] = u; this.save(); return u;
            }
          }
        } else if (++this.falhasGoogle >= 4) this.googleFora = true;
      }

      const r2 = await this.pega(`https://openlibrary.org/search.json?q=${q}&limit=3&fields=cover_i,title`);
      if (r2 && r2.ok) {
        const d = await r2.json().catch(() => null);
        const hit = d && (d.docs || []).find(x => x.cover_i);
        if (hit) {
          const u = `https://covers.openlibrary.org/b/id/${hit.cover_i}-L.jpg`;
          this.cache[key] = u; this.save(); return u;
        }
      }
      this.bad[key] = 1; this.save(); return null;
    });

    this.inflight.set(key, job);
    const out = await job;
    this.inflight.delete(key);
    return out;
  },

  /* Pinta o slot. A capa desenhada entra SEMPRE, na hora — é ela que
     garante que nenhum card fique girando para sempre. A capa real,
     quando chega e carrega, entra por cima. */
  paint(slot, b, eager) {
    if (slot.dataset.done) return;
    slot.dataset.done = '1';

    const sk = slot.querySelector('.sk');
    if (sk) sk.remove();
    const base = document.createElement('img');
    base.className = 'gen'; base.alt = 'Capa ilustrativa: ' + b.t;
    base.src = this.generated(b); base.decoding = 'async';
    slot.appendChild(base);
    requestAnimationFrame(() => base.classList.add('in'));

    const show = url => {
      if (!url) return;
      const im = new Image();
      let morreu = false;
      const desiste = () => { morreu = true; };
      const prazo = setTimeout(desiste, 9000);   // imagem que não chega em 9s fica para trás
      im.decoding = 'async';
      im.loading = eager ? 'eager' : 'lazy';
      im.alt = 'Capa: ' + b.t;
      im.onload = () => {
        clearTimeout(prazo);
        if (morreu || im.naturalWidth < 40) return;
        slot.querySelectorAll('img').forEach(x => x.remove());
        slot.appendChild(im);
        requestAnimationFrame(() => im.classList.add('in'));
      };
      im.onerror = () => {
        clearTimeout(prazo);
        if (this.cache[b.slug] === url) { delete this.cache[b.slug]; this.save(); }
        if (!b.img || b.img !== url) return;
        this.lookup(b).then(u2 => { if (u2 && u2 !== url) show(u2); });
      };
      im.src = url;
    };

    const curada = b.img || this.cache[b.slug];
    if (curada) show(curada);
    else this.lookup(b).then(show);
  }
};
