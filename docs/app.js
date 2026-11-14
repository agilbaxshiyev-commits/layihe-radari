'use strict';

const MONTHS = ['Yan', 'Fev', 'Mar', 'Apr', 'May', 'İyn', 'İyl', 'Avq', 'Sen', 'Okt', 'Noy', 'Dek'];
const TYPES = {
  youth_exchange: 'Gənclər mübadiləsi', training_course: 'Təlim kursu',
  esc_volunteering: 'ESC könüllülük', other: 'Digər proqram',
};
const SOURCES = {
  finderasmus: 'finderasmus.eu', salto: 'SALTO', euneighbours: 'EU Neighbours East',
  opportunitiesforyouth: 'Opportunities for Youth',
};
const HOME_NAMES = { Azerbaijan: 'Azərbaycan' };
const COMPETITION = { low: 'Aşağı', medium: 'Orta', high: 'Yüksək' };
const FILTER_KEY = 'radar.filters';

const state = {
  projects: [], meta: {},
  f: { q: '', country: '', month: '', type: '', dur: '', onlyHome: true, noFee: false, sort: 'score' },
};
const $ = (selector) => document.querySelector(selector);

function h(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid);
  return node;
}

// Scraped links are only ever followed when they are plain https URLs.
const safeUrl = (url) => (/^https:\/\//.test(url || '') ? url : null);

const parseDay = (iso) => (iso ? new Date(`${iso}T00:00:00`) : null);
function today() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}
function fmt(iso) {
  const d = parseDay(iso);
  return d ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}` : '—';
}
function fmtRange(from, to) {
  const s = parseDay(from), e = parseDay(to);
  if (!s) return 'Tarix məlum deyil';
  if (!e || from === to) return fmt(from);
  if (s.getFullYear() !== e.getFullYear()) return `${fmt(from)} – ${fmt(to)}`;
  if (s.getMonth() !== e.getMonth()) return `${s.getDate()} ${MONTHS[s.getMonth()]} – ${fmt(to)}`;
  return `${s.getDate()}–${fmt(to)}`;
}
function daysLeft(iso) {
  const d = parseDay(iso);
  return d ? Math.round((d - today()) / 864e5) : null;
}
const placeOf = (p) => [p.city, p.host_country].filter(Boolean).join(', ') || 'Yer məlum deyil';
const whenOf = (p) => fmtRange(p.start_date, p.end_date) + (p.duration_days ? ` · ${p.duration_days} gün` : '');

/* ---------- filtering ---------- */

function matches(p, ignore = '') {
  const f = state.f;
  if (p.status !== 'open') return false;
  if (f.onlyHome && !p.score.eligible) return false;
  if (f.type && p.type !== f.type) return false;
  if (ignore !== 'country' && f.country && p.host_country !== f.country) return false;
  if (ignore !== 'month' && f.month && (p.start_date || '').slice(0, 7) !== f.month) return false;
  const days = p.duration_days;
  if (f.dur === '7' && !(days && days <= 7)) return false;
  if (f.dur === '14' && !(days >= 8 && days <= 14)) return false;
  if (f.dur === '21' && !(days >= 15 && days <= 21)) return false;
  if (f.dur === 'long' && !(days > 21)) return false;
  if (f.noFee && p.costs.fee_eur > 0) return false;
  if (f.q.trim()) {
    const hay = [p.title, p.description, p.host_country, p.city, (p.topics || []).join(' '),
      p.ai && p.ai.summary_az].join(' ').toLowerCase();
    if (!f.q.toLowerCase().trim().split(/\s+/).every((word) => hay.includes(word))) return false;
  }
  return true;
}

const far = '9999-12-31';
const SORTERS = {
  score: (a, b) => b.score.total - a.score.total || (a.deadline || far).localeCompare(b.deadline || far),
  deadline: (a, b) => (a.deadline || far).localeCompare(b.deadline || far),
  start: (a, b) => (a.start_date || far).localeCompare(b.start_date || far),
  new: (a, b) => (b.first_seen || '').localeCompare(a.first_seen || '') || b.score.total - a.score.total,
};

function fillSelect(select, key, first, options) {
  select.replaceChildren(h('option', { value: '' }, first),
    ...options.map(([value, label]) => h('option', { value }, label)));
  if (!options.some(([value]) => value === state.f[key])) state.f[key] = '';
  select.value = state.f[key];
}

function refreshOptions() {
  const countries = new Set(), months = new Set();
  for (const p of state.projects) {
    if (p.host_country && matches(p, 'country')) countries.add(p.host_country);
    if (p.start_date && matches(p, 'month')) months.add(p.start_date.slice(0, 7));
  }
  fillSelect($('#country'), 'country', 'Hər yer', [...countries].sort().map((c) => [c, c]));
  fillSelect($('#month'), 'month', 'İstənilən vaxt', [...months].sort().map((m) => {
    const [year, month] = m.split('-');
    return [m, `${MONTHS[Number(month) - 1]} ${year}`];
  }));
}

/* ---------- tickets ---------- */

function tier(score) {
  if (!score.eligible) return 'tier-none';
  return score.total >= 70 ? 'tier-high' : score.total >= 50 ? 'tier-mid' : 'tier-low';
}

function scoreBlock(p) {
  const s = p.score;
  if (!s.eligible) {
    return h('div', { class: 'score tier-none' },
      h('div', { class: 'ring' }, h('b', {}, '—')), h('span', { class: 'score-label' }, 'Uyğun deyil'));
  }
  return h('div', { class: `score ${tier(s)}` },
    h('div', { class: 'ring', style: `--v:${s.total}`, role: 'img', 'aria-label': `Bal ${s.total} / 100` },
      h('b', {}, String(s.total))),
    h('span', { class: 'score-label' }, s.label),
    h('span', { class: 'score-sub' }, `şans ${s.chance} · uyğunluq ${s.fit}`));
}

function costChips(p) {
  const c = p.costs, chips = [];
  if (!p.score.eligible) chips.push(['bad', p.score.factors[0].t]);
  if (c.accommodation_food === 'covered') chips.push(['good', 'Yaşayış + yemək ödənilir']);
  else if (c.accommodation_food === 'not_covered') chips.push(['bad', 'Yaşayış ödənilmir']);
  if (c.travel === 'covered') chips.push(['good', 'Yol ödənilir']);
  else if (c.travel === 'reimbursed') {
    chips.push(['good', `Yol qaytarılır${c.travel_limit_eur ? ` (€${c.travel_limit_eur}-dək)` : ''}`]);
  } else if (c.travel === 'not_covered') chips.push(['bad', 'Yol ödənilmir']);
  if (c.accommodation_food === 'unknown' && c.travel === 'unknown') {
    chips.push(['', p.type === 'other' ? 'Xərclər məlum deyil' : 'Xərclər: proqram qaydaları ilə — yoxla']);
  }
  if (c.fee_eur > 0) chips.push(['warn', `İştirak haqqı €${c.fee_eur}`]);
  else if (c.fee_eur === 0) chips.push(['good', 'İştirak haqqı yoxdur']);
  if (p.spots_per_country) chips.push(['', `Ölkədən ${p.spots_per_country} yer`]);
  return chips.map(([kind, text]) => h('span', { class: `chip ${kind}` }, text));
}

function tags(p) {
  const isNew = daysLeft(p.first_seen) >= -2;
  return h('div', { class: 'tags' },
    h('span', { class: 'tag type' }, TYPES[p.type] || TYPES.other),
    isNew && h('span', { class: 'tag new' }, 'Yeni'),
    h('span', { class: 'tag' }, SOURCES[p.source] || p.source),
    p.analysis === 'ai' && h('span', { class: 'tag' }, 'AI analizi'));
}

function deadlineText(p) {
  const left = daysLeft(p.deadline);
  if (left == null) return ['tarix göstərilməyib', false];
  return [left === 0 ? 'bu gün bitir' : `${left} gün qalıb`, left <= 3];
}

function ticket(p) {
  const home = HOME_NAMES[state.meta.home_country] || state.meta.home_country || '';
  const [leftText, soon] = deadlineText(p);
  return h('li', { class: 'ticket' },
    scoreBlock(p),
    h('div', { class: 'body' },
      tags(p),
      h('h2', {}, p.title),
      h('p', { class: 'route' }, home, h('span', { class: 'arrow', 'aria-hidden': 'true' }, '→'), placeOf(p)),
      h('p', { class: 'when' }, whenOf(p)),
      h('div', { class: 'chips' }, costChips(p))),
    h('div', { class: 'stub' },
      h('small', {}, 'Son tarix'),
      h('span', { class: 'date' }, fmt(p.deadline)),
      h('span', { class: `left${soon ? ' soon' : ''}` }, leftText),
      h('button', { class: 'btn', type: 'button', onclick: () => { location.hash = p.id; } }, 'Ətraflı')));
}

function render() {
  const list = state.projects.filter((p) => matches(p)).sort(SORTERS[state.f.sort] || SORTERS.score);
  const soon = list.filter((p) => { const d = daysLeft(p.deadline); return d != null && d <= 7; }).length;
  $('#count').replaceChildren(h('strong', {}, `${list.length} layihə`), ' tapıldı',
    soon ? ` · ${soon}-nin son tarixi 7 gün ərzindədir` : '');
  $('#results').replaceChildren(...(list.length ? list.map(ticket)
    : [h('li', { class: 'empty' }, 'Bu filtrlərə uyğun layihə yoxdur. Filtrləri genişləndir və ya sonra yenidən yoxla.')]));
}

/* ---------- detail ---------- */

function factorRow(f) {
  const sign = f.d > 0 ? 'plus' : f.d < 0 ? 'minus' : '';
  const delta = f.d > 0 ? `+${f.d}` : f.d < 0 ? `−${-f.d}` : '';
  return h('li', { class: sign }, h('span', { class: 'd' }, delta), h('span', {}, f.t));
}

function bar(label, value, kind) {
  return h('div', { class: `bar ${kind}` }, h('span', {}, label), h('i', { style: `--v:${value}` }), h('b', {}, String(value)));
}

function fact(label, value) {
  return value ? h('div', {}, h('dt', {}, label), h('dd', {}, value)) : null;
}

function costSummary(c) {
  const parts = [];
  if (c.accommodation_food === 'covered') parts.push('yaşayış və yemək ödənilir');
  if (c.accommodation_food === 'not_covered') parts.push('yaşayış və yemək ödənilmir');
  if (c.travel === 'covered') parts.push('yol ödənilir');
  if (c.travel === 'reimbursed') parts.push(`yol qaytarılır${c.travel_limit_eur ? ` (€${c.travel_limit_eur}-dək)` : ''}`);
  if (c.travel === 'not_covered') parts.push('yol ödənilmir');
  return parts.join(', ') || 'göstərilməyib — infopack-ə bax';
}

function flashcard(card) {
  return h('button', {
    class: 'card-flip', type: 'button', 'aria-pressed': 'false',
    onclick: (event) => {
      const button = event.currentTarget;
      button.setAttribute('aria-pressed', String(button.classList.toggle('flipped')));
    },
  },
  h('span', { class: 'front' }, h('small', {}, 'Sual'), card.q),
  h('span', { class: 'back' }, h('small', {}, 'Cavab'), card.a));
}

function openDetail(p) {
  const dialog = $('#detail'), s = p.score, ai = p.ai || {}, c = p.costs;
  const needs = [...(ai.documents || []), ...(ai.requirements || [])];
  const ages = p.age_min ? `${p.age_min}${p.age_max ? `–${p.age_max}` : '+'}` : null;
  const spots = [p.spots_per_country && `ölkədən ${p.spots_per_country}`, p.spots_total && `cəmi ${p.spots_total}`]
    .filter(Boolean).join(', ');
  const fee = c.fee_eur == null ? 'qeyd olunmayıb' : c.fee_eur === 0 ? 'yoxdur' : `€${c.fee_eur}`;
  const who = (p.eligible_countries || []).join(', ') || p.eligible_note;
  const url = safeUrl(p.url);

  dialog.replaceChildren(
    h('div', { class: 'd-head' },
      tags(p),
      h('h2', { id: 'detail-title' }, p.title),
      h('p', { class: 'when' }, `${placeOf(p)} · ${whenOf(p)}`),
      h('button', { class: 'close', type: 'button', 'aria-label': 'Bağla', onclick: () => dialog.close() }, '×')),
    h('div', { class: 'd-body' },
      h('h3', {}, 'Bal'),
      s.eligible
        ? [h('div', { class: `bars ${tier(s)}` },
          bar('Ümumi bal', s.total, 'total'), bar('Qəbul şansı', s.chance, ''), bar('Sənə uyğunluq', s.fit, '')),
        h('ul', { class: 'factors' }, s.factors.map(factorRow))]
        : h('p', {}, `Uyğun deyil: ${s.factors[0].t}.`),
      (ai.summary_az || p.description) && [h('h3', {}, 'Xülasə'), h('p', {}, ai.summary_az || p.description)],
      h('h3', {}, 'Əsas məlumat'),
      h('dl', { class: 'facts' },
        fact('Son müraciət tarixi', fmt(p.deadline)),
        fact('Xərclər', costSummary(c)),
        fact('İştirak haqqı', c.fee_note ? `${fee} — ${c.fee_note}` : fee),
        fact('Yaş', ages), fact('Yerlər', spots), fact('Təşkilatçı', p.organizer),
        fact('İngilis dili tələbi', ai.required_english),
        fact('Rəqabət (AI təxmini)', ai.competition && [COMPETITION[ai.competition], ai.competition_reason].filter(Boolean).join(' — ')),
        fact('Seçim prosesi', ai.selection_process)),
      needs.length && [h('h3', {}, 'Müraciət üçün lazımdır'), h('ul', { class: 'need' }, needs.map((n) => h('li', {}, n)))],
      (p.flashcards || []).length && [h('h3', {}, 'Flashcard-lar — cavab üçün kartı bas'),
        h('div', { class: 'cards' }, p.flashcards.map(flashcard))],
      who && [h('h3', {}, 'Müraciət edə bilən ölkələr'), h('p', { class: 'countries' }, who)],
      h('div', { class: 'd-foot' },
        url && h('a', { class: 'btn', href: url, target: '_blank', rel: 'noopener noreferrer' }, 'Layihə səhifəsini aç'),
        h('small', {}, p.analysis === 'ai'
          ? 'Tələblər AI ilə çıxarılıb — müraciətdən əvvəl mənbədə yoxla.'
          : 'AI analizi hələ aparılmayıb — məlumat səhifədən avtomatik oxunub.'))));
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}

function route() {
  const dialog = $('#detail');
  const project = state.projects.find((p) => p.id === location.hash.slice(1));
  if (project) openDetail(project);
  else if (dialog.open) dialog.close();
}

/* ---------- wiring ---------- */

function notices() {
  const items = [];
  if (!state.meta.profile_set) {
    items.push('Profil doldurulmayıb: yaş həddi yoxlanmır və bal ümumi fərziyyələrlə hesablanır (profile.json).');
  }
  if (!state.meta.ai_enabled) {
    items.push('AI analizi aktiv deyil: flashcard-lar yalnız səhifədən oxunan sahələrə əsaslanır.');
  }
  $('#notices').replaceChildren(...items.map((text) => h('p', { class: 'notice' }, text)));
}

function bind(id, key, event = 'change') {
  const input = $(`#${id}`);
  const read = () => (input.type === 'checkbox' ? input.checked : input.value);
  if (input.type === 'checkbox') input.checked = state.f[key];
  else input.value = state.f[key];
  input.addEventListener(event, () => {
    state.f[key] = read();
    refreshOptions();
    try { localStorage.setItem(FILTER_KEY, JSON.stringify(state.f)); } catch { /* storage unavailable */ }
    render();
  });
}

