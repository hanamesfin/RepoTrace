"use strict";
// The Obsidian-style explorer, ported from the first prototype. It runs inside the app (in a frame) and talks to it with messages:
// the app sends the project data; this page sends back "open the reading view", "open the full review", its state (so Back restores it) and "Esc with nothing left to undo".
const TARGET = location.protocol === 'file:' ? '*' : location.origin;
const emit = msg => { try { window.parent.postMessage(msg, TARGET); } catch (e) { /* standalone: nobody to tell */ } };
let started = false;
function boot(INIT) {
const D = INIT.data;
const $ = s => document.querySelector(s);
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, ''); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) { if (kid == null || kid === false) continue; e.append(kid.nodeType ? kid : document.createTextNode(String(kid))); }
  return e;
}
const fill = (el, ...parts) => el.replaceChildren(...parts.flat(Infinity).filter(x => x != null && x !== false));
const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '–';
const PALETTE = ['#7aa2ff', '#5fd39a', '#e8b45a', '#d98cff', '#ff8f7a', '#4fd1d9', '#c4d65a', '#ff7fb0', '#9ab0c8', '#f0a35e', '#8ee0a8', '#b7a0ff'];

/* ------------------------------------------------------------ state */
const S = {mode: 'explore', lens: 'physical', open: new Set(), trail: [], selected: null, hover: null, force: new Set(), ask: null,
  review: null, rsel: null, rfocus: null, rnode: null, rcode: false, limitsOpen: false,
  show: {sure: true, maybe: true, tests: false}, view: {x: 0, y: 0, k: 1}, alpha: 1, pos: new Map(), drag: null, vis: [], visOf: new Map(), edges: [], deg: new Map()};

/* ------------------------------------------------------------ one graph = one version of the project */
let G, GK, N, kids, roots, outL, inL, relOut, relIn, DOCS;
function normalise(g) {
  if (g._normalised) return; g._normalised = true;
  g.links = g.links.map(l => l.length >= 5 ? [l[0], l[1], l[4] === 1 ? 2 : l[2], l[3]] : l);
  g.rel = g.rel || []; g.concepts = g.concepts || []; g.concept_of = g.concept_of || g.nodes.map(() => -1);
}
function load(key) {
  if (GK === key) return false;
  GK = key; G = D.graphs[key]; normalise(G); N = G.nodes;
  kids = N.map(() => []); roots = [];
  N.forEach(n => (n.p == null ? roots : kids[n.p]).push(n.i));
  outL = N.map(() => []); inL = N.map(() => []);
  for (const [a, b, tier, n] of G.links) { outL[a].push({id: b, tier, n}); inL[b].push({id: a, tier, n}); }
  relOut = N.map(() => []); relIn = N.map(() => []);
  for (const [a, b, kind] of G.rel) { relOut[a].push({id: b, kind}); relIn[b].push({id: a, kind}); }
  DOCS = null;
  Object.assign(S, {open: new Set(), trail: [], selected: null, hover: null, force: new Set(), ask: null, pos: new Map(), alpha: 1});
  $('#ver').replaceChildren('Showing: ', h('b', null, G.version));
  return true;
}
const ancestors = i => { const out = []; for (let p = N[i].p; p != null; p = N[p].p) out.push(p); return out; };
const dirOf = i => { let p = i; while (N[p].k !== 'dir') p = N[p].p; return p; };
const fileOf = i => { let p = i; while (N[p].k !== 'file' && N[p].k !== 'dir') p = N[p].p; return p; };
const label = i => N[i].k === 'fn' ? N[i].q + '()' : N[i].k === 'file' ? N[i].n : N[i].q;
const kindWord = n => (n.gone ? 'removed ' : '') + ({dir: 'folder', file: 'file', class: 'class', fn: n.p != null && N[n.p].k === 'class' ? 'method' : 'function'})[n.k];
const isTestNode = i => N[i].k === 'dir' ? kids[i].length > 0 && kids[i].every(isTestNode) : N[i].test;
const isContainer = i => kids[i].length > 0;
const neighbourIds = i => [...new Set([...outL[i].map(e => e.id), ...inL[i].map(e => e.id)])].filter(x => x !== i);
const groupOf = i => S.lens === 'conceptual' ? G.concept_of[i] : dirOf(i);
const colorOf = i => { if (N[i].gone) return '#c08cff'; const g = groupOf(i); return g < 0 ? '#8a94a6' : PALETTE[g % PALETTE.length]; };

function computeVisible() {
  const hits = new Set(S.force), anc = new Set();
  for (const i of hits) ancestors(i).forEach(a => anc.add(a));
  const all = new Set([...hits, ...anc]), out = [];
  const hidden = i => isTestNode(i) && !S.show.tests && !all.has(i);
  const walk = i => {
    if (hidden(i)) return;
    const byForce = anc.has(i) && !S.open.has(i);           // opened only to reach something: show just the way there
    if (kids[i].length && (S.open.has(i) || byForce)) kids[i].forEach(c => { if (!byForce || all.has(c)) walk(c); });
    else out.push(i);
  };
  roots.forEach(walk);
  S.vis = out; S.visOf = new Map();
  const mark = (v, i) => { S.visOf.set(i, v); kids[i].forEach(c => mark(v, c)); };
  out.forEach(v => mark(v, v));
  const agg = new Map(), add = (a, b, f) => {
    const va = S.visOf.get(a), vb = S.visOf.get(b);
    if (va == null || vb == null || va === vb) return;
    const key = va + '>' + vb, e = agg.get(key) || {a: va, b: vb, sure: 0, maybe: 0, before: 0, kind: 0};
    f(e); agg.set(key, e);
  };
  for (const [a, b, tier, n] of G.links) add(a, b, e => {               // the filters decide what an arrow is made of
    if (tier === 0) { if (S.show.sure) e.sure += n; } else if (tier === 1) { if (S.show.maybe) e.maybe += n; } else e.before += n;
  });
  for (const [a, b, kind] of G.rel) add(a, b, e => { e.kind = 1 + kind; });
  S.edges = [...agg.values()].filter(e => e.kind || e.sure || e.maybe || e.before);
  S.deg = new Map();
  for (const e of S.edges) for (const x of [e.a, e.b]) S.deg.set(x, (S.deg.get(x) || 0) + 1);
}
// Recompute what is visible; each new dot starts where its folder was, or where its contents were.
function update() {
  const old = S.pos;
  computeVisible();
  const next = new Map(), jitter = (p, r) => ({x: p.x + (Math.random() - .5) * r, y: p.y + (Math.random() - .5) * r, vx: 0, vy: 0});
  for (const v of S.vis) {
    if (old.has(v)) { next.set(v, old.get(v)); continue; }
    const a = ancestors(v).find(x => old.has(x));
    if (a != null) { next.set(v, jitter(old.get(a), 70)); continue; }
    const inside = [...old.keys()].filter(k => N[k] && ancestors(k).includes(v)).map(k => old.get(k));
    if (inside.length) { next.set(v, {x: inside.reduce((s, p) => s + p.x, 0) / inside.length, y: inside.reduce((s, p) => s + p.y, 0) / inside.length, vx: 0, vy: 0}); continue; }
    next.set(v, jitter({x: 0, y: 0}, 500));
  }
  S.pos = next; S.alpha = Math.max(S.alpha, 0.8); redraw = true;
  paintSide();
}
const radius = i => {
  const n = N[i], d = S.deg.get(i) || 0;
  if (n.k === 'dir') return 16 + Math.sqrt(kids[i].length) * 3.5;
  if (n.k === 'file') return 8 + Math.min(10, Math.sqrt(n.lines || 20) / 2.4) + Math.min(5, d * .4);
  if (n.k === 'class') return 8 + Math.min(7, d * .5);
  return 5 + Math.min(6, d * .6);
};

