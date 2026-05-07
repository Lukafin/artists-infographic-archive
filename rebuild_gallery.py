#!/usr/bin/env python3
import json
import math
import html
import re
from pathlib import Path
from datetime import datetime

from gallery_index import AGE_SUITABILITY_LEVELS, CATEGORY_LABELS, build_entries_index, normalize_entry_metadata

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




def validate_entry_provenance(entries):
    placeholder = []
    for entry in entries:
        sources = [str(source).strip().lower() for source in entry.get('sources', []) if str(source).strip()]
        if sources and all('://example.com/' in source or source.startswith('https://example.com/') for source in sources):
            label = f"{entry.get('date', 'unknown-date')} {entry.get('person', 'unknown-person')}"
            placeholder.append(f"{label}: {entry.get('filename', 'unknown-file')} -> {', '.join(entry.get('sources', []))}")
    if placeholder:
        raise SystemExit(
            'Refusing to rebuild artists archive with placeholder example.com sources.\n'
            'These entries are usually test/demo artifacts and can publish wrong dates for reused images.\n'
            '- ' + '\n- '.join(placeholder)
        )
    return entries


def validate_entry_assets(entries):
    missing = []
    invalid = []
    for entry in entries:
        filename = (entry.get('filename') or '').strip()
        label = f"{entry.get('date', 'unknown-date')} {entry.get('person', 'unknown-person')}"
        if not filename:
            invalid.append(f"{label}: empty filename")
            continue
        filename_path = Path(filename)
        if filename_path.is_absolute() or '..' in filename_path.parts:
            invalid.append(f"{label}: unsafe filename {filename!r}")
            continue
        if not (PUBLIC_ROOT / filename_path).is_file():
            missing.append(f"{label}: {filename}")
    if invalid or missing:
        details = []
        if invalid:
            details.append('Invalid archive image filenames:\n- ' + '\n- '.join(invalid))
        if missing:
            details.append('Missing archive image files under ' + str(PUBLIC_ROOT) + ':\n- ' + '\n- '.join(missing))
        raise SystemExit('Refusing to rebuild artists archive with broken image references.\n' + '\n'.join(details))
    return entries


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
        return '1 source'
    return f'{count} sources' if count else 'No sources'


def age_suitability_badge(e):
    keys = e.get('age_suitability_keys') or []
    if not keys:
        return ''
    label = ', '.join(AGE_SUITABILITY_LEVELS.get(key, {}).get('label_en', key) for key in keys)
    return f'<span class="tag age" data-age-tag="1">{html.escape(label)}</span>'


def age_suitability_data(e):
    return ' '.join(e.get('age_suitability_keys') or [])


def category_label_en(category: str) -> str:
    return {
        'artist': 'Artist',
        'scientist': 'Scientist',
        'sport': 'Athlete',
    }.get(category, category.title() if category else 'Scientist')


def page_filename(page_num: int) -> str:
    return 'index.html' if page_num == 1 else f'page-{page_num}.html'


def page_link(page_num: int) -> str:
    return './' if page_num == 1 else page_filename(page_num)


def render_pagination(current: int, total: int) -> str:
    if total <= 1:
        return ''
    links = []
    if current > 1:
        links.append(f'<a class="pill pager" href="{page_link(current-1)}" data-i18n="pager_previous">← Previous</a>')
    for p in range(1, total + 1):
        cls = 'pill pager active' if p == current else 'pill pager'
        links.append(f'<a class="{cls}" href="{page_link(p)}">{p}</a>')
    if current < total:
        links.append(f'<a class="pill pager" href="{page_link(current+1)}" data-i18n="pager_next">Next →</a>')
    return '<nav class="pagination">' + ''.join(links) + '</nav>'


def render_sources(e):
    sources = e.get('sources', [])
    if not sources:
        return ''
    items = ''.join(
        f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer" data-source-link="1">source</a></li>'
        for url in sources[:4]
    )
    return f'<ul class="sources">{items}</ul>'


