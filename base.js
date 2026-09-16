/* ==========================================================================
   base.js — o que as páginas têm em comum: configuração, atalhos,
   formatação, o catálogo em memória e o sistema de capas.

   MUDANÇA IMPORTANTE (set/2026)
   O site NÃO consulta mais nenhuma API de capas em tempo real. Antes ele
   perguntava ao Google Books e à Open Library a cada card, e isso causava os
   dois defeitos que apareciam na tela:

     1. capa que não carregava — a cota diária do Google estourava, a resposta
        vinha 429 e o card ficava sem foto;
     2. capa de edição estrangeira — a busca casava pelo título, sem saber que
        edição era, e trazia a capa americana no lugar da brasileira.

   Agora a capa vem SÓ do que está escrito no cadastro. A cascata é:

     1. campo `img` do anúncio (URL fixa, escolhida e conferida por você)
     2. montagem das capas dos volumes, quando o anúncio é uma coleção `parts`
     3. capa desenhada na hora a partir de título, autor e saga

   Nenhuma dessas etapas depende de serviço de terceiros respondendo bem, e
   nenhuma pode trazer a capa de outro livro.
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
  revisar: !!b.revisar,        // capa achada automaticamente, edição a conferir
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
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  del(k) { try { localStorage.removeItem(k); } catch (e) {} }
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
   CAPAS
   ================================================================== */
