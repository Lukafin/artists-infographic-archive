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
        'school_poster': 'School poster',
        'science_news': 'Science news',
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


def render_original_article(e):
    url = str(e.get('original_article_url') or '').strip()
    if e.get('category') != 'science_news' or not url:
        return ''
    return (
        f'<a class="original-article" href="{html.escape(url)}" target="_blank" '
        'rel="noopener noreferrer" data-original-article-link="1">Read the original article ↗</a>'
    )


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
        {render_original_article(e)}
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
      <div class="eyebrow" data-i18n="hero_eyebrow">Visual learning archive</div>
      <h2 data-i18n="hero_title">Infographics for curious young readers.</h2>
      <p class="intro" data-i18n="hero_intro">Kid-friendly infographics about people, school topics and science discoveries. Browse the latest image, choose a collection, or search the full archive.</p>
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
    {render_info_overlay(featured, 'featured-info')}
  </article>
</section>'''


def collection_stats(entries):
    people_categories = {'artist', 'scientist', 'sport'}
    people_count = sum(1 for entry in entries if entry.get('category') in people_categories)
    school_count = sum(1 for entry in entries if entry.get('category') == 'school_poster')
    science_count = sum(1 for entry in entries if entry.get('category') == 'science_news')
    return {
        'people': people_count,
        'school_poster': school_count,
        'science_news': science_count,
        'all': len(entries),
    }


def render_collection_hub(stats):
    return f'''<section class="collections-hub surface" aria-labelledby="collections-heading">
  <div class="section-kicker" data-i18n="collections_eyebrow">Start with a collection</div>
  <div class="collections-heading-row">
    <div>
      <h2 id="collections-heading" data-i18n="collections_title">Choose what you want to learn</h2>
      <p data-i18n="collections_intro">Browse people, school posters, current science explainers or the full searchable archive.</p>
    </div>
    <a class="text-link" href="#archive" data-i18n="collections_all_link">Browse all infographics ↓</a>
  </div>
  <div class="collection-grid">
    <a class="collection-card people" href="./?collection=people#archive" data-collection-link="people">
      <span class="collection-icon" aria-hidden="true">👥</span>
      <span class="collection-copy"><strong data-i18n="collection_people_title">People</strong><small data-i18n="collection_people_desc">Artists, scientists and athletes</small></span>
      <span class="collection-count">{stats['people']}</span>
    </a>
    <a class="collection-card school" href="./?collection=school_poster#archive" data-collection-link="school_poster">
      <span class="collection-icon" aria-hidden="true">🧭</span>
      <span class="collection-copy"><strong data-i18n="collection_school_title">School posters</strong><small data-i18n="collection_school_desc">Classroom topics and visual summaries</small></span>
      <span class="collection-count">{stats['school_poster']}</span>
    </a>
    <a class="collection-card science-news" href="science-news.html">
      <span class="collection-icon" aria-hidden="true">🔭</span>
      <span class="collection-copy"><strong data-i18n="collection_science_title">Science news</strong><small data-i18n="collection_science_desc">Current discoveries explained for young readers</small></span>
      <span class="collection-count">{stats['science_news']}</span>
    </a>
    <a class="collection-card all" href="#archive" data-collection-link="all">
      <span class="collection-icon" aria-hidden="true">🗂️</span>
      <span class="collection-copy"><strong data-i18n="collection_all_title">All infographics</strong><small data-i18n="collection_all_desc">Search the complete archive</small></span>
      <span class="collection-count">{stats['all']}</span>
    </a>
  </div>
</section>'''


def render_process_note():
    return '''<section class="process-note surface" aria-labelledby="process-heading">
  <div class="section-kicker" data-i18n="process_eyebrow">How these infographics are made</div>
  <h2 id="process-heading" data-i18n="process_title">Human-supervised visual learning</h2>
  <p data-i18n="process_body">This archive is created with help from Roj swarm agents — small AI assistants that help gather sources, summarize topics, draft kid-friendly explanations and prepare visual material. Human review keeps the archive focused, safe and useful for learning.</p>