/* ------------------------------------------------------------ layout: a small force simulation */
function tick() {
  const nodes = S.vis, n = nodes.length;
  if (S.alpha < 0.012 && !S.drag) return false;
  const a = S.alpha, P = nodes.map(i => S.pos.get(i)), R = nodes.map(radius);
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const dx = P[j].x - P[i].x, dy = P[j].y - P[i].y, d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
    const minD = R[i] + R[j] + 16;
    let f = 0;
    if (d2 < 160000) f = a * 1500 * (R[i] + R[j]) / (d2 + 600);
    if (d < minD) f += (minD - d) * 0.35;
    const fx = dx / d * f, fy = dy / d * f;
    P[i].vx -= fx; P[i].vy -= fy; P[j].vx += fx; P[j].vy += fy;
  }
  const idx = new Map(nodes.map((v, k) => [v, k]));
  for (const e of S.edges) {
    const i = idx.get(e.a), j = idx.get(e.b); if (i == null || j == null) continue;
    const dx = P[j].x - P[i].x, dy = P[j].y - P[i].y, d = Math.sqrt(dx * dx + dy * dy) + 0.01;
    const L = 70 + R[i] + R[j], w = Math.min(1.4, 0.5 + Math.log2(1 + e.sure + e.maybe + e.before + (e.kind ? 3 : 0)) * 0.25);
    const f = (d - L) * 0.035 * a * w;
    P[i].vx += dx / d * f; P[i].vy += dy / d * f; P[j].vx -= dx / d * f; P[j].vy -= dy / d * f;
  }
  if (S.lens !== 'logical') {
    const sum = new Map();
    nodes.forEach((v, k) => { const g = groupOf(v); const s = sum.get(g) || {x: 0, y: 0, c: 0}; s.x += P[k].x; s.y += P[k].y; s.c++; sum.set(g, s); });
    nodes.forEach((v, k) => { const s = sum.get(groupOf(v)); if (s.c > 1) { P[k].vx += (s.x / s.c - P[k].x) * 0.05 * a; P[k].vy += (s.y / s.c - P[k].y) * 0.05 * a; } });
  }
  nodes.forEach((v, k) => {
    const p = P[k];
    p.vx -= p.x * 0.012 * a; p.vy -= p.y * 0.012 * a;
    if (S.drag && S.drag.id === v) { p.x = S.drag.x; p.y = S.drag.y; p.vx = p.vy = 0; return; }
    p.vx *= 0.58; p.vy *= 0.58; p.x += p.vx; p.y += p.vy;
  });
  S.alpha *= 0.982;
  return true;
}

/* ------------------------------------------------------------ drawing */
const cv = $('#cv'), ctx = cv.getContext('2d');
let DPR = 1, redraw = true;
function resize() { DPR = window.devicePixelRatio || 1; const r = cv.getBoundingClientRect(); cv.width = Math.round(r.width * DPR); cv.height = Math.round(r.height * DPR); redraw = true; }
const W = () => cv.width / DPR, H = () => cv.height / DPR;
const toScreen = p => ({x: p.x * S.view.k + S.view.x + W() / 2, y: p.y * S.view.k + S.view.y + H() / 2});
const toWorld = (sx, sy) => ({x: (sx - S.view.x - W() / 2) / S.view.k, y: (sy - S.view.y - H() / 2) / S.view.k});
const rep = i => (i == null ? null : S.visOf.get(i) ?? null);

function focusSets() {
  // What is "in focus" right now; everything else fades.
  if (S.ask) return {strong: new Set(S.ask.hits.map(x => rep(x.node))), soft: new Set()};
  if (S.mode === 'review' && S.review) {
    if (S.rfocus) return {strong: new Set(S.rfocus.map(rep)), soft: new Set()};
    return {strong: new Set(S.review.changed.map(c => rep(c.node))), soft: new Set([...S.review.affected, ...S.review.tests].map(a => rep(a.node)))};
  }
  const center = S.hover ?? S.selected;
  if (center == null || rep(center) == null) return null;
  const c = rep(center), strong = new Set([c]), soft = new Set();
  for (const e of S.edges) { if (e.a === c) soft.add(e.b); if (e.b === c) soft.add(e.a); }
  return {strong, soft};
}
function reviewStyle(v) {
  if (!(S.mode === 'review' && S.review)) return null;
  const ch = S.review.changed.find(c => c.node != null && rep(c.node) === v);
  if (ch) return {ring: ch.change === 'deleted' ? '#c08cff' : '#ffffff', w: 3.5, tag: ch.change === 'deleted' ? 'removed' : ch.change === 'added' ? 'added' : 'changed'};
  const a = S.review.affected.filter(a => rep(a.node) === v).sort((x, y) => x.dist - y.dist)[0];
  if (a) return {ring: '#ffd75e', w: a.dist === 1 ? 2.6 : 1.6, tag: a.dist === 1 ? 'uses it' : 'indirect'};
  return null;
}
function themeInk() {
  const light = document.documentElement.style.colorScheme === 'light';
  const contrast = false;
  return {
    text: contrast ? '#ffffff' : light ? '#172033' : '#e8ecf2',
    plate: contrast ? 'rgba(0,0,0,.92)' : light ? 'rgba(255,255,255,.92)' : 'rgba(14,17,22,.8)',
    hole: light ? '#ffffff' : '#0e1116',
    holeInk: contrast ? '#ffffff' : light ? '#172033' : '#e8ecf2',
  };
}
function draw() {
  const w = W(), hgt = H();
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.clearRect(0, 0, w, hgt);
  const fs = focusSets(), k = S.view.k;
  const inFocus = v => !fs || fs.strong.has(v) || fs.soft.has(v);
  for (const e of S.edges) {
    const A = S.pos.get(e.a), B = S.pos.get(e.b); if (!A || !B) continue;
    const a = toScreen(A), b = toScreen(B);
    const hot = fs && (fs.strong.has(e.a) && (fs.soft.has(e.b) || fs.strong.has(e.b)) || fs.strong.has(e.b) && (fs.soft.has(e.a) || fs.strong.has(e.a)));
    const wgt = e.sure + e.maybe + e.before + (e.kind ? 3 : 0);
    ctx.globalAlpha = hot ? 0.95 : fs ? 0.07 : Math.min(0.5, 0.16 + Math.log2(1 + wgt) * 0.05);
    ctx.lineWidth = (hot ? 1.8 : 1) + Math.min(2.4, Math.log2(1 + wgt) * 0.45);
    // the colour follows the strongest evidence that is switched on: sure, then maybe, then old-version only
    ctx.strokeStyle = e.kind ? '#b9c3d6' : e.sure ? '#5fd39a' : e.maybe ? '#e8b45a' : '#8c96a8';
    ctx.setLineDash(e.kind || e.sure ? [] : e.maybe ? [6, 5] : [2, 4]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    if (hot) {
      const ang = Math.atan2(b.y - a.y, b.x - a.x), rb = radius(e.b) * k + 4, tx = b.x - Math.cos(ang) * rb, ty = b.y - Math.sin(ang) * rb;
      ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - Math.cos(ang - .4) * 9, ty - Math.sin(ang - .4) * 9); ctx.lineTo(tx - Math.cos(ang + .4) * 9, ty - Math.sin(ang + .4) * 9); ctx.closePath(); ctx.fillStyle = ctx.strokeStyle; ctx.fill();
    }
  }
  ctx.setLineDash([]);
  const drawn = [];
  for (const v of S.vis) {
    const p = S.pos.get(v); if (!p) continue;
    const s = toScreen(p), r = radius(v) * k, n = N[v], col = colorOf(v), rv = reviewStyle(v), isT = isTestNode(v);
    if (s.x < -60 || s.y < -60 || s.x > w + 60 || s.y > hgt + 60) continue;
    const alpha = inFocus(v) ? 1 : rv ? 0.45 : 0.22;
    ctx.globalAlpha = alpha;
    if (isContainer(v) && !S.open.has(v)) { ctx.beginPath(); ctx.arc(s.x, s.y, r + 4, 0, 6.283); ctx.strokeStyle = col; ctx.globalAlpha = alpha * 0.55; ctx.lineWidth = 1.4; ctx.stroke(); ctx.globalAlpha = alpha; }
    ctx.beginPath();
    if (n.k === 'class') ctx.rect(s.x - r, s.y - r, r * 2, r * 2); else ctx.arc(s.x, s.y, r, 0, 6.283);
    if (n.gone) { ctx.setLineDash([4, 3]); ctx.lineWidth = 2; ctx.strokeStyle = col; ctx.stroke(); ctx.setLineDash([]); }
    else if (isT) { const ink = themeInk(); ctx.fillStyle = ink.hole; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = col; ctx.stroke(); }
    else { ctx.fillStyle = col; ctx.fill(); }
    if (rv) { ctx.beginPath(); ctx.arc(s.x, s.y, r + 5, 0, 6.283); ctx.lineWidth = rv.w; ctx.strokeStyle = rv.ring; ctx.stroke(); }
    const sel = S.mode === 'review' ? S.rfocus && rep(S.rfocus[0]) === v : S.selected === v;
    if (sel) { ctx.beginPath(); ctx.arc(s.x, s.y, r + 9, 0, 6.283); ctx.lineWidth = 2; ctx.strokeStyle = '#ffd75e'; ctx.globalAlpha = 1; ctx.stroke(); }
    if (n.k === 'dir') { const ink = themeInk(); ctx.fillStyle = isT ? ink.holeInk : (ink.hole === '#ffffff' ? '#172033' : '#0b1020'); ctx.globalAlpha = alpha * 0.9; ctx.font = '600 ' + Math.max(10, r * 0.7) + 'px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(kids[v].length), s.x, s.y + 0.5); }
    drawn.push({v, s, r, rv, sel});
  }
  const placed = [], prio = d => (d.sel ? 0 : fs && fs.strong.has(d.v) ? 1 : fs && fs.soft.has(d.v) ? 2 : d.rv ? 2 : N[d.v].k === 'dir' ? 3 : N[d.v].k === 'file' ? 4 : 5);
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  for (const d of drawn.sort((a, b) => prio(a) - prio(b))) {
    const n = N[d.v], p = prio(d), show = p <= 3 || (p === 4 && k > 0.55) || (p === 5 && k > 0.9) || S.hover === d.v;
    if (!show) continue;
    const bold = p <= 1; ctx.font = (bold ? '700 ' : '500 ') + (bold ? 13 : 12) + 'px system-ui';
    const text = n.k === 'fn' ? (p <= 2 ? n.q : n.n) + '()' : n.k === 'dir' ? n.q : n.n, wd = ctx.measureText(text).width, x = d.s.x + d.r + 7, y = d.s.y;
    const tag = d.rv ? d.rv.tag : n.gone ? 'removed' : null;
    const box = {x0: x - 3, x1: x + wd + 3, y0: y - 9, y1: y + (tag ? 22 : 9)};
    if (p > 1 && placed.some(b => !(box.x1 < b.x0 || box.x0 > b.x1 || box.y1 < b.y0 || box.y0 > b.y1))) continue;
    placed.push(box);
    ctx.globalAlpha = inFocus(d.v) ? 1 : d.rv ? 0.6 : 0.25;
    const ink = themeInk();
    ctx.fillStyle = ink.plate; ctx.fillRect(box.x0, box.y0, box.x1 - box.x0, box.y1 - box.y0);
    ctx.fillStyle = ink.text; ctx.fillText(text, x, y);
    if (tag) { ctx.font = '650 11px system-ui'; ctx.fillStyle = d.rv ? d.rv.ring : '#c08cff'; ctx.fillText(tag, x, y + 14); }
  }
  ctx.globalAlpha = 1;
}
function frame() {
  const moved = tick();
  if (moved || redraw || S.anim) { stepAnim(); draw(); redraw = false; }
  requestAnimationFrame(frame);
}
function stepAnim() {
  if (!S.anim) return;
  const t = S.anim, v = S.view, e = 0.16;
  v.x += (t.x - v.x) * e; v.y += (t.y - v.y) * e; v.k += (t.k - v.k) * e;
  if (Math.abs(t.x - v.x) < 0.4 && Math.abs(t.y - v.y) < 0.4 && Math.abs(t.k - v.k) < 0.002) { v.x = t.x; v.y = t.y; v.k = t.k; S.anim = null; }
}
function fit(ids, pad = 80, maxK = 2.0) {
  const pts = (ids && ids.length ? ids : S.vis).map(i => S.pos.get(rep(i))).filter(Boolean);
  if (!pts.length) return;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y), x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const k = Math.max(0.25, Math.min(maxK, Math.min((W() - pad * 2) / Math.max(60, x1 - x0), (H() - pad * 2) / Math.max(60, y1 - y0))));
  S.anim = {k, x: -((x0 + x1) / 2) * k, y: -((y0 + y1) / 2) * k};
}
const later = (f, ms = 450) => setTimeout(f, ms);