def render_info_overlay(e, panel_id, expanded=False):
    raw_date = e.get('date', '')
    date = html.escape(raw_date)
    display_date = html.escape(format_display_date(raw_date))
    category = category_label_en(e.get('category', 'scientist'))
    category_cls = e.get('category_class', 'science')
    language_label = html.escape(e.get('language_label', 'SL'))
    count_label = source_count_label(e)
    age_badge = age_suitability_badge(e)
    open_attr = ' open' if expanded else ''
    return f'''<details class="info-popover"{open_attr}>
      <summary class="info-button" aria-label="Show image details" data-info-label="1">i</summary>
      <div class="info-panel" id="{html.escape(panel_id)}">
        <div class="meta-row">
          <time class="tag date" datetime="{date}" data-date="{date}">{display_date}</time>
          <span class="tag {category_cls}" data-category-tag="{html.escape(e.get('category', ''))}">{html.escape(category)}</span>
          <span class="tag language">{language_label}</span>
          {age_badge}
          <span class="tag source-count" data-source-count="{e.get('source_count', len(e.get('sources', [])))}">{count_label}</span>
        </div>
        {render_sources(e)}
      </div>
    </details>'''


def format_display_date(value):
    if not value:
        return ''
    try:
        parsed = datetime.strptime(str(value)[:10], '%Y-%m-%d')
    except ValueError:
        return str(value)
    return f'{parsed.day}. {parsed.month}. {parsed.year}'


def format_display_datetime(value):
    if not value:
        return ''
    try:
        parsed = datetime.strptime(str(value), '%Y-%m-%d %H:%M')
    except ValueError:
        return str(value)
    return f'{parsed.day}. {parsed.month}. {parsed.year}, {parsed:%H:%M}'


def render_masonry_card(e, featured=False):
    person = html.escape(e.get('person', ''))
    filename = html.escape(e.get('filename', ''))
    age_data = html.escape(age_suitability_data(e))
    feature_cls = ' feature' if featured else ''
    panel_id = 'info-' + re.sub(r'[^a-zA-Z0-9_-]+', '-', f"{e.get('date', '')}-{e.get('filename', '')}").strip('-')
    return f'''<article class="card{feature_cls}" data-person="{html.escape(e.get('person', ''))}" data-category="{html.escape(e.get('category', ''))}" data-language="{html.escape(e.get('language', 'sl'))}" data-age-suitability="{age_data}">
  <a class="thumb" href="{filename}" aria-label="Open infographic: {person}"><img src="{filename}" alt="Infographic: {person}" loading="lazy"></a>
  <div class="image-title">
    <h3>{person}</h3>
  </div>
  {render_info_overlay(e, panel_id)}
</article>'''


def render_featured(featured):
    if not featured:
        return ''
    person = html.escape(featured.get('person', ''))
    age_data = html.escape(age_suitability_data(featured))
    featured_file = html.escape(featured.get('filename', ''))
    return f'''<section class="hero">
  <div class="hero-copy surface">
    <div>
      <div class="eyebrow" data-i18n="hero_eyebrow">Today’s image</div>
      <h2 data-i18n="hero_title">A new daily infographic about famous artists, scientists and athletes.</h2>
      <p class="intro" data-i18n="hero_intro">This public archive collects educational infographics for all ages. Search, filter and browse older posts as a modern image gallery.</p>
    </div>
    <div>
    </div>
  </div>
  <article class="hero-card surface image-card" data-age-suitability="{age_data}">
    <a class="hero-image-wrap" href="{featured_file}" aria-label="Open infographic: {person}">
      <img src="{featured_file}" alt="Infographic: {person}">
    </a>
    <div class="image-title hero-title-overlay">
      <h3>{person}</h3>
    </div>
    {render_info_overlay(featured, 'featured-info', expanded=True)}
  </article>
</section>'''