</section>'''


def render_science_news_page(science_entries):
    updated = datetime.now().strftime('%Y-%m-%d %H:%M')
    updated_display = html.escape(format_display_datetime(updated))
    cards = '\n'.join(render_masonry_card(e, featured=(idx == 0)) for idx, e in enumerate(science_entries)) or '<p class="empty">No science news explainers have been published yet.</p>'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Science news explained – Visual Learning Archive</title>
  <meta name="description" content="Source-backed science news explainers for young readers from the Visual Learning Archive.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap" rel="stylesheet">
  <style>{BASE_CSS.replace('{{', '{').replace('}}', '}')}</style>
</head>
<body>
  <main class="wrap">
    <header class="nav">
      <a class="brand brand-link" href="./">
        <div class="logo">🖼️</div>
        <div>
          <h1>Visual Learning Archive</h1>
          <p>Kid-friendly infographics about people, school topics and science discoveries.</p>
        </div>
      </a>
      <div class="nav-right"><a class="pill" href="./">← Home</a><a class="pill primary" href="./?collection=science_news#archive">Search archive</a></div>
    </header>
    <section class="science-hero surface">
      <div class="section-kicker">Science news explained</div>
      <h2>Current discoveries, made easier to understand.</h2>
      <p>These explainers turn source-backed science stories into kid-friendly visual summaries. Original articles and supporting sources stay available in each card’s information panel without taking over the page.</p>
    </section>
    <section class="archive-shell" id="science-news">
      <div class="archive-top">
        <div>
          <h2>Latest science explainers</h2>
          <p>Browse the science news collection separately from biographies and school posters.</p>
        </div>
        <span class="pill">{len(science_entries)} explainers</span>
      </div>
      <div class="masonry science-list">{cards}</div>
    </section>
    {render_process_note()}
    <footer class="footer surface">
      <div>Made with human supervision and <a href="https://roj.world/swarms/famous-people-infographic" target="_blank" rel="noopener noreferrer">Roj swarm agents</a>.</div>
      <div>Updated: {updated_display}</div>
    </footer>
  </main>
</body>
</html>'''


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
    <label for="archive-search" data-i18n="search_label">Search by person or topic</label>
    <input id="archive-search" type="search" placeholder="e.g. Duke Ellington or Webb telescope" data-i18n-placeholder="search_placeholder">
  </div>
  <div class="filter-control">
    <label for="archive-category" data-i18n="category_label">Collection</label>
    <select id="archive-category">
      <option value="" data-i18n="category_all">All collections</option>
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
      document_title: 'Visual Learning Archive',
      brand_title: 'Visual Learning Archive',
      brand_subtitle: 'Kid-friendly infographics about people, school topics and science discoveries',
      kofi: 'Support the site author',
      hero_eyebrow: 'Visual learning archive',
      hero_title: 'Infographics for curious young readers.',
      hero_intro: 'Kid-friendly infographics about people, school topics and science discoveries. Browse the latest image, choose a collection, or search the full archive.',
      archive_heading_home: 'Search the full archive',
      archive_heading_page: 'Archive – page {page}',
      archive_intro_home: 'Search by person, topic, collection, image language and age suitability.',
      archive_intro_page: 'Browse older infographics and explainers by page or use search and filters.',
      total_prefix: 'Total:',
      page_prefix: 'Page {page}/{total}',
      search_label: 'Search by person or topic',
      search_placeholder: 'e.g. Duke Ellington or Webb telescope',
      category_label: 'Collection',
      category_all: 'All collections',
      image_language_label: 'Image language',
      language_all: 'All image languages',
      age_label: 'Age suitability',
      age_all: 'All age levels',
      initial_summary: 'Showing the initial selection for this page. Use search or filters above to search the full archive.',
      no_results: 'No results for the selected filters.',
      found: 'Results found: {count}',
      source: 'source',
      original_article: 'Read the original article ↗',
      sources_zero: 'No sources',
      sources_one: '1 source',
      sources_many: '{count} sources',
      footer_text: 'Visual Learning Archive: kid-friendly infographics about people, school topics and science discoveries.',
      footer_generated_by: 'Made with human supervision and',
      footer_swarm: 'Roj swarm agents',
      updated: 'Updated:',
      search_unavailable: 'Search and filters are currently unavailable.',
      pager_previous: '← Previous',
      pager_next: 'Next →',
      lang_picker_label: 'Site language',
      category_artist: 'Artist',
      category_scientist: 'Scientist',
      category_sport: 'Athlete',
      category_school_poster: 'School poster',
      category_science_news: 'Science news',
      age_age_6: 'Ages 6+',
      age_age_13: 'Ages 13+',
      age_adult: 'Adults',
      image_details: 'Show image details',
      collections_eyebrow: 'Start with a collection',
      collections_title: 'Choose what you want to learn',
      collections_intro: 'Browse people, school posters, current science explainers or the full searchable archive.',
      collections_all_link: 'Browse all infographics ↓',
      collection_people_title: 'People',
      collection_people_desc: 'Artists, scientists and athletes',
      collection_school_title: 'School posters',
      collection_school_desc: 'Classroom topics and visual summaries',
      collection_science_title: 'Science news',
      collection_science_desc: 'Current discoveries explained for young readers',
      collection_all_title: 'All infographics',
      collection_all_desc: 'Search the complete archive',
      process_eyebrow: 'How these infographics are made',
      process_title: 'Human-supervised visual learning',
      process_body: 'This archive is created with help from Roj swarm agents — small AI assistants that help gather sources, summarize topics, draft kid-friendly explanations and prepare visual material. Human review keeps the archive focused, safe and useful for learning.'
    },
    sl: {
      document_title: 'Arhiv vizualnega učenja',
      brand_title: 'Arhiv vizualnega učenja',
      brand_subtitle: 'Otrokom prijazne infografike o ljudeh, šolskih temah in znanstvenih odkritjih',
      kofi: 'Podpri avtorja strani',
      hero_eyebrow: 'Arhiv vizualnega učenja',
      hero_title: 'Infografike za radovedne mlade bralce.',
      hero_intro: 'Otrokom prijazne infografike o ljudeh, šolskih temah in znanstvenih odkritjih. Oglej si najnovejšo sliko, izberi zbirko ali preišči celoten arhiv.',
      archive_heading_home: 'Preišči celoten arhiv',
      archive_heading_page: 'Arhiv – stran {page}',
      archive_intro_home: 'Išči po osebi ali temi ter filtriraj po zbirki, jeziku slike in starostni primernosti.',
      archive_intro_page: 'Prelistaj starejše infografike in razlagalnike po straneh ali uporabi iskanje in filtre.',
      total_prefix: 'Skupaj:',
      page_prefix: 'Stran {page}/{total}',
      search_label: 'Išči po osebi ali temi',
      search_placeholder: 'npr. Duke Ellington ali teleskop Webb',
      category_label: 'Zbirka',
      category_all: 'Vse zbirke',
      image_language_label: 'Jezik slike',
      language_all: 'Vsi jeziki slik',
      age_label: 'Starostna primernost',
      age_all: 'Vse starostne ravni',
      initial_summary: 'Prikazan je začetni izbor za to stran. Za iskanje ali filtriranje celotnega arhiva uporabi polja zgoraj.',
      no_results: 'Za izbrane filtre ni zadetkov.',
      found: 'Najdenih zadetkov: {count}',
      source: 'vir',
      original_article: 'Preberi izvirni članek ↗',
      sources_zero: 'Brez virov',
      sources_one: '1 vir',
      sources_many: '{count} viri',
      footer_text: 'Arhiv vizualnega učenja: otrokom prijazne infografike o ljudeh, šolskih temah in znanstvenih odkritjih.',
      footer_generated_by: 'Ustvarjeno s človeškim pregledom in pomočjo',
      footer_swarm: 'Roj swarm agentov',
      updated: 'Posodobljeno:',
      search_unavailable: 'Iskanje in filtri trenutno niso na voljo.',
      pager_previous: '← Prejšnja',
      pager_next: 'Naslednja →',
      lang_picker_label: 'Jezik strani',
      category_artist: 'Umetnik',
      category_scientist: 'Znanstvenik',
      category_sport: 'Športnik',
      category_school_poster: 'Šolski plakat',
      category_science_news: 'Znanstvena novica',
      age_age_6: '6+ let',
      age_age_13: '13+ let',
      age_adult: 'Odrasli',
      image_details: 'Pokaži podrobnosti slike',
      collections_eyebrow: 'Začni z zbirko',
      collections_title: 'Izberi, kaj želiš spoznati',
      collections_intro: 'Brskaj med ljudmi, šolskimi plakati, znanstvenimi novicami ali celotnim iskalnim arhivom.',
      collections_all_link: 'Poglej vse infografike ↓',
      collection_people_title: 'Ljudje',
      collection_people_desc: 'Umetniki, znanstveniki in športniki',
      collection_school_title: 'Šolski plakati',
      collection_school_desc: 'Teme za učilnico in vizualni povzetki',
      collection_science_title: 'Znanstvene novice',
      collection_science_desc: 'Aktualna odkritja, razložena mladim bralcem',
      collection_all_title: 'Vse infografike',
      collection_all_desc: 'Preišči celoten arhiv',
      process_eyebrow: 'Kako nastajajo infografike',
      process_title: 'Vizualno učenje s človeškim pregledom',
      process_body: 'Arhiv nastaja s pomočjo Roj swarm agentov — majhnih AI pomočnikov, ki pomagajo zbrati vire, povzeti teme, pripraviti otrokom prijazne razlage in vizualno gradivo. Človeški pregled skrbi, da je arhiv osredotočen, varen in uporaben za učenje.'
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
    const labels = (keys || []).map(ageLabel).filter(Boolean);
    if (!labels.length) return '';
    return `<span class="tag age" data-age-tag="1">${escapeHtml(labels.join(', '))}</span>`;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return '';
    return `<ul class="sources">${sources.slice(0, 4).map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-source-link="1">${escapeHtml(t('source'))}</a></li>`).join('')}</ul>`;
  }

  function renderOriginalArticle(entry) {
    if (entry.category !== 'science_news' || !entry.original_article_url) return '';
    return `<a class="original-article" href="${escapeHtml(entry.original_article_url)}" target="_blank" rel="noopener noreferrer" data-original-article-link="1">${escapeHtml(t('original_article'))}</a>`;
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
        ${renderOriginalArticle(entry)}
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
    document.querySelectorAll('[data-original-article-link]').forEach((node) => { node.textContent = t('original_article'); });
    document.querySelectorAll('[data-info-label]').forEach((node) => { node.setAttribute('aria-label', t('image_details')); });
    document.querySelectorAll('[data-date]').forEach((node) => { node.textContent = formatDate(node.dataset.date); });
    document.querySelectorAll('[data-source-count]').forEach((node) => { node.textContent = sourceCountLabel(Number(node.dataset.sourceCount || 0)); });
    document.querySelectorAll('[data-category-option]').forEach((node) => { node.textContent = categoryLabel(node.dataset.categoryOption); });
    document.querySelectorAll('[data-age-option]').forEach((node) => { node.textContent = ageLabel(node.dataset.ageOption); });
    document.querySelectorAll('[data-category-tag]').forEach((node) => { node.textContent = categoryLabel(node.dataset.categoryTag); });
    document.querySelectorAll('[data-age-tag]').forEach((node) => {
      const parent = node.closest('[data-age-suitability]');
      const rawKeys = parent ? parent.dataset.ageSuitability : (node.dataset.ageKey || '');
      const keys = rawKeys.split(/\s+/).filter(Boolean);
      const label = keys.map(ageLabel).filter(Boolean).join(', ');
      if (label) {
        node.textContent = label;
        node.hidden = false;
      } else {
        node.hidden = true;
        node.textContent = '';
      }
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
    const activeCollection = masonry.dataset.collection || '';
    const language = languageSelect.value;
    const age = ageSelect.value;
    const hasFilters = Boolean(query || category || activeCollection || language || age);

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
      if (activeCollection === 'people' && !['artist', 'scientist', 'sport'].includes(entry.category)) return false;
      if (activeCollection && activeCollection !== 'people' && activeCollection !== 'all' && entry.category !== activeCollection) return false;
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

  function applyQueryParams() {
    const params = new URLSearchParams(window.location.search);
    const collection = params.get('collection') || '';
    if (collection) masonry.dataset.collection = collection;
    if (params.get('category')) categorySelect.value = params.get('category');
    if (params.get('language')) languageSelect.value = params.get('language');
    if (params.get('age')) ageSelect.value = params.get('age');
    if (params.get('q')) searchInput.value = params.get('q');
  }

  document.querySelectorAll('[data-collection-link]').forEach((link) => {
    link.addEventListener('click', (event) => {
      const href = link.getAttribute('href') || '';
      if (href.includes('science-news.html')) return;
      event.preventDefault();
      const collection = link.dataset.collectionLink || '';
      masonry.dataset.collection = collection === 'all' ? '' : collection;
      categorySelect.value = '';
      searchInput.value = '';
      applyFilters();
      document.getElementById('archive')?.scrollIntoView({behavior: 'smooth', block: 'start'});
    });
  });

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
      applyQueryParams();
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

BASE_CSS = "    :root {{\n      color-scheme: light;\n      --bg:#faf7f2;\n      --paper:#fffdf9;\n      --panel:#ffffff;\n      --ink:#211922;\n      --muted:#6f6a62;\n      --line:#e6ddd0;\n      --accent:#e60023;\n      --chip:#f1ece4;\n      --hero1:#ffe0c4;\n      --hero2:#d8f1ff;\n      --hero3:#e7ddff;\n      --green:#d9f3df;\n      --shadow:0 12px 32px rgba(33,25,34,.08);\n      --radius:24px;\n    }}\n    * {{ box-sizing:border-box; }}\n    body {{\n      margin:0;\n      background:\n        radial-gradient(circle at top left, rgba(255,224,196,.65), transparent 24%),\n        radial-gradient(circle at 90% 0%, rgba(216,241,255,.75), transparent 22%),\n        linear-gradient(180deg,#fffdfa,var(--bg));\n      color:var(--ink);\n      font-family:'DM Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;\n    }}\n    a {{ color:inherit; }}\n    .wrap {{ max-width:1440px; margin:0 auto; padding:24px 20px 60px; }}\n    .surface {{ background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }}\n    .nav {{\n      position:sticky; top:18px; z-index:10;\n      display:flex; justify-content:space-between; align-items:center; gap:20px;\n      padding:16px 18px; background:rgba(255,253,249,.86); backdrop-filter:blur(14px);\n      border:1px solid rgba(230,221,208,.9); border-radius:22px; box-shadow:var(--shadow);\n    }}\n    .brand {{ display:flex; align-items:center; gap:14px; }}\n    .brand-link {{ text-decoration:none; }}\n    .logo {{ width:46px; height:46px; border-radius:16px; background:linear-gradient(135deg,var(--hero1),var(--hero3)); display:grid; place-items:center; font-size:23px; }}\n    .brand h1 {{ margin:0; font-size:18px; line-height:1.1; }}\n    .brand p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}\n    .nav-actions, .hero-chips, .archive-filters, .meta-row, .pagination {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}\n    .pill {{ display:inline-flex; align-items:center; gap:8px; padding:10px 14px; border-radius:999px; background:var(--chip); border:1px solid #e4dbce; font-size:14px; color:#3f3933; text-decoration:none; }}\n    .pill.primary {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:700; }}\n    .pill.soft {{ background:rgba(255,255,255,.72); }}\n    .support-note {{ max-width:360px; text-align:right; color:var(--muted); font-size:13px; line-height:1.35; }}\n    .support-note a {{ color:var(--accent); font-weight:800; text-decoration:none; }}\n    .support-note a:hover {{ text-decoration:underline; }}\n    .kofi-link {{ display:inline-flex; align-items:center; gap:5px; }}\n    .kofi-icon {{ width:22px; height:auto; display:inline-block; }}\n    .nav-right {{ display:flex; align-items:center; justify-content:flex-end; gap:14px; flex-wrap:wrap; }}\n    .lang-picker {{ display:inline-flex; align-items:center; gap:6px; padding:6px; border-radius:999px; background:#fff; border:1px solid var(--line); box-shadow:0 6px 18px rgba(33,25,34,.06); }}\n    .lang-icon {{ width:22px; height:22px; display:grid; place-items:center; font-size:16px; }}\n    .lang-picker button {{ border:0; border-radius:999px; background:transparent; color:#51483f; font:inherit; font-size:12px; font-weight:800; padding:7px 9px; cursor:pointer; }}\n    .lang-picker button.active {{ background:var(--ink); color:#fff; }}\n    .hero {{ margin-top:24px; display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr); gap:20px; align-items:stretch; }}\n    .hero > * {{ min-width:0; }}\n    .hero-copy {{ padding:34px 34px 30px; display:flex; flex-direction:column; justify-content:space-between; }}\n    .eyebrow {{ font-size:12px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#8a5c09; display:inline-flex; align-items:center; gap:8px; }}\n    .eyebrow::before {{ content:''; width:10px; height:10px; border-radius:999px; background:linear-gradient(135deg,#ff9d00,#ff4d6d); }}\n    .hero-copy h2 {{ font-size:clamp(42px,6vw,76px); line-height:.93; letter-spacing:-.05em; margin:14px 0 16px; max-width:12ch; text-wrap:balance; }}\n    .intro {{ margin:0; color:var(--muted); font-size:20px; line-height:1.5; max-width:31ch; }}\n    .hero-stats {{ margin-top:26px; display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}\n    .stat {{ background:var(--paper); border:1px solid var(--line); border-radius:22px; padding:18px 16px; }}\n    .stat strong {{ display:block; font-size:30px; margin-bottom:4px; }}\n    .stat span {{ font-size:14px; color:var(--muted); }}\n    .hero-card {{ min-height:420px; width:100%; max-width:100%; }}\n    .hero-image-wrap {{ position:absolute; inset:0; display:block; text-decoration:none; background:#fff; }}\n    .hero-image-wrap img {{ width:100%; height:100%; display:block; object-fit:contain; }}\n    .hero-title-overlay h3 {{ font-size:32px; }}\n    .sources a:hover {{ text-decoration:underline; }}\n    .collections-hub, .process-note, .science-hero {{ margin-top:24px; padding:28px; }}\n    .section-kicker {{ color:#8a5c09; font-size:12px; font-weight:850; letter-spacing:.14em; text-transform:uppercase; margin-bottom:10px; }}\n    .collections-heading-row {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:18px; }}\n    .collections-heading-row h2, .process-note h2, .science-hero h2 {{ margin:0; font-size:clamp(32px,4vw,54px); line-height:1; letter-spacing:-.045em; text-wrap:balance; }}\n    .collections-heading-row p, .process-note p, .science-hero p {{ margin:10px 0 0; color:var(--muted); font-size:18px; line-height:1.55; max-width:66ch; }}\n    .text-link {{ color:var(--accent); font-weight:850; text-decoration:none; white-space:nowrap; }}\n    .text-link:hover {{ text-decoration:underline; }}\n    .collection-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; }}\n    .collection-card {{ min-height:150px; display:flex; flex-direction:column; justify-content:space-between; gap:16px; padding:18px; border-radius:24px; text-decoration:none; border:1px solid var(--line); background:var(--paper); transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease; }}\n    .collection-card:hover, .collection-card:focus-visible {{ transform:translateY(-3px); box-shadow:0 18px 34px rgba(33,25,34,.12); border-color:#d1c3b0; outline:0; }}\n    .collection-card:active {{ transform:translateY(-1px) scale(.99); }}\n    .collection-card.people {{ background:linear-gradient(145deg,#fff9ef,#ffe9ec); }}\n    .collection-card.school {{ background:linear-gradient(145deg,#fffdf6,#edf8df); }}\n    .collection-card.science-news {{ background:linear-gradient(145deg,#f7fdff,#e6f6ff); }}\n    .collection-card.all {{ background:linear-gradient(145deg,#fffdf9,#f1ecff); }}\n    .collection-icon {{ font-size:28px; }}\n    .collection-copy strong {{ display:block; font-size:22px; letter-spacing:-.03em; }}\n    .collection-copy small {{ display:block; margin-top:5px; color:var(--muted); line-height:1.35; }}\n    .collection-count {{ align-self:flex-start; border-radius:999px; padding:7px 10px; background:rgba(255,255,255,.74); border:1px solid rgba(230,221,208,.9); color:#4b4238; font-size:13px; font-weight:850; font-variant-numeric:tabular-nums; }}\n    .process-note {{ background:linear-gradient(135deg, rgba(255,255,255,.9), rgba(255,247,220,.78)); }}\n    .science-hero {{ background:radial-gradient(circle at 88% 18%, rgba(216,241,255,.95), transparent 32%), rgba(255,255,255,.84); }}\n    .science-hero h2 {{ max-width:13ch; }}\n    .archive-shell {{ margin-top:24px; padding:24px; background:rgba(255,255,255,.84); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }}\n    .archive-top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px; }}\n    .archive-top h2 {{ margin:0; font-size:34px; letter-spacing:-.04em; }}\n    .archive-top p {{ margin:8px 0 0; color:var(--muted); font-size:17px; max-width:60ch; }}\n    .masonry {{ display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:18px; align-items:stretch; }}\n    .card, .image-card {{\n      position:relative; isolation:isolate; margin:0; background:#fff; border:1px solid var(--line);\n      border-radius:22px; overflow:hidden; box-shadow:0 10px 28px rgba(33,25,34,.08);\n      aspect-ratio:16/9;\n    }}\n    .card.feature {{ box-shadow:0 14px 36px rgba(33,25,34,.11); }}\n    .thumb {{ position:absolute; inset:0; display:block; text-decoration:none; background:#fff; }}\n    .thumb img {{ width:100%; height:100%; display:block; object-fit:contain; }}\n    .image-title {{ position:absolute; left:0; right:0; bottom:0; z-index:2; padding:56px 16px 14px; color:#fff; background:linear-gradient(180deg, transparent, rgba(0,0,0,.68)); pointer-events:none; }}\n    .image-title h3 {{ margin:0; font-size:22px; line-height:1.05; letter-spacing:-.03em; text-shadow:0 1px 12px rgba(0,0,0,.38); }}\n    .card.feature .image-title h3 {{ font-size:28px; }}\n    .info-popover {{ position:absolute; top:12px; right:12px; z-index:4; max-width:calc(100% - 24px); }}\n    .info-popover[open] {{ right:12px; bottom:auto; }}\n    .info-popover summary {{ list-style:none; }}\n    .info-popover summary::-webkit-details-marker {{ display:none; }}\n    .info-button {{ width:32px; height:32px; display:grid; place-items:center; margin-left:auto; border-radius:999px; border:1px solid rgba(255,255,255,.5); background:rgba(255,255,255,.58); color:rgba(33,25,34,.72); font-weight:850; font-size:15px; box-shadow:0 6px 16px rgba(0,0,0,.10); backdrop-filter:blur(8px); cursor:pointer; }}\n    .info-button:hover, .info-button:focus-visible {{ background:rgba(33,25,34,.82); color:#fff; outline:0; }}\n    .info-panel {{ position:absolute; top:42px; right:0; margin-top:0; width:min(300px, calc(100vw - 76px)); max-width:calc(100vw - 76px); max-height:min(148px, calc(100vh - 156px)); overflow:auto; overscroll-behavior:contain; padding:10px; border-radius:16px; background:rgba(255,253,249,.95); border:1px solid rgba(255,255,255,.9); box-shadow:0 16px 38px rgba(0,0,0,.2); backdrop-filter:blur(16px); }}\n    .info-panel .meta-row {{ gap:7px; }}\n    .info-panel .tag {{ padding:6px 9px; }}\n    .info-panel .sources {{ margin-top:9px; gap:6px; }}\n    .info-panel .sources a {{ padding:6px 9px; }}\n    .original-article {{ display:flex; align-items:center; justify-content:center; margin-top:9px; padding:8px 10px; border-radius:11px; background:#e8fbff; border:1px solid #c9edf5; color:#14606b; font-size:12px; font-weight:800; text-decoration:none; }}\n    .original-article:hover, .original-article:focus-visible {{ background:#d7f6fc; text-decoration:underline; outline:0; }}\n    .tag {{ display:inline-flex; padding:7px 10px; border-radius:999px; background:#f7f2ea; border:1px solid #ece1d4; font-size:12px; color:#564f47; }}\n    .tag[hidden] {{ display:none !important; }}\n    .tag.artist {{ background:#ffe9ec; border-color:#ffd4dc; color:#8d2440; }}\n    .tag.science {{ background:#eaf5ff; border-color:#d4e7ff; color:#29547f; }}\n    .tag.sport {{ background:#fff1d6; border-color:#ffe2a8; color:#8a5c09; }}\n    .tag.school-poster {{ background:#f0f7e8; border-color:#d8ecc7; color:#476c25; }}\n    .tag.science-news {{ background:#e8fbff; border-color:#c9edf5; color:#14606b; }}\n    .tag.language {{ background:#f1ecff; border-color:#ddd3ff; color:#55408d; }}\n    .tag.age {{ background:#fff7dc; border-color:#ffe7a5; color:#7b5a07; }}\n    .tag.source-count {{ background:#eaf8ee; border-color:#d9efd9; color:#2b6a3c; }}\n    .filter-bar {{ display:grid; grid-template-columns:minmax(220px, 1.6fr) repeat(3, minmax(150px, .8fr)); gap:12px; margin:0 0 18px; }}\n    .filter-control {{ display:flex; flex-direction:column; gap:6px; }}\n    .filter-control label {{ font-size:13px; color:var(--muted); font-weight:700; }}\n    .filter-control input, .filter-control select {{\n      width:100%; padding:12px 14px; border-radius:16px; border:1px solid var(--line);\n      background:#fff; color:var(--ink); font:inherit;\n    }}\n    .results-summary {{ margin:0 0 14px; color:var(--muted); font-size:14px; }}\n    .sources {{ list-style:none; display:flex; flex-wrap:wrap; gap:8px; padding:0; margin:12px 0 0; }}\n    .sources a {{ display:inline-flex; padding:7px 10px; border-radius:999px; text-decoration:none; background:#faf7f2; border:1px solid var(--line); color:#594e44; font-size:12px; }}\n    .pagination {{ margin-top:22px; justify-content:flex-end; }}\n    .pagination.is-hidden {{ display:none; }}\n\n    .footer {{ margin-top:20px; padding:18px 22px; display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:14px; }}\n    .footer a {{ color:var(--accent); font-weight:800; text-decoration:none; }}\n    .footer a:hover {{ text-decoration:underline; }}\n    .empty {{ color:var(--muted); font-size:16px; }}\n    @media (max-width:1200px) {{\n      .masonry {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}\n    }}\n    @media (max-width:1100px) {{\n      .hero {{ grid-template-columns:1fr; }}\n      .hero-stats {{ grid-template-columns:1fr 1fr; }}\n      .masonry {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}\n    }}\n    @media (max-width:700px) {{\n      .nav {{ position:static; flex-direction:column; align-items:stretch; }}\n      .nav-right {{ justify-content:flex-start; }}\n      .support-note {{ max-width:none; text-align:left; }}\n      .archive-top, .footer, .collections-heading-row {{ flex-direction:column; align-items:flex-start; }}\n      .pagination {{ justify-content:flex-start; }}\n      .hero-copy {{ padding:26px; }}\n      .intro {{ font-size:18px; }}\n      .hero-stats {{ grid-template-columns:1fr; }}\n      .hero-card {{ min-height:0; }}\n      .hero-title-overlay h3 {{ font-size:28px; }}\n      .wrap {{ padding:18px 14px 44px; }}\n      .filter-bar {{ grid-template-columns:1fr; }}\n      .masonry, .collection-grid {{ grid-template-columns:1fr; }}\n      .info-popover[open] {{ left:12px; right:12px; bottom:12px; max-width:none; }}\n      .info-popover[open] .info-panel {{ width:min(276px, 100%); max-width:100%; max-height:min(104px, calc(100% - 54px)); }}\n      .info-panel .tag {{ padding:5px 8px; font-size:11px; }}\n      .info-panel .sources a {{ padding:5px 8px; font-size:11px; }}\n    }}\n"

def render_page(page_num: int, total_pages: int, chunk, featured=None):
    page_heading = 'Search the full archive' if page_num == 1 else f'Archive – page {page_num}'
    page_intro = (
        'Search by person, topic, collection, image language and age suitability.'
        if page_num == 1 else
        'Browse older infographics and explainers by page or use search and filters.'
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
  <title>Visual Learning Archive – {title_suffix}</title>
  <meta name="description" content="Kid-friendly infographics about people, school topics and science discoveries.">
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
    .brand-link {{ text-decoration:none; }}
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
    .hero {{ margin-top:24px; display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr); gap:20px; align-items:stretch; }}
    .hero > * {{ min-width:0; }}
    .hero-copy {{ padding:34px 34px 30px; display:flex; flex-direction:column; justify-content:space-between; }}
    .eyebrow {{ font-size:12px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#8a5c09; display:inline-flex; align-items:center; gap:8px; }}
    .eyebrow::before {{ content:''; width:10px; height:10px; border-radius:999px; background:linear-gradient(135deg,#ff9d00,#ff4d6d); }}
    .hero-copy h2 {{ font-size:clamp(42px,6vw,76px); line-height:.93; letter-spacing:-.05em; margin:14px 0 16px; max-width:12ch; text-wrap:balance; }}
    .intro {{ margin:0; color:var(--muted); font-size:20px; line-height:1.5; max-width:31ch; }}
    .hero-stats {{ margin-top:26px; display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
    .stat {{ background:var(--paper); border:1px solid var(--line); border-radius:22px; padding:18px 16px; }}
    .stat strong {{ display:block; font-size:30px; margin-bottom:4px; }}
    .stat span {{ font-size:14px; color:var(--muted); }}
    .hero-card {{ min-height:420px; width:100%; max-width:100%; }}
    .hero-image-wrap {{ position:absolute; inset:0; display:block; text-decoration:none; background:#fff; }}
    .hero-image-wrap img {{ width:100%; height:100%; display:block; object-fit:contain; }}
    .hero-title-overlay h3 {{ font-size:32px; }}
    .sources a:hover {{ text-decoration:underline; }}
    .collections-hub, .process-note, .science-hero {{ margin-top:24px; padding:28px; }}
    .section-kicker {{ color:#8a5c09; font-size:12px; font-weight:850; letter-spacing:.14em; text-transform:uppercase; margin-bottom:10px; }}
    .collections-heading-row {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:18px; }}
    .collections-heading-row h2, .process-note h2, .science-hero h2 {{ margin:0; font-size:clamp(32px,4vw,54px); line-height:1; letter-spacing:-.045em; text-wrap:balance; }}
    .collections-heading-row p, .process-note p, .science-hero p {{ margin:10px 0 0; color:var(--muted); font-size:18px; line-height:1.55; max-width:66ch; }}
    .text-link {{ color:var(--accent); font-weight:850; text-decoration:none; white-space:nowrap; }}
    .text-link:hover {{ text-decoration:underline; }}
    .collection-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; }}
    .collection-card {{ min-height:150px; display:flex; flex-direction:column; justify-content:space-between; gap:16px; padding:18px; border-radius:24px; text-decoration:none; border:1px solid var(--line); background:var(--paper); transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease; }}
    .collection-card:hover, .collection-card:focus-visible {{ transform:translateY(-3px); box-shadow:0 18px 34px rgba(33,25,34,.12); border-color:#d1c3b0; outline:0; }}
    .collection-card:active {{ transform:translateY(-1px) scale(.99); }}
    .collection-card.people {{ background:linear-gradient(145deg,#fff9ef,#ffe9ec); }}
    .collection-card.school {{ background:linear-gradient(145deg,#fffdf6,#edf8df); }}
    .collection-card.science-news {{ background:linear-gradient(145deg,#f7fdff,#e6f6ff); }}
    .collection-card.all {{ background:linear-gradient(145deg,#fffdf9,#f1ecff); }}
    .collection-icon {{ font-size:28px; }}
    .collection-copy strong {{ display:block; font-size:22px; letter-spacing:-.03em; }}
    .collection-copy small {{ display:block; margin-top:5px; color:var(--muted); line-height:1.35; }}
    .collection-count {{ align-self:flex-start; border-radius:999px; padding:7px 10px; background:rgba(255,255,255,.74); border:1px solid rgba(230,221,208,.9); color:#4b4238; font-size:13px; font-weight:850; font-variant-numeric:tabular-nums; }}
    .process-note {{ background:linear-gradient(135deg, rgba(255,255,255,.9), rgba(255,247,220,.78)); }}
    .science-hero {{ background:radial-gradient(circle at 88% 18%, rgba(216,241,255,.95), transparent 32%), rgba(255,255,255,.84); }}
    .science-hero h2 {{ max-width:13ch; }}
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
    .info-popover {{ position:absolute; top:12px; right:12px; z-index:4; max-width:calc(100% - 24px); }}
    .info-popover[open] {{ right:12px; bottom:auto; }}
    .info-popover summary {{ list-style:none; }}
    .info-popover summary::-webkit-details-marker {{ display:none; }}
    .info-button {{ width:32px; height:32px; display:grid; place-items:center; margin-left:auto; border-radius:999px; border:1px solid rgba(255,255,255,.5); background:rgba(255,255,255,.58); color:rgba(33,25,34,.72); font-weight:850; font-size:15px; box-shadow:0 6px 16px rgba(0,0,0,.10); backdrop-filter:blur(8px); cursor:pointer; }}
    .info-button:hover, .info-button:focus-visible {{ background:rgba(33,25,34,.82); color:#fff; outline:0; }}
    .info-panel {{ position:absolute; top:42px; right:0; margin-top:0; width:min(300px, calc(100vw - 76px)); max-width:calc(100vw - 76px); max-height:min(148px, calc(100vh - 156px)); overflow:auto; overscroll-behavior:contain; padding:10px; border-radius:16px; background:rgba(255,253,249,.95); border:1px solid rgba(255,255,255,.9); box-shadow:0 16px 38px rgba(0,0,0,.2); backdrop-filter:blur(16px); }}
    .info-panel .meta-row {{ gap:7px; }}
    .info-panel .tag {{ padding:6px 9px; }}
    .info-panel .sources {{ margin-top:9px; gap:6px; }}
    .info-panel .sources a {{ padding:6px 9px; }}
    .original-article {{ display:flex; align-items:center; justify-content:center; margin-top:9px; padding:8px 10px; border-radius:11px; background:#e8fbff; border:1px solid #c9edf5; color:#14606b; font-size:12px; font-weight:800; text-decoration:none; }}
    .original-article:hover, .original-article:focus-visible {{ background:#d7f6fc; text-decoration:underline; outline:0; }}
    .tag {{ display:inline-flex; padding:7px 10px; border-radius:999px; background:#f7f2ea; border:1px solid #ece1d4; font-size:12px; color:#564f47; }}
    .tag[hidden] {{ display:none !important; }}
    .tag.artist {{ background:#ffe9ec; border-color:#ffd4dc; color:#8d2440; }}
    .tag.science {{ background:#eaf5ff; border-color:#d4e7ff; color:#29547f; }}
    .tag.sport {{ background:#fff1d6; border-color:#ffe2a8; color:#8a5c09; }}
    .tag.school-poster {{ background:#f0f7e8; border-color:#d8ecc7; color:#476c25; }}
    .tag.science-news {{ background:#e8fbff; border-color:#c9edf5; color:#14606b; }}
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
      .archive-top, .footer, .collections-heading-row {{ flex-direction:column; align-items:flex-start; }}
      .pagination {{ justify-content:flex-start; }}
      .hero-copy {{ padding:26px; }}
      .intro {{ font-size:18px; }}
      .hero-stats {{ grid-template-columns:1fr; }}
      .hero-card {{ min-height:0; }}
      .hero-title-overlay h3 {{ font-size:28px; }}
      .wrap {{ padding:18px 14px 44px; }}
      .filter-bar {{ grid-template-columns:1fr; }}
      .masonry, .collection-grid {{ grid-template-columns:1fr; }}
      .info-popover[open] {{ left:12px; right:12px; bottom:12px; max-width:none; }}
      .info-popover[open] .info-panel {{ width:min(276px, 100%); max-width:100%; max-height:min(104px, calc(100% - 54px)); }}
      .info-panel .tag {{ padding:5px 8px; font-size:11px; }}
      .info-panel .sources a {{ padding:5px 8px; font-size:11px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="nav">
      <div class="brand">
        <div class="logo">🖼️</div>
        <div>
          <h1 data-i18n="brand_title">Visual Learning Archive</h1>
          <p data-i18n="brand_subtitle">Kid-friendly infographics about people, school topics and science discoveries</p>
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
    {render_collection_hub(collection_stats(entries)) if page_num == 1 else ''}
    <section class="archive-shell" id="archive">
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
    {render_process_note() if page_num == 1 else ''}
    <footer class="footer surface">
      <div><span data-i18n="footer_text">Visual Learning Archive: kid-friendly infographics about people, school topics and science discoveries.</span> <span data-i18n="footer_generated_by">Made with human supervision and</span> <a href="https://roj.world/swarms/famous-people-infographic" target="_blank" rel="noopener noreferrer" data-i18n="footer_swarm">Roj swarm agents</a>.</div>
      <div data-updated="{html.escape(updated)}">Updated: {updated_display}</div>
    </footer>
  </main>
  {client_script}
</body>
</html>'''


def clean_html_document(value: str) -> str:
    return '\n'.join(line.rstrip() for line in value.splitlines()) + '\n'


entries = []
for e in load_json(LEGACY_IMPORTED, []):
    e['_kind'] = 'legacy'
    entries.append(e)

for entry_path in sorted(RUNS_DIR.glob('*/entry.json')):
    entry = load_json(entry_path, None)
    if isinstance(entry, dict):
        entry['_kind'] = 'native'
        # Multiple lanes can publish on the same calendar day. Preserve the
        # newest native bridge entry as the homepage/latest item instead of
        # letting a same-day alphabetical person sort choose stale content.
        entry['_source_mtime'] = entry_path.stat().st_mtime
        entries.append(entry)

entries = [normalize_entry_metadata(entry) for entry in dedupe_entries(entries)]
entries = validate_entry_provenance(entries)
entries = validate_entry_assets(entries)

def entry_sort_key(entry):
    published_hint = (
        entry.get('published_at')
        or entry.get('updated_at')
        or entry.get('created_at')
        or entry.get('_source_mtime')
        or 0
    )
    return (
        entry.get('date') or '',
        str(published_hint),
        entry.get('person') or '',
        entry.get('filename') or '',
    )

entries.sort(key=entry_sort_key, reverse=True)
entries_index = build_entries_index(entries)

featured = entries[0] if entries else None
archive_entries = entries[1:] if len(entries) > 1 else []
# Multiple valid outputs can be published on the same day (for example a
# scheduled cron run plus a manual/debug run). Keep same-day non-featured
# entries in the visible archive grid instead of hiding them behind search.

ENTRIES_INDEX.write_text(json.dumps(entries_index, ensure_ascii=False, indent=2), encoding='utf-8')
(PUBLIC_ROOT / KOFI_ICON_FILENAME).write_text(KOFI_ICON_SVG + '\n', encoding='utf-8')

total_pages = max(1, math.ceil(len(archive_entries) / PER_PAGE))

for page_num in range(1, total_pages + 1):
    start = (page_num - 1) * PER_PAGE
    end = start + PER_PAGE
    chunk = archive_entries[start:end]
    html_doc = render_page(page_num, total_pages, chunk, featured=featured)
    (PUBLIC_ROOT / page_filename(page_num)).write_text(clean_html_document(html_doc), encoding='utf-8')

science_entries = [entry for entry in entries if entry.get('category') == 'science_news']
(PUBLIC_ROOT / 'science-news.html').write_text(clean_html_document(render_science_news_page(science_entries)), encoding='utf-8')

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
        'original_article_url': featured.get('original_article_url'),
        'sources': featured.get('sources', []),
        'age_suitability_keys': featured.get('age_suitability_keys', []),
        'age_suitability_labels_en': featured.get('age_suitability_labels_en', []),
        'age_suitability_labels_sl': featured.get('age_suitability_labels_sl', []),
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
