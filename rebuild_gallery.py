#!/usr/bin/env python3
import json
import math
import html
import re
from pathlib import Path
from datetime import datetime

from gallery_index import CATEGORY_LABELS, build_entries_index, normalize_entry_metadata

BASE = Path('/home/lukafinzgar/projects/.caller_tasks/artists')
RUNS_DIR = BASE / 'runs'
PUBLIC_ROOT = Path('/home/lukafinzgar/projects/.caller_tasks/artists-infographic-archive/docs')
LEGACY_IMPORTED = BASE / 'imported_legacy_entries.json'
LATEST_META = PUBLIC_ROOT / 'latest.json'
ENTRIES_INDEX = PUBLIC_ROOT / 'entries.json'
PER_PAGE = 10
KOFI_ICON_FILENAME = 'kofi_stroke_cup.svg'
KOFI_ICON_SVG = '''<svg id="Layer_1" data-name="Layer 1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 13.12"><defs><style>.cls-1{fill:#fff;stroke:#323a47;stroke-linecap:round;stroke-linejoin:round;}.cls-2{fill:#ff5e5b;}</style></defs><title>Kofi_logo_RGB_Outline copy</title><g id="layer1"><g id="g40"><g id="g4184"><path id="path38" class="cls-1" d="M15.54,7.29a5.87,5.87,0,0,1-1.33,0V2.82h.9a2,2,0,0,1,2.06,2.09,2.21,2.21,0,0,1-1.63,2.38m3.87-3.15a4.34,4.34,0,0,0-1.78-2.8A4.8,4.8,0,0,0,14.91.5H1.17a.72.72,0,0,0-.67.71s0,.15,0,.15,0,6.08,0,9.33A2,2,0,0,0,2.58,12.6l9.28,0a3,3,0,0,0,.42-.05,2.65,2.65,0,0,0,1.87-2.91c3.44.19,5.87-2.24,5.26-5.47"/><path id="path42" class="cls-2" d="M7.24,10.08a.19.19,0,0,0,.24,0s2.19-2,3.17-3.14a2.1,2.1,0,0,0-.57-3.41,2.57,2.57,0,0,0-2.74.76A2.41,2.41,0,0,0,3.89,4,2.43,2.43,0,0,0,4,6.88C4.49,7.6,6.8,9.66,7.15,10l.09.07"/></g></g></g></svg>'''

PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def dedupe_entries(entries):
    best = {}
    for e in entries:
        key = (e.get('date', ''), e.get('filename', ''))
        if key not in best:
            best[key] = e
            continue
        current = best[key]
        cur_score = (
            1 if current.get('sources') else 0,
            1 if current.get('_kind') == 'native' else 0,
            len(current.get('person', '')),
        )
        new_score = (
            1 if e.get('sources') else 0,
            1 if e.get('_kind') == 'native' else 0,
            len(e.get('person', '')),
        )
        if new_score > cur_score:
            best[key] = e
    return list(best.values())


def source_count_label(e):
    count = e.get('source_count', len(e.get('sources', [])))
    if count == 1:
        return '1 vir'
    return f'{count} viri' if count else 'Brez virov'


def page_filename(page_num: int) -> str:
    return 'index.html' if page_num == 1 else f'page-{page_num}.html'


def page_link(page_num: int) -> str:
    return './' if page_num == 1 else page_filename(page_num)


def render_pagination(current: int, total: int) -> str:
    if total <= 1:
        return ''
    links = []
    if current > 1:
        links.append(f'<a class="pill pager" href="{page_link(current-1)}">← Prejšnja</a>')
    for p in range(1, total + 1):
        cls = 'pill pager active' if p == current else 'pill pager'
        links.append(f'<a class="{cls}" href="{page_link(p)}">{p}</a>')
    if current < total:
        links.append(f'<a class="pill pager" href="{page_link(current+1)}">Naslednja →</a>')
    return '<nav class="pagination">' + ''.join(links) + '</nav>'


def render_sources(e):
    sources = e.get('sources', [])
    if not sources:
        return ''
    items = ''.join(
        f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">vir</a></li>'
        for url in sources[:4]
    )
    return f'<ul class="sources">{items}</ul>'