const Cover = {

  /* Diário de carregamento. Guarda quais URLs do cadastro carregaram e
     quais falharam NESTE navegador, que é o único lugar onde dá para
     saber isso de verdade. A página capas.html lê daqui para montar o
     relatório do que precisa ser trocado. */
  log: { ok: {}, erro: {} },

  iniciado: false,
  inicia() {
    if (this.iniciado) return;
    this.iniciado = true;
    /* limpa o cache da busca antiga: ele guardava URLs do Google Books,
       inclusive de edição estrangeira, e voltaria a aparecer sem isso */
    St.del('acv_covers3'); St.del('acv_bad3');
    St.del('acv_covers2'); St.del('acv_bad2');
    St.del('acv_covers'); St.del('acv_bad');
    this.log = St.get('acv_capas_log', { ok: {}, erro: {} });
    if (!this.log || typeof this.log !== 'object') this.log = { ok: {}, erro: {} };
    this.log.ok = this.log.ok || {}; this.log.erro = this.log.erro || {};
  },
  anota(slug, url, deu) {
    this.inicia();
    if (deu) { this.log.ok[slug] = url; delete this.log.erro[slug]; }
    else { this.log.erro[slug] = url; delete this.log.ok[slug]; }
    clearTimeout(this._gv);
    this._gv = setTimeout(() => St.set('acv_capas_log', this.log), 400);
  },
  /* usado por capas.html */
  relatorio() {
    this.inicia();
    return {
      ok: Object.keys(this.log.ok).length,
      erro: Object.keys(this.log.erro),
      erroUrl: Object.assign({}, this.log.erro)
    };
  },
  limpaLog() { this.log = { ok: {}, erro: {} }; St.set('acv_capas_log', this.log); },

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
     Coleção montada por você não existe como produto em lugar nenhum,
     então não há foto de caixa para procurar. A capa dela é a montagem
     das capas dos próprios volumes: mostra exatamente o que vai junto
     e acompanha sozinha qualquer capa que você preencher depois.
     --------------------------------------------------------------- */
  membros(b, limite) {
    const vistos = new Set();
    const saida = [];
    const anda = slug => {
      if (saida.length >= (limite || 3) || vistos.has(slug)) return;
      vistos.add(slug);
      const x = BY[slug];
      if (!x) return;
      if (x.parts && x.parts.length) { x.parts.forEach(anda); return; }
      saida.push(x);
    };
    (b.parts || []).forEach(anda);
    return saida;
  },

  montagem(slot, b, eager) {
    const vols = this.membros(b, 3);
    if (vols.length < 2) return false;

    /* estilo aplicado em linha e com !important: assim a montagem se encaixa
       em qualquer slot das quatro páginas sem depender do CSS de cada uma */
    const st = (el, css) => { for (const k in css) el.style.setProperty(k, css[k], 'important'); };
    const [dark, mid, light] = this.palette(b);

    const caixa = document.createElement('div');
    caixa.className = 'gen';
    st(caixa, {
      position: 'absolute', inset: '0', width: '100%', height: '100%',
      display: 'block', overflow: 'hidden', opacity: '0', transition: 'opacity .35s',
      /* fundo escurecido de propósito: é o que faz as capas dos volumes
         saltarem, já que elas costumam repetir a cor da própria saga */
      background: 'linear-gradient(rgba(0,0,0,.52),rgba(0,0,0,.3)),'
                + 'linear-gradient(140deg,' + dark + ',' + mid + ')'
    });

    /* leque centralizado: o volume 1 fica na frente, os outros abrem para os lados */
    const poses = vols.length === 2
      ? [{ l: 3, w: 62, r: -7, dy: 0, z: 2 }, { l: 35, w: 62, r: 7, dy: 0, z: 1 }]
      : [{ l: 0, w: 58, r: -11, dy: 3, z: 1 }, { l: 19, w: 64, r: 0, dy: -2, z: 3 }, { l: 42, w: 58, r: 11, dy: 3, z: 2 }];
    const ordem = vols.length === 3 ? [vols[1], vols[0], vols[2]] : vols;
    const pose = vols.length === 3 ? [poses[1], poses[0], poses[2]] : poses;

    ordem.forEach((v, i) => {
      const p = pose[i];
      const im = document.createElement('img');
      im.alt = '';
      im.decoding = 'async';
      im.loading = eager ? 'eager' : 'lazy';
      st(im, {
        position: 'absolute', left: p.l + '%', top: '50%', width: p.w + '%',
        height: 'auto', 'aspect-ratio': '2 / 3', 'object-fit': 'cover',
        'z-index': String(p.z),
        transform: 'translateY(calc(-50% + ' + p.dy + '%)) rotate(' + p.r + 'deg)',
        'border-radius': '3px', 'box-shadow': '0 8px 20px rgba(0,0,0,.42)', opacity: '1'
      });
      /* a capa desenhada do volume é o ponto de partida; a real entra por cima */
      im.src = this.generated(v);
      if (v.img) {
        const real = new Image();
        real.onload = () => { if (real.naturalWidth >= 40) im.src = v.img; };
        real.src = v.img;
      }
      caixa.appendChild(im);
    });

    const n = b.setOf || this.membros(b, 99).length;
    if (n > 1) {
      const tag = document.createElement('span');
      tag.textContent = n + ' volumes';
      st(tag, {
        position: 'absolute', left: '50%', bottom: '5%', 'z-index': '5',
        transform: 'translateX(-50%)', 'white-space': 'nowrap',
        background: 'rgba(12,9,6,.72)', color: light, 'border-radius': '999px',
        padding: '3px 11px', font: '700 11px/1.5 system-ui,-apple-system,sans-serif',
        'letter-spacing': '.04em', 'backdrop-filter': 'blur(4px)'
      });
      caixa.appendChild(tag);
    }

    slot.appendChild(caixa);
    requestAnimationFrame(() => caixa.style.setProperty('opacity', '1', 'important'));
    return true;
  },

  /* ---------------------------------------------------------------
     Pinta o slot. A capa desenhada entra SEMPRE, na hora, e é ela que
     garante que nenhum card fique girando. Quando existe URL fixa, a
     foto real entra por cima assim que carrega.

     Se a URL falhar, o card FICA na capa desenhada e o slug vai para o
     relatório. O que ele nunca faz é sair procurando outra imagem: era
     exatamente aí que entrava a capa da edição estrangeira.
     --------------------------------------------------------------- */
  paint(slot, b, eager) {
    if (!slot || !b) return;
    if (slot.dataset.done) return;
    slot.dataset.done = '1';
    this.inicia();

    const sk = slot.querySelector('.sk');
    if (sk) sk.remove();

    /* 2) coleção montada por você, sem URL própria: montagem dos volumes */
    if (!b.img && b.parts && b.parts.length && this.montagem(slot, b, eager)) return;

    /* 3) piso: capa desenhada, imediata */
    const base = document.createElement('img');
    base.className = 'gen';
    base.alt = 'Capa ilustrativa: ' + b.t;
    base.src = this.generated(b);
    base.decoding = 'async';
    slot.appendChild(base);
    requestAnimationFrame(() => base.classList.add('in'));

    /* 1) URL fixa do cadastro, quando existe */
    if (!b.img) return;

    const url = b.img;
    const im = new Image();
    let desistiu = false;
    const prazo = setTimeout(() => { desistiu = true; this.anota(b.slug, url, false); }, 12000);

    im.decoding = 'async';
    im.loading = eager ? 'eager' : 'lazy';
    im.alt = 'Capa: ' + b.t;
    im.onload = () => {
      clearTimeout(prazo);
      if (desistiu) return;
      if (im.naturalWidth < 40) { this.anota(b.slug, url, false); return; }
      this.anota(b.slug, url, true);
      if (!slot.isConnected) return;
      slot.querySelectorAll('img,.gen').forEach(x => x.remove());
      slot.appendChild(im);
      requestAnimationFrame(() => im.classList.add('in'));
    };
    im.onerror = () => {
      clearTimeout(prazo);
      this.anota(b.slug, url, false);   // fica a capa desenhada, e nada mais
    };
    im.src = url;
  }
};

window.Cover = Cover;
window.CFG = CFG;