def render_filter_bar(index_summary):
    category_options = ''.join(
        f'<option value="{html.escape(category)}" data-category-option="{html.escape(category)}">{html.escape(category_label_en(category))}</option>'
        for category in index_summary.get('categories', [])
    )
    language_options = ''.join(
        f'<option value="{html.escape(language)}">{html.escape(language.upper())}</option>'
        for language in index_summary.get('languages', [])
    )
    age_options = ''.join(
        f'<option value="{html.escape(key)}" data-age-option="{html.escape(key)}">{html.escape(AGE_SUITABILITY_LEVELS.get(key, {}).get("label_en", key))}</option>'
        for key in index_summary.get('age_suitability_levels', AGE_SUITABILITY_LEVELS.keys())
    )
    return f'''<div class="filter-bar">
  <div class="filter-control">
    <label for="archive-search" data-i18n="search_label">Search by person</label>
    <input id="archive-search" type="search" placeholder="e.g. Duke Ellington" data-i18n-placeholder="search_placeholder">
  </div>
  <div class="filter-control">
    <label for="archive-category" data-i18n="category_label">Type</label>
    <select id="archive-category">
      <option value="" data-i18n="category_all">All types</option>
      {category_options}
    </select>
  </div>
  <div class="filter-control">
    <label for="archive-language" data-i18n="image_language_label">Image language</label>
    <select id="archive-language">
      <option value="" data-i18n="language_all">All image languages</option>
      {language_options}
    </select>
  </div>
  <div class="filter-control">
    <label for="archive-age" data-i18n="age_label">Age suitability</label>
    <select id="archive-age">
      <option value="" data-i18n="age_all">All age levels</option>
      {age_options}
    </select>
  </div>
</div>
<p id="results-summary" class="results-summary" data-i18n="initial_summary">Showing the initial selection for this page. Use search or filters above to search the full archive.</p>'''