def render_masonry_card(e, featured=False):
    person = html.escape(e.get('person', ''))
    filename = html.escape(e.get('filename', ''))
    date = html.escape(e.get('date', ''))
    category = e.get('category_label', 'Znanstvenik')
    category_cls = e.get('category_class', 'science')
    language_label = html.escape(e.get('language_label', 'SL'))
    count_label = source_count_label(e)
    feature_cls = ' feature' if featured else ''
    return f'''<article class="card{feature_cls}" data-person="{html.escape(e.get('person', ''))}" data-category="{html.escape(e.get('category', ''))}" data-language="{html.escape(e.get('language', 'sl'))}">
  <a class="thumb" href="{filename}"><img src="{filename}" alt="Infografika: {person}" loading="lazy"></a>
  <div class="content">
    <div class="meta-row">
      <span class="tag date">{date}</span>
      <span class="tag {category_cls}">{html.escape(category)}</span>
      <span class="tag language">{language_label}</span>
      <span class="tag source-count">{count_label}</span>
    </div>
    <h3>{person}</h3>
    <p class="direct-link"><a href="{filename}">Odpri sliko</a></p>
    {render_sources(e)}
  </div>
</article>'''


def render_featured(featured):
    if not featured:
        return ''
    person = html.escape(featured.get('person', ''))
    date = html.escape(featured.get('date', ''))
    category_label = html.escape(featured.get('category_label', 'Znanstvenik'))
    category_class = featured.get('category_class', 'science')
    language_label = html.escape(featured.get('language_label', 'SL'))
    count_label = source_count_label(featured)
    featured_file = html.escape(featured.get('filename', ''))
    return f'''<section class="hero">
  <div class="hero-copy surface">
    <div>
      <div class="eyebrow">Današnja slika</div>
      <h2>Vsak dan nova infografika o znanih umetnikih, znanstvenikih in športnikih.</h2>
      <p class="intro">Javni arhiv zbira dnevno ustvarjene izobraževalne infografike za otroke. Spodaj lahko hitro iščeš, filtriraš in prelistaš starejše objave kot moderno galerijo slik.</p>
    </div>
    <div>
    </div>
  </div>
  <article class="hero-card surface">
    <a class="hero-image-wrap" href="{featured_file}">
      <img src="{featured_file}" alt="Infografika: {person}">
    </a>
    <div class="meta-row hero-meta">
      <span class="tag date">{date}</span>
      <span class="tag {category_class}">{category_label}</span>
      <span class="tag language">{language_label}</span>
      <span class="tag source-count">{count_label}</span>
    </div>
    <h3>{person}</h3>
    <p class="hero-link"><a href="{featured_file}">Odpri današnjo sliko</a></p>
    {render_sources(featured)}
  </article>
</section>'''


def render_filter_bar(index_summary):
    category_options = ''.join(
        f'<option value="{html.escape(category)}">{html.escape(CATEGORY_LABELS.get(category, (category.title(),))[0])}</option>'
        for category in index_summary.get('categories', [])
    )
    language_options = ''.join(
        f'<option value="{html.escape(language)}">{html.escape(language.upper())}</option>'
        for language in index_summary.get('languages', [])
    )
    return f'''<div class="filter-bar">
  <div class="filter-control">
    <label for="archive-search">Išči po osebi</label>
    <input id="archive-search" type="search" placeholder="npr. Duke Ellington">
  </div>
  <div class="filter-control">
    <label for="archive-category">Vrsta</label>
    <select id="archive-category">
      <option value="">Vse vrste</option>
      {category_options}
    </select>
  </div>
  <div class="filter-control">
    <label for="archive-language">Jezik</label>
    <select id="archive-language">
      <option value="">Vsi jeziki</option>
      {language_options}
    </select>
  </div>
</div>
<p id="results-summary" class="results-summary">Prikazan je začetni izbor za to stran. Za iskanje ali filtriranje uporabi polja zgoraj.</p>'''