/* ------------------------------------------------------------ interaction on the canvas */
function pick(sx, sy) {
  let best = null, bd = 1e9;
  for (const v of S.vis) {
    const p = S.pos.get(v); if (!p) continue;
    const s = toScreen(p), d = Math.hypot(s.x - sx, s.y - sy), r = radius(v) * S.view.k + 5;
    if (d <= r && d < bd) { best = v; bd = d; }
  }
  return best;
}
let down = null;
cv.addEventListener('mousedown', ev => {
  const r = cv.getBoundingClientRect(), sx = ev.clientX - r.left, sy = ev.clientY - r.top;
  down = {sx, sy, hit: pick(sx, sy), moved: false, vx: S.view.x, vy: S.view.y};
  cv.style.cursor = 'grabbing';
});
window.addEventListener('mousemove', ev => {
  const r = cv.getBoundingClientRect(), sx = ev.clientX - r.left, sy = ev.clientY - r.top;
  if (down) {
    if (Math.hypot(sx - down.sx, sy - down.sy) > 4) down.moved = true;
    if (down.moved) {
      if (down.hit != null) { const w = toWorld(sx, sy); S.drag = {id: down.hit, x: w.x, y: w.y}; S.alpha = Math.max(S.alpha, 0.3); }
      else { S.view.x = down.vx + (sx - down.sx); S.view.y = down.vy + (sy - down.sy); S.anim = null; redraw = true; }
    }
    return;
  }
  if (ev.target !== cv || S.mode === 'review') return;
  const hit = pick(sx, sy);
  if (hit !== S.hover) { S.hover = hit; cv.style.cursor = hit != null ? 'pointer' : 'grab'; redraw = true; }
});
window.addEventListener('mouseup', () => {
  if (!down) return;
  const d = down; down = null; S.drag = null; cv.style.cursor = d.hit != null ? 'pointer' : 'grab';
  if (!d.moved) { if (d.hit != null) clickNode(d.hit); else if (S.ask) clearAsk(); }
});
cv.addEventListener('wheel', ev => {
  ev.preventDefault();
  const r = cv.getBoundingClientRect(), sx = ev.clientX - r.left, sy = ev.clientY - r.top, before = toWorld(sx, sy);
  S.view.k = Math.max(0.2, Math.min(3.5, S.view.k * Math.exp(-ev.deltaY * 0.0015))); S.anim = null;
  S.view.x = sx - W() / 2 - before.x * S.view.k; S.view.y = sy - H() / 2 - before.y * S.view.k; redraw = true;
}, {passive: false});
$('#zin').onclick = () => { S.anim = {k: Math.min(3.5, S.view.k * 1.3), x: S.view.x * 1.3, y: S.view.y * 1.3}; };
$('#zout').onclick = () => { S.anim = {k: Math.max(0.2, S.view.k / 1.3), x: S.view.x / 1.3, y: S.view.y / 1.3}; };
$('#zfit').onclick = () => fit();