async function start() {
  try { Object.assign(state.f, JSON.parse(localStorage.getItem(FILTER_KEY) || '{}')); } catch { /* ignore */ }
  try {
    const response = await fetch('data/projects.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(response.status);
    const data = await response.json();
    state.projects = data.projects || [];
    state.meta = data.meta || {};
  } catch {
    $('#results').replaceChildren(h('li', { class: 'empty' },
      'Məlumat hələ yüklənməyib. Toplayıcını bir dəfə işə sal: python -m radar run'));
    return;
  }
  const updated = state.meta.updated_at && new Date(state.meta.updated_at);
  if (updated) {
    const time = updated.toLocaleTimeString('az', { hour: '2-digit', minute: '2-digit' });
    $('#updated').textContent = `Son yenilənmə: ${updated.getDate()} ${MONTHS[updated.getMonth()]}, ${time}`;
  }
  notices();
  refreshOptions();
  bind('q', 'q', 'input');
  ['country', 'month', 'type', 'dur', 'sort', 'onlyHome', 'noFee'].forEach((id) => bind(id, id));
  $('#search').addEventListener('submit', (event) => {
    event.preventDefault();
    $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  const dialog = $('#detail');
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  });
  window.addEventListener('hashchange', route);
  render();
  route();
}

start();
