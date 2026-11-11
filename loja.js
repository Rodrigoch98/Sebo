/* ==========================================================================
   loja.js — estado compartilhado do acervo (Firebase Firestore)

   O acervo tem anúncios sobrepostos: o mesmo exemplar físico pode aparecer
   avulso, dentro da coleção da série e dentro do box do universo. Por isso
   o estoque é controlado por EXEMPLAR FÍSICO (as "folhas"), nunca por
   anúncio. Quando uma folha sai:

     • o anúncio que foi realmente vendido fica marcado como "Vendido";
     • todos os outros anúncios que dependiam daquela folha somem da página.

   Sem Firebase configurado — ou sem internet — nada quebra: a loja entra em
   "modo vitrine" e usa apenas o que está marcado no próprio cadastro.
   ========================================================================== */
"use strict";

const Loja = (function () {

  const CFGL   = window.ACERVO_CFG || {};
  const FBCFG  = CFGL.firebase || null;
  const HORAS  = CFGL.horasReserva || 24;
  const SDK    = 'https://www.gstatic.com/firebasejs/12.19.0/';

  let db = null, auth = null, uid = null, dono = null, fb = null;
  let timerExp = null;

  const S = {
    modo: 'vitrine',        // 'vitrine' | 'online'
    conexao: 'offline',     // offline | conectando | online | erro
    erro: '',
    reservas: {},           // folha -> {anuncio, pedido, uid, ate}   (público: sem nomes)
    vendidos: {},           // folha -> {anuncio, pedido, quando}       (público: sem nomes)
    subs: [],
    prontos: 0
  };

  /* ---------------------------------------------------------------- utils */
  const agora  = () => Date.now();
  const ms     = t => !t ? 0 : (typeof t.toMillis === 'function' ? t.toMillis() : (t.seconds ? t.seconds * 1000 : +t || 0));
  const unico  = a => Array.from(new Set(a));
  const guarda = fn => { try { return fn(); } catch (e) { return undefined; } };

  /* ------------------------------------------------------- folhas do item */
  const memo = new Map();
  function folhas(slug, visto) {
    if (!visto && memo.has(slug)) return memo.get(slug);
    const b = (window.BY || {})[slug];
    if (!b) return [];
    let saida;
    if (!b.parts || !b.parts.length) saida = [slug];
    else {
      const v = visto || new Set();
      if (v.has(slug)) return [];
      v.add(slug);
      const acc = [];
      b.parts.forEach(p => folhas(p, v).forEach(x => acc.push(x)));
      saida = unico(acc);
      if (!saida.length) saida = [slug];
    }
    if (!visto) memo.set(slug, saida);
    return saida;
  }

  /* -------------------------------------------------- situação do anúncio */
  function estado(slug) {
    const b = (window.BY || {})[slug];
    if (!b) return { st: 'fora' };
    if (b.estatico) return { st: 'vendido' };

    const t = agora();
    let vAqui = null, vFora = false, rAqui = null, rFora = false;

    for (const f of folhas(slug)) {
      const v = S.vendidos[f];
      if (v) { if (v.anuncio === slug) vAqui = v; else vFora = true; continue; }
      const r = S.reservas[f];
      if (r && r.ate > t) { if (r.anuncio === slug) rAqui = r; else rFora = true; }
    }
    if (vAqui) return { st: 'vendido', venda: vAqui };
    if (vFora) return { st: 'fora', motivo: 'vendido' };
    if (rAqui) return { st: 'reservado', res: rAqui, meu: !!uid && rAqui.uid === uid };
    if (rFora) return { st: 'fora', motivo: 'reservado' };
    return { st: 'livre' };
  }

  /* ------------------------------------- grava a situação em cada livro   */
  function aplicar() {
    let prox = Infinity;
    (window.BOOKS || []).forEach(b => {
      const e = estado(b.slug);
      b.st   = e.st;
      b.s    = e.st === 'vendido';
      b.fora = e.st === 'fora';
      b.res  = e.res || null;
      b.meu  = !!e.meu;
      if (e.res && e.res.ate > agora()) prox = Math.min(prox, e.res.ate);
    });
    if (timerExp) clearTimeout(timerExp);
    if (prox < Infinity) timerExp = setTimeout(aplicar, Math.max(5000, Math.min(prox - agora() + 1500, 1800000)));
    S.subs.forEach(fn => guarda(() => fn(S)));
  }

  /* ----------------------------------------------------- carregar o SDK   */
  function script(src) {
    return new Promise((ok, falha) => {
      const s = document.createElement('script');
      s.src = src; s.async = false;
      s.onload = ok; s.onerror = () => falha(new Error('falhou ' + src));
      document.head.appendChild(s);
    });
  }

  async function init(opts) {
    opts = opts || {};
    if (opts.onChange) S.subs.push(opts.onChange);
    aplicar();

    if (!FBCFG || !FBCFG.apiKey || /COLE_AQUI/.test(FBCFG.apiKey)) {
      S.modo = 'vitrine'; S.conexao = 'offline';
      S.subs.forEach(fn => guarda(() => fn(S)));
      return S;
    }

    S.conexao = 'conectando';
    S.subs.forEach(fn => guarda(() => fn(S)));

    try {
      await script(SDK + 'firebase-app-compat.js');
      await Promise.all([
        script(SDK + 'firebase-firestore-compat.js'),
        script(SDK + 'firebase-auth-compat.js')
      ]);
      fb   = window.firebase;
      if (!fb.apps.length) fb.initializeApp(FBCFG);
      db   = fb.firestore();
      auth = fb.auth();

      await new Promise(ok => {
        auth.onAuthStateChanged(u => {
          uid  = u ? u.uid : null;
          dono = (u && u.email) ? u.email : null;
          aplicar();
          ok();
        });
        auth.signInAnonymously().catch(e => {
          // login anônimo desligado no console: dá para ler, não dá para reservar
          S.erro = 'anon:' + (e && e.code || '');
          ok();
        });
      });

      db.collection('vendidos').onSnapshot(snap => {
        const m = {};
        snap.forEach(d => { const x = d.data() || {}; m[d.id] = { anuncio: x.anuncio || d.id, pedido: x.pedido || '', quando: ms(x.quando) }; });
        S.vendidos = m; marcarPronto(); aplicar();
      }, erroSnap);

      db.collection('reservas').onSnapshot(snap => {
        const m = {};
        snap.forEach(d => { const x = d.data() || {}; m[d.id] = { anuncio: x.anuncio || d.id, pedido: x.pedido || '', uid: x.uid || '', ate: ms(x.ate) }; });
        S.reservas = m; marcarPronto(); aplicar();
      }, erroSnap);

    } catch (e) {
      S.modo = 'vitrine'; S.conexao = 'erro'; S.erro = String(e && e.message || e);
      S.subs.forEach(fn => guarda(() => fn(S)));
    }
    return S;
  }

  function marcarPronto() {
    S.prontos++;
    if (S.prontos >= 2) { S.modo = 'online'; S.conexao = 'online'; }
  }
  function erroSnap(e) {
    S.modo = 'vitrine'; S.conexao = 'erro';
    S.erro = (e && e.code) === 'permission-denied'
      ? 'As regras do Firestore ainda não liberam a leitura (veja o README).'
      : String(e && e.message || e);
    aplicar();
  }

  /* ============================== COMPRADOR ============================== */

  /* reserva os anúncios escolhidos e devolve o código do pedido */
  async function reservar(slugs, dados) {
    if (S.modo !== 'online') { const e = new Error('offline'); e.tipo = 'offline'; throw e; }
    if (!uid) { const e = new Error('sem login'); e.tipo = 'login'; throw e; }

    const itens = unico(slugs).map(s => (window.BY || {})[s]).filter(Boolean);
    if (!itens.length) { const e = new Error('vazio'); e.tipo = 'vazio'; throw e; }

    const alvos = [];                                   // {folha, anuncio}
    const visto = new Set();
    itens.forEach(b => folhas(b.slug).forEach(f => { if (!visto.has(f)) { visto.add(f); alvos.push({ f: f, anuncio: b.slug }); } }));

    const pedidoRef = db.collection('pedidos').doc();
    const ate       = fb.firestore.Timestamp.fromMillis(agora() + HORAS * 3600000);
    const total     = itens.reduce((s, b) => s + b.v, 0);
    let ocupados    = [];

    await db.runTransaction(async tx => {
      ocupados = [];
      const vs = await Promise.all(alvos.map(a => tx.get(db.collection('vendidos').doc(a.f))));
      const rs = await Promise.all(alvos.map(a => tx.get(db.collection('reservas').doc(a.f))));

      alvos.forEach((a, i) => {
        if (vs[i].exists) { ocupados.push(a.anuncio); return; }
        if (rs[i].exists) {
          const d = rs[i].data() || {};
          if (ms(d.ate) > agora() && d.uid !== uid) ocupados.push(a.anuncio);
        }
      });
      if (ocupados.length) { const e = new Error('ocupado'); e.tipo = 'ocupado'; throw e; }

      tx.set(pedidoRef, {
        uid: uid,
        nome: String(dados.nome || '').slice(0, 60),
        contato: String(dados.contato || '').slice(0, 60),
        itens: itens.map(b => ({ slug: b.slug, t: b.t, v: b.v })),
        total: total,
        status: 'reservado',
        criado: fb.firestore.FieldValue.serverTimestamp(),
        ate: ate
      });
      alvos.forEach(a => tx.set(db.collection('reservas').doc(a.f), {
        anuncio: a.anuncio,
        pedido: pedidoRef.id,
        uid: uid,
        criado: fb.firestore.FieldValue.serverTimestamp(),
        ate: ate
      }));
    }).catch(e => {
      if (e && e.tipo === 'ocupado') { e.itens = unico(ocupados); throw e; }
      if (e && e.code === 'permission-denied') { const x = new Error('regras'); x.tipo = 'regras'; throw x; }
      throw e;
    });

    const meus = guarda(() => JSON.parse(localStorage.getItem('acv_pedidos') || '[]')) || [];
    meus.unshift({ id: pedidoRef.id, quando: agora(), total: total, n: itens.length });
    guarda(() => localStorage.setItem('acv_pedidos', JSON.stringify(meus.slice(0, 20))));

    return { id: pedidoRef.id, total: total, itens: itens, ate: agora() + HORAS * 3600000 };
  }

  /* o próprio comprador desiste */
  async function desistir(pedidoId) {
    if (S.modo !== 'online') return;
    const lote = db.batch();
    Object.keys(S.reservas).forEach(f => {
      if (S.reservas[f].pedido === pedidoId && S.reservas[f].uid === uid) lote.delete(db.collection('reservas').doc(f));
    });
    await lote.commit();
    await db.collection('pedidos').doc(pedidoId).update({ status: 'cancelado' }).catch(() => {});
  }

  function meusPedidos() { return guarda(() => JSON.parse(localStorage.getItem('acv_pedidos') || '[]')) || []; }

  /* ================================= DONO ================================ */

  async function entrar(email, senha) {
    if (!auth) throw new Error('Firebase não carregou.');
    const c = await auth.signInWithEmailAndPassword(email, senha);
    return c.user;
  }
  async function sair() { if (auth) { await auth.signOut(); await auth.signInAnonymously().catch(() => {}); } }
  function souDono() { return !!dono && dono.toLowerCase() === String(CFGL.dono || '').toLowerCase(); }
  function emailAtual() { return dono; }

  function ouvirPedidos(cb) {
    if (!db) return () => {};
    return db.collection('pedidos').orderBy('criado', 'desc').limit(300)
      .onSnapshot(snap => {
        const out = [];
        snap.forEach(d => { const x = d.data() || {}; out.push(Object.assign({ id: d.id }, x, { criadoMs: ms(x.criado), ateMs: ms(x.ate) })); });
        cb(out, null);
      }, e => cb([], e));
  }

  /* confirma a venda: as folhas do pedido saem do estoque de vez */
  async function confirmar(pedidoId) {
    const snap = await db.collection('pedidos').doc(pedidoId).get();
    if (!snap.exists) throw new Error('Pedido não encontrado.');
    const p = snap.data();
    const lote = db.batch();
    const visto = new Set();
    (p.itens || []).forEach(it => folhas(it.slug).forEach(f => {
      if (visto.has(f)) return; visto.add(f);
      lote.set(db.collection('vendidos').doc(f), {
        anuncio: it.slug, pedido: pedidoId,
        quando: fb.firestore.FieldValue.serverTimestamp()
      });
      lote.delete(db.collection('reservas').doc(f));
    }));
    lote.update(db.collection('pedidos').doc(pedidoId), { status: 'vendido', fechado: fb.firestore.FieldValue.serverTimestamp() });
    await lote.commit();
  }

  /* libera a reserva e devolve tudo para a vitrine */
  async function liberar(pedidoId) {
    const lote = db.batch();
    Object.keys(S.reservas).forEach(f => { if (S.reservas[f].pedido === pedidoId) lote.delete(db.collection('reservas').doc(f)); });
    lote.update(db.collection('pedidos').doc(pedidoId), { status: 'cancelado' });
    await lote.commit();
  }

  /* venda feita fora do site: registra um pedido já fechado e dá a baixa */
  async function marcarVendido(slug, nome) {
    const b = (window.BY || {})[slug] || { t: slug, v: 0 };
    const ped = db.collection('pedidos').doc();
    const lote = db.batch();
    lote.set(ped, {
      uid: uid, nome: String(nome || '').slice(0, 60), contato: '',
      itens: [{ slug: slug, t: b.t, v: b.v }], total: b.v,
      status: 'vendido', origem: 'manual',
      criado: fb.firestore.FieldValue.serverTimestamp(),
      fechado: fb.firestore.FieldValue.serverTimestamp()
    });
    folhas(slug).forEach(f => {
      lote.set(db.collection('vendidos').doc(f), {
        anuncio: slug, pedido: ped.id,
        quando: fb.firestore.FieldValue.serverTimestamp()
      });
      lote.delete(db.collection('reservas').doc(f));
    });
    await lote.commit();
  }

  /* volta para a vitrine — desfaz a venda/reserva INTEIRA que prendeu este
     anúncio, senão o resto do conjunto continuaria fora sem explicação */
  async function marcarLivre(slug) {
    const alvo = new Set();
    const abrir = s => folhas(s).forEach(f => alvo.add(f));
    abrir(slug);
    folhas(slug).forEach(f => {
      const v = S.vendidos[f]; if (v && v.anuncio) abrir(v.anuncio);
      const r = S.reservas[f]; if (r && r.anuncio) abrir(r.anuncio);
    });
    const lote = db.batch();
    alvo.forEach(f => { lote.delete(db.collection('vendidos').doc(f)); lote.delete(db.collection('reservas').doc(f)); });
    await lote.commit();
  }

  /* ------------------------------------------------------------ resumo    */
  function numeros() {
    const L = (window.BOOKS || []);
    const disp = L.filter(b => b.st === 'livre');
    const vend = L.filter(b => b.st === 'vendido');
    const resv = L.filter(b => b.st === 'reservado');
    return {
      disponiveis: disp.length,
      vendidos: vend.length,
      reservados: resv.length,
      ocultos: L.filter(b => b.st === 'fora').length,
      emCaixa: vend.reduce((s, b) => s + b.v, 0),
      naVitrine: disp.reduce((s, b) => s + b.v, 0)
    };
  }

  return {
    S: S, init: init, estado: estado, folhas: folhas, aplicar: aplicar, numeros: numeros,
    reservar: reservar, desistir: desistir, meusPedidos: meusPedidos,
    entrar: entrar, sair: sair, souDono: souDono, emailAtual: emailAtual,
    ouvirPedidos: ouvirPedidos, confirmar: confirmar, liberar: liberar,
    marcarVendido: marcarVendido, marcarLivre: marcarLivre,
    get modo() { return S.modo; },
    get conexao() { return S.conexao; },
    get uid() { return uid; },
    assinar(fn) { S.subs.push(fn); }
  };
})();
window.Loja = Loja;