function clickNode(i) {
  if (S.mode === 'review') return reviewClick(i);
  S.ask = null;
  if (N[i].k === 'fn') return selectFn(i);
  S.selected = i; S.force = new Set();
  if (isContainer(i) && !S.open.has(i)) { S.open.add(i); S.trail.push(i); update(); later(() => fit(kids[i].filter(c => S.pos.has(c)), 110)); }
  else update();
}
// Selecting a function brings its real callers and callees onto the graph, as functions, with their folders as context.
function selectFn(i) {
  S.selected = i; S.ask = null;
  S.force = new Set([i, ...neighbourIds(i)]);
  update();
  later(() => fit([i, ...neighbourIds(i)], 120, 1.6), 500);
}
function goTo(id) {                                         // open the way to a node, as if clicking down to it, and select it
  for (const a of ancestors(id).reverse()) if (!S.open.has(a)) { S.open.add(a); S.trail.push(a); }
  if (N[id].k === 'fn') return selectFn(id);
  S.selected = id; S.force = new Set(); update(); later(() => fit([id], 120, 1.4));
}
function clearAsk() { S.ask = null; S.force = S.selected != null && N[S.selected].k === 'fn' ? new Set([S.selected, ...neighbourIds(S.selected)]) : new Set(); update(); }
function undoOne() {                                      // steps back inside the explorer; true when it did something
  if (!$('#palette').hidden) { closePalette(); return true; }
  if (S.mode === 'review') { if (S.rnode != null) S.rnode = null; else if (S.rfocus) S.rfocus = null; else return false; update(); later(() => fit([...S.force], 110)); return true; }
  if (S.ask) { clearAsk(); return true; }
  if (S.selected != null && N[S.selected].k === 'fn') { const f = S.selected; S.selected = null; S.force = new Set(); update(); later(() => fit([fileOf(f)], 140, 1.4)); return true; }
  const last = S.trail.pop();
  if (last != null) {
    S.open.delete(last);
    for (const o of [...S.open]) if (ancestors(o).includes(last)) S.open.delete(o);
    S.trail = S.trail.filter(x => S.open.has(x));
    S.selected = last; update(); later(() => fit()); return true;
  }
  if (S.selected != null) { S.selected = null; update(); return true; }
  return false;
}
function back() { if (!undoOne()) emit({rt: 'escape'}); }      // nothing left to undo here: the app goes back a page
$('#back').onclick = back;
window.addEventListener('keydown', ev => {
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') { ev.preventDefault(); openPalette(); }
  else if (ev.key === '/' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { ev.preventDefault(); openPalette(); }
  else if (ev.key === 'Escape' && $('#palette').hidden) back();
});

/* ------------------------------------------------------------ explore: the panel on the right */
const R = $('#right');
const goBtn = (id, text) => h('button', {class: 'btn link', onclick: () => goTo(id)}, text || label(id));
const list = items => items.length ? h('ul', {class: 'list'}, items) : h('p', {class: 'note'}, 'Nothing RepoTrace could trace.');
const codeLines = (code, first, hl) => h('pre', {class: 'code'}, code.split('\n').map((t, k) => h('div', {class: first + k === hl ? 'hl' : null}, h('span', {class: 'ln'}, first + k), t)));
const snippetAt = (rows, line) => h('pre', {class: 'code'}, rows.map(([n, t]) => h('div', {class: n === line ? 'hl' : null}, h('span', {class: 'ln'}, n), t)));
function neighbours(id) {
  const agg = list => { const m = new Map(); for (const e of list) { const o = m.get(e.id) || {id: e.id, sure: 0, maybe: 0, before: 0}; if (e.tier === 0) o.sure += e.n; else if (e.tier === 1) o.maybe += e.n; else o.before += e.n; m.set(e.id, o); } return [...m.values()]; };
  return {uses: agg(outL[id]), usedBy: agg(inL[id])};
}
function fileNeighbours(file) {
  const inside = new Set(), collect = i => { inside.add(i); kids[i].forEach(collect); }; collect(file);
  const up = new Map(), down = new Map();
  for (const [a, b, tier, n] of G.links) {
    if (inside.has(a) && !inside.has(b)) { const f = fileOf(b); up.set(f, (up.get(f) || 0) + n); }
    if (inside.has(b) && !inside.has(a)) { const f = fileOf(a); down.set(f, (down.get(f) || 0) + n); }
  }
  const top = m => [...m.entries()].sort((x, y) => y[1] - x[1]).slice(0, 8);
  return {uses: top(up), usedBy: top(down)};
}
function paintSide() {
  if (S.mode === 'review') return paintReview();
  if (S.ask) return paintAsk();
  const i = S.selected;
  if (i == null) return paintIntro();
  const n = N[i], parts = [h('h1', {class: 'title'}, label(i)),
    h('div', null, h('span', {class: 'chip'}, kindWord(n)), n.test ? h('span', {class: 'chip'}, 'test code') : null, n.file ? h('span', {class: 'mono note'}, n.file + (n.line > 1 ? ':' + n.line : '')) : null)];
  if (n.doc) parts.push(h('p', null, n.doc));
  if (n.k === 'dir') {
    parts.push(h('p', {class: 'note'}, plural(kids[i].length, 'file') + (S.open.has(i) ? ', open on the graph.' : '. Click it on the graph to open it.')),
      h('h2', null, 'Files'), list(kids[i].filter(c => !N[c].test || S.show.tests).map(c => h('li', null, goBtn(c, N[c].n), h('span', {class: 'note'}, plural(N[c].lines || 0, 'line'))))));
  } else if (n.k === 'file') {
    const nb = fileNeighbours(i);
    parts.push(h('h2', null, 'Inside it'), list(kids[i].map(c => h('li', null, goBtn(c, label(c)), N[c].doc ? h('span', {class: 'note'}, N[c].doc.slice(0, 60)) : null))),
      h('h2', null, 'Uses these files'), list(nb.uses.map(([f, c]) => h('li', null, goBtn(f), h('span', {class: 'note'}, plural(c, 'call'))))),
      h('h2', null, 'Used by these files'), list(nb.usedBy.map(([f, c]) => h('li', null, goBtn(f), h('span', {class: 'note'}, plural(c, 'call'))))));
  } else if (n.k === 'class') {
    parts.push(h('h2', null, 'What it can do'), list(kids[i].map(c => h('li', null, goBtn(c, N[c].n + '()')))),
      relOut[i].some(r => r.kind === 0) ? [h('h2', null, 'Is a kind of'), list(relOut[i].filter(r => r.kind === 0).map(r => h('li', null, goBtn(r.id))))] : null,
      relIn[i].some(r => r.kind === 0) ? [h('h2', null, 'Kinds of it'), list(relIn[i].filter(r => r.kind === 0).map(r => h('li', null, goBtn(r.id))))] : null);
  } else {
    const nb = neighbours(i), tests = nb.usedBy.filter(x => N[x.id].test), users = nb.usedBy.filter(x => !N[x.id].test);
    const row = x => h('li', null, h('button', {class: 'btn link', onclick: () => selectFn(x.id)}, label(x.id)), x.sure ? null : h('span', {class: 'tag m'}, 'maybe'), h('span', {class: 'note mono'}, N[x.id].file.split('/').slice(-2).join('/')));
    parts.push(h('p', {class: 'note'}, 'These functions are now on the graph. Arrows point from the caller to the function it calls.'),
      h('h2', null, 'It calls (' + nb.uses.length + ')'), list(nb.uses.map(row)),
      n.unres ? h('p', {class: 'note'}, '+ ' + plural(n.unres, 'call') + ' inside it that RepoTrace could not trace, so this list may be incomplete.') : null,
      h('h2', null, 'Called by (' + users.length + ')'), list(users.map(row)),
      h('h2', null, 'Tests that call it (' + tests.length + ')'), tests.length ? list(tests.map(row)) : h('p', {class: 'note'}, 'No test calls it directly that RepoTrace could trace. That is not proof it is untested.'),
      n.code ? h('details', {open: true}, h('summary', null, 'The code'), codeLines(n.code, n.line, -1)) : null,
      h('div', {class: 'acts'}, h('button', {class: 'btn', onclick: () => emit({rt: 'read', graph: GK, review: S.review ? D.reviews.indexOf(S.review) : null, id: i})}, 'Open the reading view \u2197')));
  }
  fill(R, parts);
  paintChrome();
}
function traceBox() {
  const c = G.calls, own = c.sure + c.maybe + c.untraced;
  const seg = (col, v) => v ? h('i', {style: `width:${100 * v / own}%;background:${col}`}) : null;
  const row = (col, v, name, what) => h('div', {class: 'row2'}, h('i', {style: 'background:' + col}), h('b', null, v.toLocaleString()), h('span', null, h('b', null, name), ' (' + pct(v, own) + ') · ' + what));
  return h('div', {class: 'trace'},
    h('h2', null, 'What the analysis could trace'),
    h('p', {class: 'note', style: 'margin:0'}, `Of ${own.toLocaleString()} calls that could go to this project's own code:`),
    h('div', {class: 'bar', role: 'img', 'aria-label': `${c.sure} sure, ${c.maybe} maybe, ${c.untraced} not traced`}, seg('#5fd39a', c.sure), seg('#e8b45a', c.maybe), seg('#4a5466', c.untraced)),
    row('#5fd39a', c.sure, 'sure', 'the code text shows where it goes'),
    row('#e8b45a', c.maybe, 'maybe', 'depends on an assumption'),
    row('#4a5466', c.untraced, 'not traced', 'could not tell where it goes'),
    h('p', {class: 'note'}, `Another ${c.outside.toLocaleString()} calls go to Python itself or installed libraries: counted, not drawn. These numbers say how much was traced, not whether the traced links are correct.`));
}
function paintIntro() {
  fill(R, h('h1', {class: 'title'}, 'Start anywhere'),
    h('p', null, 'Each dot is a ', h('b', null, 'folder'), '. Click one to open it into its files, a file into its classes and functions. Click a function to bring the functions it calls, and that call it, onto the graph.'),
    h('h2', null, 'Or ask'), h('p', {class: 'note'}, 'Press ⌘K (or /) and type a question. Matches are highlighted on the graph with file and line.'),
    D.questions.map(q => h('button', {class: 'btn q', onclick: () => runAsk(q)}, '“' + q + '”')),
    traceBox());
  paintChrome();
}
let stateTimer = 0;
function emitState() { clearTimeout(stateTimer); stateTimer = setTimeout(() => emit({rt: 'state', snapshot: snapshot()}), 250); }
function snapshot() {
  return {mode: S.mode, review: S.review ? D.reviews.indexOf(S.review) : null, graph: GK, open: [...S.open], trail: [...S.trail], selected: S.selected, force: [...S.force], lens: S.lens, show: {...S.show},
    view: {...S.view}, pos: [...S.pos].map(([k, p]) => [k, Math.round(p.x), Math.round(p.y)]), rsel: S.rsel, rfocus: S.rfocus, ask: S.ask ? S.ask.q : null};
}
function restoreState(s) {
  load(s.graph);
  S.mode = s.mode; S.review = s.review != null ? D.reviews[s.review] : null;
  if (S.review) S.rbase = new Set([...S.review.changed.map(c => c.node), ...S.review.affected.map(a => a.node), ...S.review.tests.map(t => t.node)].filter(x => x != null));
  Object.assign(S, {open: new Set(s.open), trail: s.trail, selected: s.selected, force: new Set(s.force), lens: s.lens, show: s.show, view: s.view, rsel: s.rsel, rfocus: s.rfocus});
  S.pos = new Map(s.pos.map(([k, x, y]) => [k, {x, y, vx: 0, vy: 0}]));
  document.querySelector(`input[name=lens][value=${s.lens}]`).checked = true;
  $('#oSure').checked = s.show.sure; $('#oMaybe').checked = s.show.maybe; $('#oTests').checked = s.show.tests;
  setTabs(); update(); S.alpha = 0.05;
}
function paintChrome() {
  const chain = S.mode === 'explore' && S.selected != null ? [...ancestors(S.selected).reverse(), S.selected] : [];
  fill($('#crumbs'), h('button', {onclick: () => { S.selected = null; S.open = new Set(); S.trail = []; S.force = new Set(); S.ask = null; update(); later(() => fit()); }}, D.project.name),
    chain.flatMap(i => [h('span', null, '›'), h('button', {onclick: () => goTo(i)}, N[i].k === 'dir' ? N[i].q : N[i].n)]));
  const c = G.calls;
  $('#status').textContent = `Traced: ${c.sure} sure · ${c.maybe} maybe · ${c.untraced} not traced`;
  $('#hint').textContent = S.ask ? 'Showing where matches were found. Click empty space or press Esc to clear.'
    : S.mode === 'review' ? (S.rfocus ? 'Showing the selected finding. Esc shows the whole change.' : 'White ring = changed · yellow ring = may be affected · the rest is faded.')
    : S.selected != null && N[S.selected].k === 'fn' ? 'Arrows go from caller to called. Click another function to walk there. Esc goes back.'
    : 'Click a dot to open it. Drag to move. Scroll to zoom. Esc goes back.';
  document.querySelectorAll('.legend .rv').forEach(e => { e.hidden = S.mode !== 'review'; });
  emitState();
}

/* ------------------------------------------------------------ ask: retrieval first, no language model */
const SYN = {retry: ['retry', 'retries', 'attempt', 'backoff', 'delay'], store: ['store', 'storage', 'persist', 'save', 'sqlite', 'memory', 'repository'], fail: ['fail', 'failure', 'error', 'exception', 'retry'],
  auth: ['auth', 'authentication', 'login', 'token', 'permission', 'middleware'], authentication: ['auth', 'token', 'login', 'middleware'], job: ['job', 'task', 'queue'], handle: ['handle', 'handler', 'process', 'run'],
  save: ['save', 'write', 'store', 'file', 'json', 'repository'], email: ['email', 'valid', 'rule'], check: ['valid', 'rule', 'check', 'fail'],
  full: ['full', 'seat', 'maximum', 'capacity', 'count'], enroll: ['enroll', 'enrollment', 'join']};
function STEM(w) {
  if (w.length < 4) return w;
  if (/ies$/.test(w)) w = w.slice(0, -3) + 'y';
  else if (/(ss|us|is)$/.test(w)) { /* keep */ }
  else if (/(sses|xes|ches|shes|zes)$/.test(w)) w = w.slice(0, -2);
  else if (/s$/.test(w)) w = w.slice(0, -1);
  return w.replace(/(ing|ed)$/, '').replace(/e$/, '');
}
for (const k of Object.keys(SYN)) { const s = STEM(k); SYN[s] = [...new Set([...(SYN[s] || []), ...SYN[k]])]; }
const STOPQ = new Set('where what how when why who which does do did is are was were the a an of to in on for and or with by from it this that happens happen handled handle implemented checked'.split(' '));
const tokenize = t => (t || '').replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase().replace(/_/g, ' ').match(/[a-z][a-z0-9]+/g) || [];
function buildDocs() {
  DOCS = []; const df = new Map();
  N.forEach(n => {
    if ((n.k !== 'fn' && n.k !== 'class') || n.gone) return;
    const f = new Map(), add = (words, wt) => words.forEach(w => { const s = STEM(w); f.set(s, (f.get(s) || 0) + wt); });
    add(tokenize(n.n), 4); add(tokenize(n.q), 2); add(tokenize(n.file), 2); add(tokenize(n.doc), 1.5); add(tokenize(n.code).slice(0, 80), 0.4);
    DOCS.push({node: n.i, f}); for (const s of f.keys()) df.set(s, (df.get(s) || 0) + 1);
  });
  DOCS.df = df;
}
function retrieve(q) {
  if (!DOCS) buildDocs();
  const want = new Map();
  for (const w of tokenize(q).filter(w => !STOPQ.has(w))) { want.set(STEM(w), 1); for (const s of (SYN[STEM(w)] || [])) want.set(STEM(s), Math.max(want.get(STEM(s)) || 0, 0.6)); }
  const scored = [];
  for (const d of DOCS) {
    let score = 0; const why = [];
    for (const [t, wt] of want) { const tf = d.f.get(t); if (tf) { score += wt * tf * Math.log(1 + DOCS.length / (DOCS.df.get(t) || 1)); why.push(t); } }
    if (score > 0 && !N[d.node].test) scored.push({node: d.node, score, why});
  }
  scored.sort((a, b) => b.score - a.score);
  return {hits: scored.slice(0, 8)};
}
function runAsk(q) {
  closePalette();
  if (S.mode !== 'explore') enterExplore(false);
  const r = retrieve(q);
  S.ask = {q, ...r}; S.selected = null;
  S.force = new Set(r.hits.map(x => x.node));
  update();
  later(() => fit(r.hits.map(x => x.node), 120), 550);
}
function paintAsk() {
  const a = S.ask;
  fill(R, h('h1', {class: 'title'}, 'Found in the code'), h('p', {class: 'note'}, '“' + a.q + '”'),
    h('div', {class: 'card info'}, h('b', {style: 'display:block'}, 'No AI explanation (yet)'), h('p', {class: 'note', style: 'margin:0'}, 'These are word matches on names, paths, comments and code. An optional AI summary that cites these same lines would go here, only if you switch it on.')),
    h('h2', null, a.hits.length ? 'Best matches' : 'No match'),
    a.hits.length ? a.hits.map((x, k) => { const n = N[x.node]; return h('div', {class: 'card'}, h('div', null, h('b', null, (k + 1) + '. '), h('button', {class: 'btn link', onclick: () => n.k === 'fn' ? selectFn(x.node) : goTo(x.node)}, label(x.node)), ' ', h('span', {class: 'chip'}, kindWord(n))),
      h('div', {class: 'mono note'}, n.file + ':' + n.line), n.doc ? h('p', {style: 'margin:4px 0'}, n.doc) : null, h('div', {class: 'note'}, 'Matched on: ' + x.why.join(', '))); })
      : h('p', {class: 'note'}, 'Nothing matched. Try other words, or browse the folders.'),
    h('button', {class: 'btn', onclick: clearAsk}, 'Clear'));
  paintChrome();
}

/* ------------------------------------------------------------ review mode */
function enterExplore(relayout = true) {
  S.mode = 'explore'; S.rfocus = null; S.rnode = null;
  const fresh = load('main');
  setTabs();
  if (fresh) startLayout(); else if (relayout) { S.force = new Set(); update(); }
}
function setTabs() {
  $('#mExplore').setAttribute('aria-pressed', S.mode === 'explore'); $('#mReview').setAttribute('aria-pressed', S.mode === 'review');
  renderLeft();
}
function renderLeft() {
  const box = $('#reviewControls');
  if (S.mode === 'review') {
    fill(box, h('h2', null, 'Compare'), h('select', {id: 'cmp', 'aria-label': 'Which change', onchange: e => selectReview(+e.target.value)}, D.reviews.map((r, i) => h('option', {value: i, selected: S.review === r}, r.label))),
      S.review ? h('p', {class: 'note'}, S.review.example ? 'An edit made for this demo, so there is something to find.' : 'A real commit from the project’s history.') : null);
  } else box.replaceChildren();
  const showTopics = S.lens === 'conceptual';
  $('#topicsBox').hidden = !showTopics;
  if (showTopics) {
    const files = N.filter(n => n.k === 'file' && !n.test && !n.gone);
    fill($('#topics'), G.concepts.map((c, i) => {
      const ex = files.filter(f => G.concept_of[f.i] === i).sort((a, b) => (b.lines || 0) - (a.lines || 0));
      return h('div', {class: 'topic'}, h('span', {class: 'dot', style: `background:${PALETTE[i % PALETTE.length]};border-color:${PALETTE[i % PALETTE.length]}`}),
        h('span', null, c, h('small', null, plural(ex.length, 'file') + ', e.g. ' + ex.slice(0, 3).map(f => f.q.split('/').slice(-2).join('/')).join(', '))));
    }));
  }
}
function selectReview(i) {
  S.mode = 'review'; S.review = D.reviews[i];
  const fresh = load(S.review.graph), r = S.review;
  S.rfocus = null; S.rnode = null; S.rcode = false; S.limitsOpen = false;
  S.rsel = r.concerns.length ? {kind: 'concern', i: 0} : r.changed.length ? {kind: 'changed', i: 0} : null;
  S.rbase = new Set([...r.changed.map(c => c.node), ...r.affected.map(a => a.node), ...r.tests.map(t => t.node)].filter(x => x != null));
  S.force = new Set(S.rbase);
  setTabs();
  if (fresh) startLayout(true); else update();
  applyRsel(false);
  later(() => fit([...S.force], 110), 200);
}
// The selected finding decides what the graph focuses on.
function applyRsel(move = true) {
  const r = S.review, sel = S.rsel;
  S.rfocus = null;
  if (sel && sel.kind === 'concern') { const c = r.concerns[sel.i]; S.rfocus = [c.node, c.target]; }
  if (sel && sel.kind === 'test') { const t = r.tests[sel.i]; S.rfocus = [t.node, t.for_node]; }
  if (sel && sel.kind === 'changed') { const c = r.changed[sel.i]; S.rfocus = c.node == null ? [] : [c.node, ...inL[c.node].map(e => e.id)]; }   // a changed function and whoever calls (or used to call) it
  if (S.rfocus) { S.rfocus = [...new Set(S.rfocus.filter(x => x != null))]; if (!S.rfocus.length) S.rfocus = null; }
  S.force = new Set([...S.rbase, ...(S.rfocus || [])]);
  update();
  if (move) later(() => fit(S.rfocus || [...S.force], 140, 1.6), 300);
}
function reviewClick(i) {
  const r = S.review, find = (items, kind) => { const k = items.findIndex(x => x.node === i); return k >= 0 ? {kind, i: k} : null; };
  const sel = find(r.concerns, 'concern') || find(r.tests, 'test') || find(r.changed, 'changed');
  S.rcode = false;
  if (sel) { S.rsel = sel; S.rnode = null; applyRsel(); }
  else { S.rnode = i; paintSide(); redraw = true; R.scrollTop = 0; }
}
const loc = (file, line) => file.split('/').slice(-1)[0] + (line ? ':' + line : '');
function sigBox(ch) {
  if (!ch || !(ch.before_sig || ch.after_sig)) return null;
  return h('div', {class: 'sig'}, h('span', null, 'Before'), h('code', null, ch.before_sig || '(did not exist)'), h('span', null, 'After'), h('code', null, ch.after_sig || '(removed)'));
}
function wholeCode(id, hl) {
  if (id == null || !N[id].code) return null;
  return h('details', {open: S.rcode, ontoggle: e => { if (S.rcode !== e.target.open) { S.rcode = e.target.open; } }}, h('summary', null, 'The whole of ' + label(id) + (N[id].gone ? ' (old version)' : '')), codeLines(N[id].code, N[id].line, hl));
}
function paintReview() {
  const r = S.review;
  if (!r) return;
  const open = (kind, i) => S.rsel && S.rsel.kind === kind && S.rsel.i === i;
  const pickRow = (kind, i) => { S.rsel = open(kind, i) ? null : {kind, i}; S.rcode = false; S.rnode = null; applyRsel(); };
  const act = (text, f) => h('button', {class: 'btn', onclick: f}, text);
  const focusOn = ids => { S.rfocus = ids.filter(x => x != null); update(); later(() => fit(S.rfocus, 140, 1.6), 100); };
  const rowsOf = (kind, items, head, body) => h('div', {class: 'rows'}, items.map((it, i) => h('div', {class: 'row' + (open(kind, i) ? ' open' : ''), 'data-kind': kind},
    h('button', {class: 'head', 'aria-expanded': String(open(kind, i)), onclick: () => pickRow(kind, i)}, head(it, i)), open(kind, i) ? h('div', {class: 'body'}, body(it, i)) : null)));
  const jump = id => document.getElementById(id).scrollIntoView({behavior: 'smooth', block: 'start'});
  const gone = r.changed.some(c => c.change === 'deleted');
  const parts = [
    h('h1', {class: 'title'}, 'Review'), h('div', {class: 'acts', style: 'margin:6px 0 2px'}, h('button', {class: 'btn', onclick: () => emit({rt: 'review', index: D.reviews.indexOf(r)})}, 'Open the full review \u2197')),
    h('div', {class: 'note'}, h('b', null, r.base), ' → ', h('b', null, r.head), '. The graph and code show ', h('b', null, r.head), gone ? [', plus removed code from ', h('b', null, r.base), ' (dashed)'] : null, '.'),
    h('div', {class: 'sum'},
      h('button', {class: 'w', onclick: () => jump('secCalls')}, h('b', null, r.concerns.length), r.concerns.length === 1 ? 'to inspect' : 'to inspect'),
      h('button', {class: 't', onclick: () => jump('secTests')}, h('b', null, r.tests.length), r.tests.length === 1 ? 'test to look at' : 'tests to look at'),
      h('button', {onclick: () => jump('secChanged')}, h('b', null, r.changed.length), 'changed'),
      h('button', {class: 'l', onclick: () => { S.limitsOpen = true; paintSide(); jump('secLimits'); }}, h('b', null, r.gaps.length), 'not checked')),

    h('h2', {id: 'secCalls'}, 'To inspect (' + r.concerns.length + ')'),
    r.concerns.length ? rowsOf('concern', r.concerns, c => [h('span', {class: 'mark', style: 'background:var(--warn)'}), h('span', {class: 'nm'}, c.title), h('span', {class: 'loc'}, loc(c.file, c.line))],
      c => {
        const ch = c.changed != null ? r.changed[c.changed] : r.changed.find(x => x.node === c.target);
        return [h('p', null, c.what + ' ' + c.why),
          h('span', {class: 'k'}, 'The line, in ' + c.file),
          c.snippet ? snippetAt(c.snippet, c.line) : null,
          c.type === 'signature' || c.type === 'leftover' ? [h('span', {class: 'k'}, c.type === 'leftover' ? 'The function it uses, which was removed' : 'The function it calls'), sigBox(ch)] : null,
          h('span', {class: 'k'}, 'Check next'), h('p', null, c.check),
          h('div', {class: 'acts'}, act('Focus this relationship', () => focusOn([c.node, c.target])), c.node != null ? act(S.rcode ? 'Hide the caller' : 'View the whole caller', () => { S.rcode = !S.rcode; paintSide(); }) : null),
          S.rcode ? wholeCode(c.node, c.line) : null];
      })
      : h('div', {class: 'card'}, h('p', {style: 'margin:0'}, 'The checks that exist found nothing to inspect.'), h('p', {class: 'note', style: 'margin:4px 0 0'}, 'They only cover changed call signatures and leftover uses of removed names, so this is not “safe”. Look at the tests and at what was not checked.')),

    h('h2', {id: 'secTests'}, 'Existing tests worth running first (' + r.tests.length + ')'),
    r.tests.length ? rowsOf('test', r.tests, t => [h('span', {class: 'mark', style: 'background:var(--sure)'}), h('span', {class: 'nm'}, t.name), t.tier ? h('span', {class: 'tag m'}, 'maybe') : null, h('span', {class: 'loc'}, loc(t.file, t.call_line || t.line))],
      t => [h('span', {class: 'k'}, 'How it connects to the change'),
        h('p', {class: 'mono', style: 'overflow-wrap:anywhere'}, t.chain.join('  →  ')),
        t.via ? h('p', {class: 'note'}, t.via.kind === 'setup' ? `Through ${t.via.name}, which unittest runs before this test.`
          : `Through the pytest fixture ${t.via.name}${t.via.autouse ? ', which runs automatically for every test in its folder' : ', which the test asks for'}.`) : null,
        h('span', {class: 'k'}, 'Which version shows this connection'),
        h('p', null, t.seen_in.length === 2 ? 'Both the old and the new version.' : t.seen_in[0] === 'before'
          ? h('span', null, h('b', null, 'Only the old version (' + r.base + ').'), ' RepoTrace cannot follow it in the new code, so check it yourself.')
          : 'Only the new version (' + r.head + ').'),
        h('p', {class: 'note'}, t.tier ? 'Graded maybe: at least one step depends on an assumption (for example a call through self, which a subclass could override).' : 'Graded sure: every step is written out in the code.'),
        t.snippet ? [h('span', {class: 'k'}, t.via && t.via.kind === 'setup' ? 'The line in ' + t.via.name + ' that leads there' : 'The line in the test that leads there'), snippetAt(t.snippet, t.call_line)] : null,
        h('span', {class: 'k'}, 'Run it'), h('p', {class: 'mono'}, t.run || ('python3 -m pytest ' + t.file + '::' + t.name)),
        h('div', {class: 'acts'}, act('Inspect this test', () => { S.rcode = true; focusOn([t.node, t.for_node]); })),
        S.rcode ? wholeCode(t.node, t.call_line) : null])
      : h('p', {class: 'note'}, 'No test that reaches this change was found. That is missing evidence, not proof that no test exists.'),
    r.tests.length ? h('p', {class: 'note'}, 'Found by following calls from tests to the change, in both versions. Not run: a listed test may pass, and an unlisted test may still matter (see what could not be checked).') : null,
    r.removed_tests && r.removed_tests.length ? h('details', {class: 'sec'}, h('summary', null, 'Tests that no longer exist (' + r.removed_tests.length + ')'),
      h('p', {class: 'note'}, 'These tests reached the change in the old version but are gone or renamed in the new one, so there is nothing to run.'),
      h('ul', {class: 'list'}, r.removed_tests.map(t => h('li', null, h('span', {class: 'mono'}, t.name), h('span', {class: 'note'}, t.file))))) : null,

    h('h2', {id: 'secChanged'}, 'What changed (' + r.changed.length + ')'),
    rowsOf('changed', r.changed, c => [h('span', {class: 'mark', style: `background:${c.change === 'deleted' ? 'var(--gone)' : '#fff'}`}), h('span', {class: 'nm'}, c.name + '()'),
      h('span', {class: 'tag ' + (c.change === 'deleted' ? 'g' : 't')}, c.pair ? (c.pair.how === 'moved' ? (c.pair.role === 'old' ? 'moved away' : 'moved here') : (c.pair.role === 'old' ? 'old name' : 'new name')) : c.change), h('span', {class: 'loc'}, loc(c.file))],
      c => [c.pair ? h('p', {class: 'note'}, (c.pair.how === 'moved' ? 'Moved ' : 'Renamed ') + (c.pair.role === 'old' ? 'to ' : 'from ') + c.pair.other + ' in ' + c.pair.other_file + '. The body is otherwise identical.') : null,
        sigBox(c), c.diff ? h('details', null, h('summary', null, 'Show every changed line'), h('pre', {class: 'plain mono'}, c.diff)) : null,
        h('div', {class: 'acts'}, c.node != null ? act(S.rcode ? 'Hide its code' : 'View its code' + (c.change === 'deleted' ? ' (old version)' : ''), () => { S.rcode = !S.rcode; paintSide(); }) : null),
        S.rcode ? wholeCode(c.node, -1) : null]),

    h('details', {class: 'sec', id: 'secLimits', open: S.limitsOpen, ontoggle: e => { S.limitsOpen = e.target.open; }}, h('summary', null, 'What could not be checked (' + r.gaps.length + ')'), h('ul', {class: 'list'}, r.gaps.map(g => h('li', null, '• ' + g)))),
    h('details', {class: 'sec'}, h('summary', null, 'Other code that uses it (' + r.candidates.length + ')'), h('p', {class: 'note'}, 'Candidates to look at, not predicted failures.'),
      list(r.candidates.map(c => h('li', null, c.node != null ? h('button', {class: 'btn link', onclick: () => reviewClick(c.node)}, c.name) : c.name, h('span', {class: 'note'}, c.dist === 1 ? 'calls it directly' : (c.dist - 1) + ' step' + (c.dist > 2 ? 's' : '') + ' away'), c.tier ? h('span', {class: 'tag m'}, 'maybe') : null)))),
    h('details', {class: 'sec'}, h('summary', null, 'Hints from history'), h('p', {class: 'note'}, 'Files edited in the same past commits (' + r.history_window + ' commits looked at). A hint, not a call link.'),
      r.history.length ? r.history.map(x => h('p', null, h('b', null, x.file), h('br'), x.with.length ? x.with.map(w => w.file + ' (' + w.together + ' of ' + w.of + ')').join(', ') : h('span', {class: 'note'}, 'edited alone in ' + plural(x.changed_in, 'commit')))) : h('p', {class: 'note'}, 'No history for these files.'))];
  if (S.rnode != null) {
    const n = N[S.rnode], nb = neighbours(S.rnode);
    parts.splice(1, 0, h('div', {class: 'card'}, h('b', null, label(S.rnode)), ' ', h('span', {class: 'chip'}, kindWord(n)), h('div', {class: 'mono note'}, n.file + ':' + n.line),
      h('p', {class: 'note', style: 'margin:4px 0'}, `Calls ${nb.uses.length} · called by ${nb.usedBy.length}. Not part of a finding for this change.`),
      n.code ? codeLines(n.code, n.line, -1) : null, act('Close', () => { S.rnode = null; paintSide(); })));
  }
  fill(R, parts);
  paintChrome();
}

/* ------------------------------------------------------------ command palette */
const P = {items: [], i: 0};
const FIND_KEY = 'repotrace-find-history';
const REVIEW_TABS = [['overview', 'What to check'], ['changes', 'Changed code'], ['tests', 'Related tests'], ['limits', 'Limits and history'], ['recommendations', 'Recommendations']];
function findHistory() {
  try {
    const value = JSON.parse(localStorage.getItem(FIND_KEY) || '[]');
    return Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.trim()).slice(0, 8) : [];
  } catch (e) { return []; }
}
function rememberFind(text) {
  const typed = String(text || '').trim();
  if (!typed) return;
  const next = [typed].concat(findHistory().filter(item => item.toLowerCase() !== typed.toLowerCase())).slice(0, 8);
  try { localStorage.setItem(FIND_KEY, JSON.stringify(next)); } catch (e) {}
}
function clearFind() { try { localStorage.removeItem(FIND_KEY); } catch (e) {} paintPalette(); }
function openPalette() { $('#palette').hidden = false; $('#pin').value = ''; $('#pin').focus(); paintPalette(); }
function closePalette() { $('#palette').hidden = true; }
function paintPalette() {
  const q = $('#pin').value.trim(), ql = q.toLowerCase(), items = [];
  const M = D.graphs.main.nodes;
  if (!q) D.questions.forEach(x => items.push({type: 'ask', q: x, label: x, sub: 'Ask'}));
  else {
    const ask = q.split(/\s+/).length >= 2 || q.endsWith('?');
    if (ask) items.push({type: 'ask', q, label: q, sub: 'Word search'});
    M.filter(n => n.k !== 'dir' && (n.q.toLowerCase().includes(ql) || n.file.toLowerCase().includes(ql)))
      .map(n => ({n, r: n.n.toLowerCase() === ql ? 0 : n.n.toLowerCase().startsWith(ql) ? 1 : n.q.toLowerCase().includes(ql) ? 2 : 3})).sort((a, b) => a.r - b.r || a.n.q.length - b.n.q.length).slice(0, 8)
      .forEach(({n}) => items.push({type: 'go', id: n.i, label: n.k === 'fn' ? n.q + '()' : n.k === 'file' ? n.n : n.q, sub: (n.k === 'fn' ? 'function' : n.k) + ' · ' + n.file}));
    if (!ask) items.push({type: 'ask', q, label: q, sub: 'Word search'});
  }
  const shown = S.review || (D.reviews || [])[0];
  if (shown) {
    REVIEW_TABS.forEach(([tab, label]) => {
      if (!q || label.toLowerCase().includes(ql) || tab.includes(ql)) items.push({type: 'review', tab, label, sub: 'Review section'});
    });
    if (q.length >= 2) (shown.recommendations || []).forEach(rec => {
      const text = ((rec.recommendation || '') + ' ' + ((rec.evidence && rec.evidence.summary) || '')).toLowerCase();
      if (text.includes(ql)) items.push({type: 'review', tab: 'recommendations', label: rec.recommendation, sub: 'Recommendation'});
    });
  }
  if (!q) findHistory().forEach(text => items.push({type: 'recent', q: text, label: text, sub: 'Recent search'}));
  P.items = items.slice(0, 24); P.i = 0;
  const box = $('#pres'); box.replaceChildren();
  let lastType = null;
  const groupName = type => type === 'ask' ? (q ? 'Ask' : 'Try asking') : type === 'recent' ? 'Recent searches' : type === 'review' ? 'Review' : 'Go to';
  P.items.forEach((it, k) => {
    if (it.type !== lastType) { box.append(h('div', {class: 'grp'}, groupName(it.type))); lastType = it.type; }
    box.append(h('button', {role: 'option', 'aria-selected': String(k === P.i), onclick: () => choose(it), onmousemove: () => { P.i = k; mark(); }}, h('span', {class: 'plabel'}, it.type === 'ask' || it.type === 'recent' ? '? ' : '', it.label), h('span', {class: 'k2'}, it.sub)));
  });
  if (!q && findHistory().length) box.append(h('button', {type: 'button', class: 'clear-find', onclick: event => { event.preventDefault(); clearFind(); }}, 'Clear recent searches'));
}
const mark = () => [...$('#pres').querySelectorAll('[role=option]')].forEach((b, k) => b.setAttribute('aria-selected', String(k === P.i)));
function choose(it) {
  const typed = $('#pin').value.trim();
  if (typed) rememberFind(typed);
  else if (it.type === 'ask' || it.type === 'recent') rememberFind(it.q);
  closePalette();
  if (it.type === 'review') { emit({rt: 'open-review', tab: it.tab, index: S.review ? Math.max(0, D.reviews.indexOf(S.review)) : 0}); return; }
  if (it.type === 'ask' || it.type === 'recent') return runAsk(it.q);
  if (S.mode !== 'explore') enterExplore(false); S.ask = null; goTo(it.id);
}
$('#cmd').onclick = openPalette;
$('#palette').addEventListener('mousedown', e => { if (e.target.id === 'palette') closePalette(); });
$('#pin').addEventListener('input', paintPalette);
$('#pin').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { e.preventDefault(); P.i = Math.min(P.items.length - 1, P.i + 1); mark(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); P.i = Math.max(0, P.i - 1); mark(); }
  else if (e.key === 'Enter') { e.preventDefault(); if (P.items[P.i]) choose(P.items[P.i]); }
  else if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
});