def render_client_script():
    return r'''<script>
(function () {
  const masonry = document.querySelector('.masonry');
  const pagination = document.querySelector('.pagination');
  const summary = document.getElementById('results-summary');
  const searchInput = document.getElementById('archive-search');
  const categorySelect = document.getElementById('archive-category');
  const languageSelect = document.getElementById('archive-language');
  const ageSelect = document.getElementById('archive-age');
  if (!masonry || !summary || !searchInput || !categorySelect || !languageSelect || !ageSelect) return;

  const initialMarkup = masonry.innerHTML;
  const defaultLang = 'en';
  let uiLang = localStorage.getItem('archive-ui-lang') || defaultLang;
  let entries = [];

  const dict = {
    en: {
      document_title: 'Daily birthday infographic archive',
      brand_title: 'Daily birthday infographic archive',
      brand_subtitle: 'Daily Slovenian infographics for all ages',
      kofi: 'Support the site author',
      hero_eyebrow: 'Today’s image',
      hero_title: 'A new daily infographic about famous artists, scientists and athletes.',
      hero_intro: 'This public archive collects educational infographics for all ages. Search, filter and browse older posts as a modern image gallery.',
      archive_heading_home: 'Archive as a modern gallery',
      archive_heading_page: 'Archive – page {page}',
      archive_intro_home: 'Search by person, type, image language and age suitability.',
      archive_intro_page: 'Browse older daily infographics by page or use search and filters.',
      total_prefix: 'Total:',
      page_prefix: 'Page {page}/{total}',
      search_label: 'Search by person',
      search_placeholder: 'e.g. Duke Ellington',
      category_label: 'Type',
      category_all: 'All types',
      image_language_label: 'Image language',
      language_all: 'All image languages',
      age_label: 'Age suitability',
      age_all: 'All age levels',
      initial_summary: 'Showing the initial selection for this page. Use search or filters above to search the full archive.',
      no_results: 'No results for the selected filters.',
      found: 'Results found: {count}',
      source: 'source',
      sources_zero: 'No sources',
      sources_one: '1 source',
      sources_many: '{count} sources',
      footer_text: 'Public archive of daily infographics about famous artists, scientists and athletes.',
      footer_generated_by: 'Generated by the',
      footer_swarm: 'AI swarm',
      updated: 'Updated:',
      search_unavailable: 'Search and filters are currently unavailable.',
      pager_previous: '← Previous',
      pager_next: 'Next →',
      lang_picker_label: 'Site language',
      category_artist: 'Artist',
      category_scientist: 'Scientist',
      category_sport: 'Athlete',
      age_age_6: 'Ages 6+',
      age_age_13: 'Ages 13+',
      age_adult: 'Adults',
      image_details: 'Show image details'
    },
    sl: {
      document_title: 'Arhiv dnevnih rojstnodnevnih infografik',
      brand_title: 'Arhiv dnevnih rojstnodnevnih infografik',
      brand_subtitle: 'Dnevno ustvarjene slovenske infografike za vse starosti',
      kofi: 'Podpri avtorja strani',
      hero_eyebrow: 'Današnja slika',
      hero_title: 'Vsak dan nova infografika o znanih umetnikih, znanstvenikih in športnikih.',
      hero_intro: 'Javni arhiv zbira dnevno ustvarjene izobraževalne infografike za vse starosti. Spodaj lahko hitro iščeš, filtriraš in prelistaš starejše objave kot moderno galerijo slik.',
      archive_heading_home: 'Arhiv kot moderna galerija',
      archive_heading_page: 'Arhiv – stran {page}',
      archive_intro_home: 'Išči po osebi ter filtriraj po vrsti, jeziku slike in starostni primernosti.',
      archive_intro_page: 'Prelistaj starejše dnevne infografike po straneh ali uporabi iskanje in filtre.',
      total_prefix: 'Skupaj:',
      page_prefix: 'Stran {page}/{total}',
      search_label: 'Išči po osebi',
      search_placeholder: 'npr. Duke Ellington',
      category_label: 'Vrsta',
      category_all: 'Vse vrste',
      image_language_label: 'Jezik slike',
      language_all: 'Vsi jeziki slik',
      age_label: 'Starostna primernost',
      age_all: 'Vse starostne ravni',
      initial_summary: 'Prikazan je začetni izbor za to stran. Za iskanje ali filtriranje celotnega arhiva uporabi polja zgoraj.',
      no_results: 'Za izbrane filtre ni zadetkov.',
      found: 'Najdenih zadetkov: {count}',
      source: 'vir',
      sources_zero: 'Brez virov',
      sources_one: '1 vir',
      sources_many: '{count} viri',
      footer_text: 'Javni arhiv dnevnih infografik o znanih umetnikih, znanstvenikih in športnikih.',
      footer_generated_by: 'Ustvarja jih',
      footer_swarm: 'AI swarm',
      updated: 'Posodobljeno:',
      search_unavailable: 'Iskanje in filtri trenutno niso na voljo.',
      pager_previous: '← Prejšnja',
      pager_next: 'Naslednja →',
      lang_picker_label: 'Jezik strani',
      category_artist: 'Umetnik',
      category_scientist: 'Znanstvenik',
      category_sport: 'Športnik',
      age_age_6: '6+ let',
      age_age_13: '13+ let',
      age_adult: 'Odrasli',
      image_details: 'Pokaži podrobnosti slike'
    }
  };

  function t(key, params) {
    let value = (dict[uiLang] && dict[uiLang][key]) || dict.en[key] || key;
    if (params) {
      Object.entries(params).forEach(([name, replacement]) => {
        value = value.replace(`{${name}}`, replacement);
      });
    }
    return value;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatDate(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return value || '';
    return `${Number(match[3])}. ${Number(match[2])}. ${match[1]}`;
  }

  function formatUpdated(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})/);
    if (!match) return value || '';
    return `${Number(match[3])}. ${Number(match[2])}. ${match[1]}, ${match[4]}`;
  }

  function categoryLabel(category) {
    return t(`category_${category || 'scientist'}`);
  }

  function sourceCountLabel(count) {
    if (count === 1) return t('sources_one');
    return count ? t('sources_many', {count}) : t('sources_zero');
  }

  function ageLabel(key) {
    return t(`age_${key}`);
  }

  function ageBadges(keys) {
    if (!keys || !keys.length) return '';
    return `<span class="tag age" data-age-tag="1">${escapeHtml(keys.map(ageLabel).join(', '))}</span>`;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return '';
    return `<ul class="sources">${sources.slice(0, 4).map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-source-link="1">${escapeHtml(t('source'))}</a></li>`).join('')}</ul>`;
  }

  function renderInfoOverlay(entry) {
    const ageKeys = entry.age_suitability_keys || [];
    return `<details class="info-popover">
      <summary class="info-button" aria-label="${escapeHtml(t('image_details'))}" data-info-label="1">i</summary>
      <div class="info-panel">
        <div class="meta-row">
          <time class="tag date" datetime="${escapeHtml(entry.date)}" data-date="${escapeHtml(entry.date)}">${escapeHtml(formatDate(entry.date))}</time>
          <span class="tag ${escapeHtml(entry.category_class)}" data-category-tag="${escapeHtml(entry.category)}">${escapeHtml(categoryLabel(entry.category))}</span>
          <span class="tag language">${escapeHtml(entry.language_label)}</span>
          ${ageBadges(ageKeys)}
          <span class="tag source-count" data-source-count="${Number(entry.source_count || 0)}">${sourceCountLabel(entry.source_count)}</span>
        </div>
        ${renderSources(entry.sources || [])}
      </div>
    </details>`;
  }

  function renderCard(entry, featured) {
    const featureClass = featured ? ' feature' : '';
    const ageKeys = entry.age_suitability_keys || [];
    return `<article class="card${featureClass}" data-person="${escapeHtml(entry.person)}" data-category="${escapeHtml(entry.category)}" data-language="${escapeHtml(entry.language)}" data-age-suitability="${escapeHtml(ageKeys.join(' '))}">
      <a class="thumb" href="${escapeHtml(entry.filename)}" aria-label="Open infographic: ${escapeHtml(entry.person)}"><img src="${escapeHtml(entry.filename)}" alt="Infographic: ${escapeHtml(entry.person)}" loading="lazy"></a>
      <div class="image-title"><h3>${escapeHtml(entry.person)}</h3></div>
      ${renderInfoOverlay(entry)}
    </article>`;
  }

  function updateStaticTranslations() {
    document.documentElement.lang = uiLang;
    document.title = t('document_title');
    document.querySelectorAll('[data-i18n]').forEach((node) => {
      if (node.id === 'results-summary' && node.dataset.dynamic === 'true') return;
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
      node.setAttribute('placeholder', t(node.dataset.i18nPlaceholder));
    });
    document.querySelectorAll('[data-source-link]').forEach((node) => { node.textContent = t('source'); });
    document.querySelectorAll('[data-info-label]').forEach((node) => { node.setAttribute('aria-label', t('image_details')); });
    document.querySelectorAll('[data-date]').forEach((node) => { node.textContent = formatDate(node.dataset.date); });
    document.querySelectorAll('[data-source-count]').forEach((node) => { node.textContent = sourceCountLabel(Number(node.dataset.sourceCount || 0)); });
    document.querySelectorAll('[data-category-option]').forEach((node) => { node.textContent = categoryLabel(node.dataset.categoryOption); });
    document.querySelectorAll('[data-age-option]').forEach((node) => { node.textContent = ageLabel(node.dataset.ageOption); });
    document.querySelectorAll('[data-category-tag]').forEach((node) => { node.textContent = categoryLabel(node.dataset.categoryTag); });
    document.querySelectorAll('[data-age-tag]').forEach((node) => {
      const parent = node.closest('[data-age-suitability]');
      const keys = parent ? parent.dataset.ageSuitability.split(/\\s+/).filter(Boolean) : [];
      node.textContent = keys.map(ageLabel).join(', ');
    });
    document.querySelectorAll('[data-lang-option]').forEach((button) => {
      const active = button.dataset.langOption === uiLang;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    const totalPill = document.querySelector('[data-total-pill]');
    if (totalPill) totalPill.textContent = `${t('total_prefix')} ${totalPill.dataset.total}`;
    const pagePill = document.querySelector('[data-page-pill]');
    if (pagePill) pagePill.textContent = t('page_prefix', {page: pagePill.dataset.page, total: pagePill.dataset.total});
    const archiveHeading = document.querySelector('[data-archive-heading]');
    if (archiveHeading) archiveHeading.textContent = archiveHeading.dataset.page === '1' ? t('archive_heading_home') : t('archive_heading_page', {page: archiveHeading.dataset.page});
    const archiveIntro = document.querySelector('[data-archive-intro]');
    if (archiveIntro) archiveIntro.textContent = archiveIntro.dataset.page === '1' ? t('archive_intro_home') : t('archive_intro_page');
    const updatedNode = document.querySelector('[data-updated]');
    if (updatedNode) updatedNode.textContent = `${t('updated')} ${formatUpdated(updatedNode.dataset.updated)}`;
  }

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    const category = categorySelect.value;
    const language = languageSelect.value;
    const age = ageSelect.value;
    const hasFilters = Boolean(query || category || language || age);

    if (!hasFilters) {
      masonry.innerHTML = initialMarkup;
      summary.dataset.dynamic = 'false';
      summary.textContent = t('initial_summary');
      if (pagination) pagination.classList.remove('is-hidden');
      updateStaticTranslations();
      return;
    }

    const filtered = entries.filter((entry) => {
      if (query && !entry.search_text.includes(query)) return false;
      if (category && entry.category !== category) return false;
      if (language && entry.language !== language) return false;
      if (age && !(entry.age_suitability_keys || []).includes(age)) return false;
      return true;
    });

    masonry.innerHTML = filtered.length
      ? filtered.map((entry, index) => renderCard(entry, index % 4 === 0)).join('')
      : `<p class="empty">${escapeHtml(t('no_results'))}</p>`;
    summary.dataset.dynamic = 'true';
    summary.textContent = t('found', {count: filtered.length});
    if (pagination) pagination.classList.add('is-hidden');
    updateStaticTranslations();
  }

  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => {
      uiLang = button.dataset.langOption;
      localStorage.setItem('archive-ui-lang', uiLang);
      applyFilters();
    });
  });

  const entriesUrl = new URL('entries.json', window.location.href);
  const pageVersion = new URLSearchParams(window.location.search).get('v');
  if (pageVersion) entriesUrl.searchParams.set('v', pageVersion);
  fetch(entriesUrl.toString(), {cache: 'no-store'})
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('entries.json fetch failed')))
    .then((data) => {
      entries = data.entries || [];
      searchInput.addEventListener('input', applyFilters);
      categorySelect.addEventListener('change', applyFilters);
      languageSelect.addEventListener('change', applyFilters);
      ageSelect.addEventListener('change', applyFilters);
      applyFilters();
    })
    .catch(() => {
      summary.textContent = t('search_unavailable');
      updateStaticTranslations();
    });
})();
</script>'''