def render_client_script():
    return '''<script>
(function () {
  const masonry = document.querySelector('.masonry');
  const pagination = document.querySelector('.pagination');
  const summary = document.getElementById('results-summary');
  const searchInput = document.getElementById('archive-search');
  const categorySelect = document.getElementById('archive-category');
  const languageSelect = document.getElementById('archive-language');
  if (!masonry || !summary || !searchInput || !categorySelect || !languageSelect) return;

  const initialMarkup = masonry.innerHTML;
  let entries = [];

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function sourceCountLabel(count) {
    if (count === 1) return '1 vir';
    return count ? `${count} viri` : 'Brez virov';
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return '';
    return `<ul class="sources">${sources.slice(0, 4).map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">vir</a></li>`).join('')}</ul>`;
  }

  function renderCard(entry, featured) {
    const featureClass = featured ? ' feature' : '';
    return `<article class="card${featureClass}" data-person="${escapeHtml(entry.person)}" data-category="${escapeHtml(entry.category)}" data-language="${escapeHtml(entry.language)}">
      <a class="thumb" href="${escapeHtml(entry.filename)}"><img src="${escapeHtml(entry.filename)}" alt="Infografika: ${escapeHtml(entry.person)}" loading="lazy"></a>
      <div class="content">
        <div class="meta-row">
          <span class="tag date">${escapeHtml(entry.date)}</span>
          <span class="tag ${escapeHtml(entry.category_class)}">${escapeHtml(entry.category_label)}</span>
          <span class="tag language">${escapeHtml(entry.language_label)}</span>
          <span class="tag source-count">${sourceCountLabel(entry.source_count)}</span>
        </div>
        <h3>${escapeHtml(entry.person)}</h3>
        <p class="direct-link"><a href="${escapeHtml(entry.filename)}">Odpri sliko</a></p>
        ${renderSources(entry.sources || [])}
      </div>
    </article>`;
  }

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    const category = categorySelect.value;
    const language = languageSelect.value;
    const hasFilters = Boolean(query || category || language);

    if (!hasFilters) {
      masonry.innerHTML = initialMarkup;
      summary.textContent = 'Prikazan je začetni izbor za to stran. Za iskanje ali filtriranje uporabi polja zgoraj.';
      if (pagination) pagination.classList.remove('is-hidden');
      return;
    }

    const filtered = entries.filter((entry) => {
      if (query && !entry.search_text.includes(query)) return false;
      if (category && entry.category !== category) return false;
      if (language && entry.language !== language) return false;
      return true;
    });

    masonry.innerHTML = filtered.length
      ? filtered.map((entry, index) => renderCard(entry, index % 4 === 0)).join('')
      : '<p class="empty">Za izbrane filtre ni zadetkov.</p>';
    summary.textContent = `Najdenih zadetkov: ${filtered.length}`;
    if (pagination) pagination.classList.add('is-hidden');
  }

  fetch('entries.json')
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('entries.json fetch failed')))
    .then((data) => {
      entries = data.entries || [];
      searchInput.addEventListener('input', applyFilters);
      categorySelect.addEventListener('change', applyFilters);
      languageSelect.addEventListener('change', applyFilters);
    })
    .catch(() => {
      summary.textContent = 'Iskanje in filtri trenutno niso na voljo.';
    });
})();
</script>'''