/* ------------------------------------------------------------ wiring */
function startLayout(keepForce) {
  if (!keepForce) S.force = new Set();
  S.pos = new Map();
  computeVisible();
  const groups = [...new Set(S.vis.map(groupOf))];
  S.vis.forEach((v, k) => { const g = groups.indexOf(groupOf(v)), a = g / groups.length * 6.283 + k * 0.01; S.pos.set(v, {x: Math.cos(a) * 240 + (Math.random() - .5) * 60, y: Math.sin(a) * 240 + (Math.random() - .5) * 60, vx: 0, vy: 0}); });
  S.alpha = 1;
  for (let t = 0; t < 260; t++) tick();
  fit(keepForce && S.force.size ? [...S.force] : null, 90);
  if (S.anim) { Object.assign(S.view, {x: S.anim.x, y: S.anim.y, k: S.anim.k}); S.anim = null; }
  redraw = true; paintSide();
}
$('#mExplore').onclick = () => { if (S.mode !== 'explore') enterExplore(); };
$('#mReview').onclick = () => { if (S.mode !== 'review') selectReview(S.review ? D.reviews.indexOf(S.review) : 0); };
document.querySelectorAll('input[name=lens]').forEach(r => r.addEventListener('change', () => { S.lens = r.value; S.alpha = 0.9; renderLeft(); redraw = true; }));
$('#oSure').onchange = e => { S.show.sure = e.target.checked; update(); };
$('#oMaybe').onchange = e => { S.show.maybe = e.target.checked; update(); };
$('#oTests').onchange = e => { S.show.tests = e.target.checked; update(); };
window.addEventListener('resize', resize);