def render_page(page_num: int, total_pages: int, chunk, featured=None):
    page_heading = 'Archive as a modern gallery' if page_num == 1 else f'Archive – page {page_num}'
    page_intro = (
        'Search by person, type, image language and age suitability.'
        if page_num == 1 else
        'Browse older daily infographics by page or use search and filters.'
    )
    updated = datetime.now().strftime('%Y-%m-%d %H:%M')
    updated_display = html.escape(format_display_datetime(updated))
    cards = '\n'.join(
        render_masonry_card(e, featured=(page_num == 1 and idx in (0, 3)))
        for idx, e in enumerate(chunk)
    ) if chunk else '<p class="empty">No images on this page yet.</p>'
    featured_html = render_featured(featured) if page_num == 1 and featured else ''
    pagination = render_pagination(page_num, total_pages)
    filters_html = render_filter_bar(entries_index['summary'])
    client_script = render_client_script()
    title_suffix = 'Today’s image and archive' if page_num == 1 else f'Archive – page {page_num}'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily birthday infographic archive – {title_suffix}</title>
  <meta name="description" content="Daily Slovenian infographics for all ages about famous artists, scientists and athletes.">
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
    .nav-right {{ display:flex; align-items:center; justify-content:flex-end; gap:14px; flex-wrap:wrap; }}
    .lang-picker {{ display:inline-flex; align-items:center; gap:6px; padding:6px; border-radius:999px; background:#fff; border:1px solid var(--line); box-shadow:0 6px 18px rgba(33,25,34,.06); }}
    .lang-icon {{ width:22px; height:22px; display:grid; place-items:center; font-size:16px; }}
    .lang-picker button {{ border:0; border-radius:999px; background:transparent; color:#51483f; font:inherit; font-size:12px; font-weight:800; padding:7px 9px; cursor:pointer; }}
    .lang-picker button.active {{ background:var(--ink); color:#fff; }}
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
    .hero-card {{ min-height:420px; }}
    .hero-image-wrap {{ position:absolute; inset:0; display:block; text-decoration:none; background:#fff; }}
    .hero-image-wrap img {{ width:100%; height:100%; display:block; object-fit:contain; }}
    .hero-title-overlay h3 {{ font-size:32px; }}
    .sources a:hover {{ text-decoration:underline; }}
    .archive-shell {{ margin-top:24px; padding:24px; background:rgba(255,255,255,.84); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }}
    .archive-top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px; }}
    .archive-top h2 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}
    .archive-top p {{ margin:8px 0 0; color:var(--muted); font-size:17px; max-width:60ch; }}
    .masonry {{ display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:18px; align-items:stretch; }}
    .card, .image-card {{
      position:relative; isolation:isolate; margin:0; background:#fff; border:1px solid var(--line);
      border-radius:22px; overflow:hidden; box-shadow:0 10px 28px rgba(33,25,34,.08);
      aspect-ratio:16/9;
    }}
    .card.feature {{ box-shadow:0 14px 36px rgba(33,25,34,.11); }}
    .thumb {{ position:absolute; inset:0; display:block; text-decoration:none; background:#fff; }}
    .thumb img {{ width:100%; height:100%; display:block; object-fit:contain; }}
    .image-title {{ position:absolute; left:0; right:0; bottom:0; z-index:2; padding:56px 16px 14px; color:#fff; background:linear-gradient(180deg, transparent, rgba(0,0,0,.68)); pointer-events:none; }}
    .image-title h3 {{ margin:0; font-size:22px; line-height:1.05; letter-spacing:-.03em; text-shadow:0 1px 12px rgba(0,0,0,.38); }}
    .card.feature .image-title h3 {{ font-size:28px; }}
    .info-popover {{ position:absolute; top:12px; right:12px; z-index:4; }}
    .info-popover[open] {{ left:12px; bottom:12px; }}
    .info-popover summary {{ list-style:none; }}
    .info-popover summary::-webkit-details-marker {{ display:none; }}
    .info-button {{ width:38px; height:38px; display:grid; place-items:center; margin-left:auto; border-radius:999px; border:1px solid rgba(255,255,255,.78); background:rgba(255,255,255,.9); color:#211922; font-weight:900; font-size:18px; box-shadow:0 8px 22px rgba(0,0,0,.14); cursor:pointer; }}
    .info-button:hover, .info-button:focus-visible {{ background:#211922; color:#fff; outline:0; }}
    .info-panel {{ margin-top:10px; max-width:min(420px, calc(100vw - 56px)); padding:14px; border-radius:18px; background:rgba(255,253,249,.95); border:1px solid rgba(255,255,255,.9); box-shadow:0 16px 38px rgba(0,0,0,.2); backdrop-filter:blur(16px); }}
    .info-panel .sources {{ margin-top:12px; }}
    .tag {{ display:inline-flex; padding:7px 10px; border-radius:999px; background:#f7f2ea; border:1px solid #ece1d4; font-size:12px; color:#564f47; }}
    .tag.artist {{ background:#ffe9ec; border-color:#ffd4dc; color:#8d2440; }}
    .tag.science {{ background:#eaf5ff; border-color:#d4e7ff; color:#29547f; }}
    .tag.sport {{ background:#fff1d6; border-color:#ffe2a8; color:#8a5c09; }}
    .tag.language {{ background:#f1ecff; border-color:#ddd3ff; color:#55408d; }}
    .tag.age {{ background:#fff7dc; border-color:#ffe7a5; color:#7b5a07; }}
    .tag.source-count {{ background:#eaf8ee; border-color:#d9efd9; color:#2b6a3c; }}
    .filter-bar {{ display:grid; grid-template-columns:minmax(220px, 1.6fr) repeat(3, minmax(150px, .8fr)); gap:12px; margin:0 0 18px; }}
    .filter-control {{ display:flex; flex-direction:column; gap:6px; }}
    .filter-control label {{ font-size:13px; color:var(--muted); font-weight:700; }}
    .filter-control input, .filter-control select {{
      width:100%; padding:12px 14px; border-radius:16px; border:1px solid var(--line);
      background:#fff; color:var(--ink); font:inherit;
    }}
    .results-summary {{ margin:0 0 14px; color:var(--muted); font-size:14px; }}
    .sources {{ list-style:none; display:flex; flex-wrap:wrap; gap:8px; padding:0; margin:12px 0 0; }}
    .sources a {{ display:inline-flex; padding:7px 10px; border-radius:999px; text-decoration:none; background:#faf7f2; border:1px solid var(--line); color:#594e44; font-size:12px; }}
    .pagination {{ margin-top:22px; justify-content:flex-end; }}
    .pagination.is-hidden {{ display:none; }}

    .footer {{ margin-top:20px; padding:18px 22px; display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:14px; }}
    .footer a {{ color:var(--accent); font-weight:800; text-decoration:none; }}
    .footer a:hover {{ text-decoration:underline; }}
    .empty {{ color:var(--muted); font-size:16px; }}
    @media (max-width:1200px) {{
      .masonry {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width:1100px) {{
      .hero {{ grid-template-columns:1fr; }}
      .hero-stats {{ grid-template-columns:1fr 1fr; }}
      .masonry {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width:700px) {{
      .nav {{ position:static; flex-direction:column; align-items:stretch; }}
      .nav-right {{ justify-content:flex-start; }}
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
          <h1 data-i18n="brand_title">Daily birthday infographic archive</h1>
          <p data-i18n="brand_subtitle">Daily Slovenian infographics for all ages</p>
        </div>
      </div>
      <div class="nav-right">
        <div class="lang-picker" role="group" aria-label="Site language">
          <span class="lang-icon" aria-hidden="true">🌐</span>
          <button type="button" class="active" data-lang-option="en" aria-pressed="true">EN</button>
          <button type="button" data-lang-option="sl" aria-pressed="false">SL</button>
        </div>
        <p class="support-note"><a class="kofi-link" href="https://ko-fi.com/lukafinzgar" target="_blank" rel="noopener noreferrer" aria-label="Support the site author on Ko-fi"><img class="kofi-icon" src="kofi_stroke_cup.svg" alt="Ko-fi"><span data-i18n="kofi">Support the site author</span></a></p>
      </div>
    </header>
    {featured_html}
    <section class="archive-shell">
      <div class="archive-top">
        <div>
          <h2 data-archive-heading="1" data-page="{page_num}">{page_heading}</h2>
          <p data-archive-intro="1" data-page="{page_num}">{page_intro}</p>
        </div>
        <div class="archive-filters">
          <span class="pill" data-total-pill="1" data-total="{len(entries)}">Total: {len(entries)}</span>
          <span class="pill" data-page-pill="1" data-page="{page_num}" data-total="{total_pages}">Page {page_num}/{total_pages}</span>
        </div>
      </div>
      {filters_html}
      <div class="masonry">{cards}</div>
      {pagination}
    </section>
    <footer class="footer surface">
      <div><span data-i18n="footer_text">Public archive of daily infographics about famous artists, scientists and athletes.</span> <span data-i18n="footer_generated_by">Generated by the</span> <a href="https://roj.world/swarms/famous-people-infographic" target="_blank" rel="noopener noreferrer" data-i18n="footer_swarm">AI swarm</a>.</div>
      <div data-updated="{html.escape(updated)}">Updated: {updated_display}</div>
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
entries = validate_entry_provenance(entries)
entries = validate_entry_assets(entries)
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