def render_page(page_num: int, total_pages: int, chunk, featured=None):
    page_heading = 'Arhiv kot moderna galerija' if page_num == 1 else f'Arhiv – stran {page_num}'
    page_intro = (
        'Išči po osebi ter filtriraj po vrsti in jeziku.'
        if page_num == 1 else
        'Prelistaj starejše dnevne infografike po straneh ali uporabi iskanje in filtre.'
    )
    updated = datetime.now().strftime('%Y-%m-%d %H:%M')
    cards = '\n'.join(
        render_masonry_card(e, featured=(page_num == 1 and idx in (0, 3)))
        for idx, e in enumerate(chunk)
    ) if chunk else '<p class="empty">Na tej strani še ni slik.</p>'
    featured_html = render_featured(featured) if page_num == 1 and featured else ''
    pagination = render_pagination(page_num, total_pages)
    filters_html = render_filter_bar(entries_index['summary'])
    client_script = render_client_script()
    title_suffix = 'Današnja slika in arhiv' if page_num == 1 else f'Arhiv – stran {page_num}'
    return f'''<!doctype html>
<html lang="sl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arhiv dnevnih rojstnodnevnih infografik – {title_suffix}</title>
  <meta name="description" content="Dnevno ustvarjene slovenske infografike o znanih umetnikih in znanstvenikih za otroke.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap" rel="stylesheet">
  <style>
    :root {{
      color-scheme: light;
      --bg:#faf7f2;
      --paper:#fffdf9;
      --panel:#ffffff;
      --ink:#211922;
      --muted:#6f6a62;
      --line:#e6ddd0;
      --accent:#e60023;
      --chip:#f1ece4;
      --hero1:#ffe0c4;
      --hero2:#d8f1ff;
      --hero3:#e7ddff;
      --green:#d9f3df;
      --shadow:0 12px 32px rgba(33,25,34,.08);
      --radius:24px;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      background:
        radial-gradient(circle at top left, rgba(255,224,196,.65), transparent 24%),
        radial-gradient(circle at 90% 0%, rgba(216,241,255,.75), transparent 22%),
        linear-gradient(180deg,#fffdfa,var(--bg));
      color:var(--ink);
      font-family:'DM Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    }}
    a {{ color:inherit; }}
    .wrap {{ max-width:1440px; margin:0 auto; padding:24px 20px 60px; }}
    .surface {{ background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }}
    .nav {{
      position:sticky; top:18px; z-index:10;
      display:flex; justify-content:space-between; align-items:center; gap:20px;
      padding:16px 18px; background:rgba(255,253,249,.86); backdrop-filter:blur(14px);
      border:1px solid rgba(230,221,208,.9); border-radius:22px; box-shadow:var(--shadow);
    }}
    .brand {{ display:flex; align-items:center; gap:14px; }}
    .logo {{ width:46px; height:46px; border-radius:16px; background:linear-gradient(135deg,var(--hero1),var(--hero3)); display:grid; place-items:center; font-size:23px; }}
    .brand h1 {{ margin:0; font-size:18px; line-height:1.1; }}
    .brand p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
    .nav-actions, .hero-chips, .archive-filters, .meta-row, .pagination {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .pill {{ display:inline-flex; align-items:center; gap:8px; padding:10px 14px; border-radius:999px; background:var(--chip); border:1px solid #e4dbce; font-size:14px; color:#3f3933; text-decoration:none; }}
    .pill.primary {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:700; }}
    .pill.soft {{ background:rgba(255,255,255,.72); }}
    .support-note {{ max-width:360px; text-align:right; color:var(--muted); font-size:13px; line-height:1.35; }}
    .support-note a {{ color:var(--accent); font-weight:800; text-decoration:none; }}
    .support-note a:hover {{ text-decoration:underline; }}
    .kofi-link {{ display:inline-flex; align-items:center; gap:5px; }}
    .kofi-icon {{ width:22px; height:auto; display:inline-block; }}
    .hero {{ margin-top:24px; display:grid; grid-template-columns:1.1fr .9fr; gap:20px; align-items:stretch; }}
    .hero-copy {{ padding:34px 34px 30px; display:flex; flex-direction:column; justify-content:space-between; }}
    .eyebrow {{ font-size:12px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#8a5c09; display:inline-flex; align-items:center; gap:8px; }}
    .eyebrow::before {{ content:''; width:10px; height:10px; border-radius:999px; background:linear-gradient(135deg,#ff9d00,#ff4d6d); }}
    .hero-copy h2 {{ font-size:clamp(42px,6vw,76px); line-height:.93; letter-spacing:-.05em; margin:14px 0 16px; max-width:11ch; }}
    .intro {{ margin:0; color:var(--muted); font-size:20px; line-height:1.5; max-width:31ch; }}
    .hero-stats {{ margin-top:26px; display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
    .stat {{ background:var(--paper); border:1px solid var(--line); border-radius:22px; padding:18px 16px; }}
    .stat strong {{ display:block; font-size:30px; margin-bottom:4px; }}
    .stat span {{ font-size:14px; color:var(--muted); }}
    .hero-card {{ padding:18px; background:linear-gradient(180deg,#fff,#fffaf4); }}
    .hero-image-wrap {{ display:block; padding:12px; background:linear-gradient(135deg,var(--hero2),var(--hero1),var(--hero3)); border-radius:26px; text-decoration:none; }}
    .hero-image-wrap img {{ width:100%; display:block; border-radius:20px; border:8px solid rgba(255,255,255,.96); }}
    .hero-meta {{ margin-top:18px; }}
    .hero-card h3 {{ margin:16px 0 8px; font-size:32px; letter-spacing:-.03em; }}
    .hero-link a, .direct-link a {{ color:var(--accent); font-weight:700; text-decoration:none; }}
    .hero-link a:hover, .direct-link a:hover, .sources a:hover {{ text-decoration:underline; }}
    .archive-shell {{ margin-top:24px; padding:24px; background:rgba(255,255,255,.84); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }}
    .archive-top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px; }}
    .archive-top h2 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}
    .archive-top p {{ margin:8px 0 0; color:var(--muted); font-size:17px; max-width:60ch; }}
    .masonry {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:16px; align-items:stretch; }}
    .card {{
      margin:0; background:var(--panel); border:1px solid var(--line);
      border-radius:22px; overflow:hidden; box-shadow:0 8px 24px rgba(33,25,34,.06);
      height:100%; display:flex; flex-direction:column;
    }}
    .card.feature {{ background:linear-gradient(180deg,#fffefb,#fff7ee); }}
    .thumb {{ display:block; text-decoration:none; }}
    .thumb img {{ width:100%; display:block; }}
    .content {{ padding:14px 14px 16px; flex:1; display:flex; flex-direction:column; }}
    .content h3 {{ margin:8px 0 8px; font-size:22px; line-height:1.08; letter-spacing:-.03em; min-height:2.16em; display:block; }}
    .card.feature .content h3 {{ font-size:28px; min-height:2.16em; }}
    .tag {{ display:inline-flex; padding:7px 10px; border-radius:999px; background:#f7f2ea; border:1px solid #ece1d4; font-size:12px; color:#564f47; }}
    .tag.artist {{ background:#ffe9ec; border-color:#ffd4dc; color:#8d2440; }}
    .tag.science {{ background:#eaf5ff; border-color:#d4e7ff; color:#29547f; }}
    .tag.sport {{ background:#fff1d6; border-color:#ffe2a8; color:#8a5c09; }}
    .tag.language {{ background:#f1ecff; border-color:#ddd3ff; color:#55408d; }}
    .tag.source-count {{ background:#eaf8ee; border-color:#d9efd9; color:#2b6a3c; }}
    .filter-bar {{ display:grid; grid-template-columns:minmax(220px, 1.6fr) repeat(2, minmax(160px, .8fr)); gap:12px; margin:0 0 18px; }}
    .filter-control {{ display:flex; flex-direction:column; gap:6px; }}
    .filter-control label {{ font-size:13px; color:var(--muted); font-weight:700; }}
    .filter-control input, .filter-control select {{
      width:100%; padding:12px 14px; border-radius:16px; border:1px solid var(--line);
      background:#fff; color:var(--ink); font:inherit;
    }}
    .results-summary {{ margin:0 0 14px; color:var(--muted); font-size:14px; }}
    .sources {{ list-style:none; display:flex; flex-wrap:wrap; gap:8px; padding:0; margin:12px 0 0; }}
    .direct-link {{ margin-top:auto; }}
    .sources a {{ display:inline-flex; padding:7px 10px; border-radius:999px; text-decoration:none; background:#faf7f2; border:1px solid var(--line); color:#594e44; font-size:12px; }}
    .pagination {{ margin-top:22px; justify-content:flex-end; }}
    .pagination.is-hidden {{ display:none; }}

    .footer {{ margin-top:20px; padding:18px 22px; display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:14px; }}
    .empty {{ color:var(--muted); font-size:16px; }}
    @media (max-width:1200px) {{
      .masonry {{ grid-template-columns:repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width:1100px) {{
      .hero {{ grid-template-columns:1fr; }}
      .hero-stats {{ grid-template-columns:1fr 1fr; }}
      .masonry {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width:700px) {{
      .nav {{ position:static; flex-direction:column; align-items:stretch; }}
      .support-note {{ max-width:none; text-align:left; }}
      .archive-top, .footer {{ flex-direction:column; align-items:flex-start; }}
      .pagination {{ justify-content:flex-start; }}
      .hero-copy {{ padding:26px; }}
      .intro {{ font-size:18px; }}
      .hero-stats {{ grid-template-columns:1fr; }}
      .wrap {{ padding:18px 14px 44px; }}
      .filter-bar {{ grid-template-columns:1fr; }}
      .masonry {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="nav">
      <div class="brand">
        <div class="logo">🖼️</div>
        <div>
          <h1>Arhiv dnevnih rojstnodnevnih infografik</h1>
          <p>Dnevno ustvarjene slovenske infografike za otroke</p>
        </div>
      </div>
      <p class="support-note"><a class="kofi-link" href="https://ko-fi.com/lukafinzgar" target="_blank" rel="noopener noreferrer" aria-label="Podpri avtorja strani na Ko-fi"><img class="kofi-icon" src="kofi_stroke_cup.svg" alt="Ko-fi"><span>Podpri avtorja strani</span></a></p>
    </header>
    {featured_html}
    <section class="archive-shell">
      <div class="archive-top">
        <div>
          <h2>{page_heading}</h2>
          <p>{page_intro}</p>
        </div>
        <div class="archive-filters">
          <span class="pill">Skupaj: {len(entries)}</span>
          <span class="pill">Stran {page_num}/{total_pages}</span>
        </div>
      </div>
      {filters_html}
      <div class="masonry">{cards}</div>
      {pagination}
    </section>
    <footer class="footer surface">
      <div>Javni arhiv dnevnih infografik o znanih umetnikih, znanstvenikih in športnikih.</div>
      <div>Posodobljeno: {html.escape(updated)}</div>
    </footer>
  </main>
  {client_script}
</body>
</html>'''