resize(); load('main'); setTabs(); startLayout();
requestAnimationFrame(frame);
if (INIT.restore) restoreState(INIT.restore);
else {
  if (INIT.review != null && D.reviews[INIT.review]) selectReview(INIT.review);
  if (INIT.focus != null) { if (S.mode === 'review') reviewClick(INIT.focus); else goTo(INIT.focus); }
  else if (INIT.query) runAsk(INIT.query);
}
if (INIT.palette) openPalette();
window.__xp = {S, D, get N() { return N; }, get G() { return G; }, get GK() { return GK; }, neighbourIds: i => neighbourIds(i), retrieve: q => retrieve(q),
  // read-only: where each visible dot is inside this page, for the browser checks
  inspect: () => S.vis.map(v => { const s = toScreen(S.pos.get(v)), r = cv.getBoundingClientRect(); return {id: v, q: N[v].q, k: N[v].k, x: r.left + s.x, y: r.top + s.y, open: S.open.has(v), contents: kids[v].length, selected: S.selected === v, gone: !!N[v].gone}; })};
window.__xpHandle = m => {
  if (m.rt === 'palette') openPalette();
  else if (m.rt === 'navigate') navigateTo(m);
  else if (m.rt === 'theme' || m.rt === 'settings') { if (m.rt === 'settings' && window.RTSettings) RTSettings.apply(); redraw = true; }
};
// The app brings this page back to the front. Same place as before: change nothing. Otherwise go where it asks.
function navigateTo(m) {
  resize();
  const cur = S.mode === 'review' && S.review ? D.reviews.indexOf(S.review) : null;
  if (m.keep && (m.review == null ? null : m.review) === cur) { redraw = true; return; }
  if (m.restore) restoreState(m.restore);
  else {
    if (m.review != null && D.reviews[m.review]) selectReview(m.review);
    else { enterExplore(true); S.selected = null; S.open = new Set(); S.trail = []; S.force = new Set(); S.ask = null; update(); later(() => fit()); }
    if (m.focus != null) { if (S.mode === 'review') reviewClick(m.focus); else goTo(m.focus); }
    else if (m.query) runAsk(m.query);
  }
  if (m.palette) openPalette();
  redraw = true;
}
}
window.addEventListener('message', ev => {
  if (ev.source !== window.parent || (location.protocol !== 'file:' && ev.origin !== location.origin)) return;
  const m = ev.data || {};
  if (m.rt === 'init' && !started) { started = true; boot(m); }
  else if (window.__xpHandle) window.__xpHandle(m);
});
emit({rt: 'ready'});