entries = []
for e in load_json(LEGACY_IMPORTED, []):
    e['_kind'] = 'legacy'
    entries.append(e)

for entry_path in sorted(RUNS_DIR.glob('*/entry.json')):
    entry = load_json(entry_path, None)
    if isinstance(entry, dict):
        entry['_kind'] = 'native'
        entries.append(entry)

entries = [normalize_entry_metadata(entry) for entry in dedupe_entries(entries)]
entries.sort(key=lambda x: ((x.get('date') or ''), (x.get('person') or ''), (x.get('filename') or '')), reverse=True)
entries_index = build_entries_index(entries)

featured = entries[0] if entries else None
archive_entries = entries[1:] if len(entries) > 1 else []
if featured and featured.get('date'):
    archive_entries = [e for e in archive_entries if e.get('date') != featured.get('date')]

ENTRIES_INDEX.write_text(json.dumps(entries_index, ensure_ascii=False, indent=2), encoding='utf-8')
(PUBLIC_ROOT / KOFI_ICON_FILENAME).write_text(KOFI_ICON_SVG + '\n', encoding='utf-8')

total_pages = max(1, math.ceil(len(archive_entries) / PER_PAGE))

for page_num in range(1, total_pages + 1):
    start = (page_num - 1) * PER_PAGE
    end = start + PER_PAGE
    chunk = archive_entries[start:end]
    html_doc = render_page(page_num, total_pages, chunk, featured=featured)
    (PUBLIC_ROOT / page_filename(page_num)).write_text(html_doc, encoding='utf-8')

for stale in PUBLIC_ROOT.glob('page-*.html'):
    m = re.match(r'page-(\d+)\.html$', stale.name)
    if m and int(m.group(1)) > total_pages:
        stale.unlink()

if isinstance(featured, dict):
    LATEST_META.write_text(json.dumps({
        'date': featured.get('date'),
        'person': featured.get('person'),
        'image_filename': featured.get('filename'),
        'category': featured.get('category'),
        'category_label': featured.get('category_label'),
        'language': featured.get('language'),
        'language_label': featured.get('language_label'),
        'sources': featured.get('sources', []),
        'total_entries': len(entries),
        'total_pages': total_pages,
        'per_page': PER_PAGE,
    }, ensure_ascii=False, indent=2), encoding='utf-8')

print(json.dumps({
    'entries': len(entries),
    'featured': featured.get('person') if featured else None,
    'archive_entries': len(archive_entries),
    'pages': total_pages,
    'per_page': PER_PAGE,
    'files': [page_filename(i) for i in range(1, total_pages + 1)]
}, ensure_ascii=False))
