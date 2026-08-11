#!/usr/bin/env python3
import html
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from gallery_index import AGE_SUITABILITY_LEVELS, CATEGORY_LABELS, build_entries_index, normalize_entry_metadata


def configured_path(variable: str, default: str) -> Path:
    """Resolve a local or production archive path without forking the generator."""
    return Path(os.environ.get(variable, default)).expanduser().resolve()


BASE = configured_path(
    'ARTISTS_ARCHIVE_BASE',
    '/home/lukafinzgar/projects/.caller_tasks/artists',
)
RUNS_DIR = configured_path('ARTISTS_ARCHIVE_RUNS_DIR', str(BASE / 'runs'))
PUBLIC_ROOT = configured_path(
    'ARTISTS_ARCHIVE_PUBLIC_ROOT',
    '/home/lukafinzgar/projects/.caller_tasks/artists-infographic-archive/docs',
)
LEGACY_IMPORTED = configured_path(
    'ARTISTS_ARCHIVE_LEGACY_IMPORTED',
    str(BASE / 'imported_legacy_entries.json'),
)
LATEST_META = PUBLIC_ROOT / 'latest.json'
ENTRIES_INDEX = PUBLIC_ROOT / 'entries.json'
PER_PAGE = 10
FAVICON_FILENAME = 'favicon.svg'
FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="17" fill="#fff8e8"/><path d="M12 18c8-2 15 0 20 5v29c-5-5-12-7-20-5V18Zm40 0c-8-2-15 0-20 5v29c5-5 12-7 20-5V18Z" fill="none" stroke="#12391f" stroke-width="3" stroke-linejoin="round"/><path d="M32 23v29M32 20c0-5 3-9 8-11M32 17c-3-4-6-5-10-5M37 13l4 1-1-4M25 13l-4 2 1-5" fill="none" stroke="#b87408" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
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


SCIENCE_TITLE_SL = {
    '31f8c0fc-6403-4210-9be0-a1386751c039': 'Drobni vrtinci mešajo površje Sonca',
    '27fd91ee-7c15-4c25-b84e-482d61ee1f04': 'LiDAR razkriva obsežno predkolonialno pokrajino pod jugozahodno Amazonijo',
}

SCIENCE_TOPICS = {
    'sun': ('☀', 'Sun', 'Sonce', ('sun', 'solar', 'photosphere', 'plasma')),
    'plasma_physics': ('≈', 'Plasma physics', 'Fizika plazme', ('plasma', 'kelvin–helmholtz', 'magnetic flux')),
    'archaeology': ('⌂', 'Archaeology', 'Arheologija', ('archaeolog', 'precolonial', 'earthwork', 'geoglyph')),
    'amazonia': ('♧', 'Amazonia', 'Amazonija', ('amazon', 'aquiry', 'rainforest')),
    'space': ('◌', 'Space', 'Vesolje', ('space', 'planet', 'galaxy', 'star', 'asteroid', 'comet')),
    'biology': ('⌁', 'Biology', 'Biologija', ('biology', 'species', 'genome', 'cell', 'animal', 'plant')),
    'climate': ('☼', 'Climate', 'Podnebje', ('climate', 'warming', 'emission', 'temperature')),
    'health': ('+', 'Health', 'Zdravje', ('health', 'medical', 'disease', 'patient', 'vaccine')),
    'earth': ('◇', 'Earth science', 'Vede o Zemlji', ('earthquake', 'volcano', 'geology', 'ocean')),
    'technology': ('▦', 'Technology', 'Tehnologija', ('technology', 'computer', 'robot', 'artificial intelligence')),
}


def science_titles(e):
    english = display_title(e.get('title') or e.get('person', ''))
    localized = e.get('localized_titles') if isinstance(e.get('localized_titles'), dict) else {}
    slovenian = (
        e.get('title_sl')
        or localized.get('sl')
        or SCIENCE_TITLE_SL.get(str(e.get('assignment_id') or ''))
        or english
    )
    return english, display_title(slovenian)


def science_topic_keys(entries, limit=4):
    found = []
    for entry in entries:
        explicit = entry.get('science_topics') or entry.get('topics') or []
        if isinstance(explicit, str):
            explicit = [explicit]
        text = ' '.join(str(entry.get(key) or '') for key in ('person', 'title', 'summary')).lower()
        candidates = [str(key).strip().lower() for key in explicit]
        candidates.extend(
            key for key, (_, _, _, terms) in SCIENCE_TOPICS.items()
            if any(term in text for term in terms)
        )
        for key in candidates:
            if key in SCIENCE_TOPICS and key not in found:
                found.append(key)
                if len(found) >= limit:
                    return found
    return found


def source_details(url):
    host = urlparse(str(url)).netloc.lower().removeprefix('www.')
    if host == 'doi.org':
        return 'Nature', 'research_paper'
    known = {
        'nature.com': ('Nature', 'research_paper'),
        'pubmed.ncbi.nlm.nih.gov': ('PubMed', 'research_record'),
        'sciencenews.org': ('Science News', 'news_explainer'),
        'sciencedaily.com': ('ScienceDaily', 'news_article'),
        'helsinki.fi': ('University of Helsinki', 'research_news'),
        'livescience.com': ('Live Science', 'news_article'),
        'nasa.gov': ('NASA', 'website'),
    }
    for domain, details in known.items():
        if host == domain or host.endswith('.' + domain):
            return details
    name = host.split('.')[0].replace('-', ' ').title() if host else 'Source'
    return name, 'website'


def source_link_label(url, index, url_limit=44):
    clean = str(url)
    short_url = clean if len(clean) <= url_limit else clean[:url_limit - 1] + '…'
    return f'Source {index} ({short_url})'


def friendly_source_label(url):
    name, kind = source_details(url)
    labels = {
        'research_paper': 'Research paper',
        'research_record': 'Research record',
        'news_explainer': 'News explainer',
        'news_article': 'News article',
        'research_news': 'Research news',
        'website': 'Website',
    }
    return f'{name} — {labels[kind]}'


def render_source_link(url, index, friendly=False):
    name, kind = source_details(url)
    friendly_data = (
        f' data-source-name="{html.escape(name)}" data-source-kind="{html.escape(kind)}"'
        if friendly else ''
    )
    label = friendly_source_label(url) if friendly else source_link_label(url, index)
    return (
        f'<li><a href="{html.escape(url)}" title="{html.escape(url)}" target="_blank" rel="noopener noreferrer" '
        f'data-source-index="{index}" data-source-url="{html.escape(url)}"{friendly_data}>'
        f'{html.escape(label)}</a></li>'
    )


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


def render_sources(e, friendly=False):
    sources = e.get('sources', [])
    if not sources:
        return ''
    items = ''.join(render_source_link(url, index, friendly=friendly) for index, url in enumerate(sources[:4], 1))
    return f'<ul class="sources">{items}</ul>'


def render_original_article(e):
    url = str(e.get('original_article_url') or '').strip()
    if e.get('category') != 'science_news' or not url:
        return ''
    return (
        f'<a class="original-article" href="{html.escape(url)}" target="_blank" '
        'rel="noopener noreferrer" data-original-article-link="1">Read the original article ↗</a>'
    )


def render_info_overlay(e, panel_id, expanded=False, friendly_sources=False):
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
        {render_sources(e, friendly=friendly_sources)}
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



def pick_preview(entries, categories, fallback_index=0):
    for entry in entries:
        if entry.get('category') in categories and entry.get('filename'):
            return entry
    for entry in entries:
        if entry.get('filename'):
            return entry
    return None


def display_title(value):
    title = str(value or '')
    return title[:1].upper() + title[1:] if title else ''


def preview_img(entry, class_name, alt_prefix='Archive preview'):
    if not entry:
        return ''
    filename = html.escape(entry.get('filename', ''))
    title = html.escape(display_title(entry.get('person', 'infographic')))
    return f'<img class="{class_name}" src="{filename}" alt="{alt_prefix}: {title}" loading="lazy">'


def collection_preview_set(entries):
    people_previews = []
    seen_people_files = set()
    for entry in entries:
        filename = entry.get('filename')
        if (
            entry.get('category') in {'artist', 'scientist', 'sport'}
            and filename
            and filename not in seen_people_files
        ):
            people_previews.append(entry)
            seen_people_files.add(filename)
            if len(people_previews) == 3:
                break

    first_school = pick_preview(entries, {'school_poster'})
    return {
        'people_a': people_previews[0] if len(people_previews) > 0 else None,
        'people_b': people_previews[1] if len(people_previews) > 1 else None,
        'people_c': people_previews[2] if len(people_previews) > 2 else None,
        'school_a': first_school,
        'school_b': pick_preview([e for e in entries if e.get('filename') != (first_school or {}).get('filename')], {'school_poster'}),
        'science_a': pick_preview(entries, {'science_news'}),
        'all_a': pick_preview(entries, {'artist', 'scientist', 'sport', 'school_poster', 'science_news'}),
    }

def render_masonry_card(e, featured=False, friendly_sources=False):
    if e.get('category') == 'science_news':
        title_en, title_sl = science_titles(e)
    else:
        title_en = title_sl = display_title(e.get('person', ''))
    person = html.escape(title_en)
    title_sl_attr = html.escape(title_sl)
    filename = html.escape(e.get('filename', ''))
    age_data = html.escape(age_suitability_data(e))
    feature_cls = ' feature' if featured else ''
    panel_id = 'info-' + re.sub(r'[^a-zA-Z0-9_-]+', '-', f"{e.get('date', '')}-{e.get('filename', '')}").strip('-')
    return f'''<article class="card{feature_cls}" data-person="{html.escape(e.get('person', ''))}" data-category="{html.escape(e.get('category', ''))}" data-language="{html.escape(e.get('language', 'sl'))}" data-age-suitability="{age_data}">
  <a class="thumb" href="{filename}" aria-label="Open infographic: {person}" data-infographic-link="1" data-title-en="{person}" data-title-sl="{title_sl_attr}"><img src="{filename}" alt="Infographic: {person}" loading="lazy"></a>
  <div class="image-title">
    <h3 data-localized-title="1" data-title-en="{person}" data-title-sl="{title_sl_attr}">{person}</h3>
  </div>
  {render_info_overlay(e, panel_id, friendly_sources=friendly_sources)}
</article>'''


def render_featured(featured):
    if not featured:
        return ''
    person = html.escape(display_title(featured.get('person', '')))
    featured_file = html.escape(featured.get('filename', ''))
    previews = [entry for entry in entries if entry.get('filename') and entry.get('filename') != featured.get('filename')][:2]
    poster_stack = ''.join(
        preview_img(entry, f'hero-poster poster-{idx + 1}', 'Overlapping archive poster')
        for idx, entry in enumerate(previews)
    )
    return f'''<section class="hero hero-desk" aria-labelledby="hero-title">
  <div class="hero-copy">
    <div class="eyebrow" data-i18n="hero_eyebrow">Visual learning archive</div>
    <h2 id="hero-title" data-i18n="hero_title">Visual explanations for curious learners</h2>
    <div class="ornament" aria-hidden="true"><span></span>✦<span></span></div>
    <p class="intro" data-i18n="hero_intro">Accessible infographics about people, school topics and science discoveries. Browse the latest image, choose a collection, or search the full archive.</p>
    <div class="hero-chips" aria-label="Featured collections">
      <a class="hero-chip" href="./?collection=people#archive" data-collection-link="people"><span aria-hidden="true">♙</span><strong data-i18n="collection_people_title">People</strong> →</a>
      <a class="hero-chip" href="./?collection=school_poster#archive" data-collection-link="school_poster"><span aria-hidden="true">▤</span><strong data-i18n="collection_school_title">School posters</strong> →</a>
      <a class="hero-chip" href="science-news.html"><span aria-hidden="true">⚗</span><strong data-i18n="collection_science_title">Science news</strong> →</a>
    </div>
  </div>
  <div class="poster-stage" aria-label="Latest and recent archive posters">
    {poster_stack}
    <article class="hero-card image-card main-poster" aria-label="Latest infographic: {person}">
      <a class="hero-image-wrap" href="{featured_file}" aria-label="Open latest infographic: {person}">
        <img src="{featured_file}" alt="Infographic: {person}">
      </a>
    </article>
  </div>
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


def render_collection_hub(stats, previews=None):
    previews = previews or {}
    people_imgs = ''.join([
        preview_img(previews.get('people_a'), 'people-sheet sheet-main', 'People collection preview'),
        preview_img(previews.get('people_b'), 'people-sheet sheet-left', 'People collection preview'),
        preview_img(previews.get('people_c'), 'people-sheet sheet-right', 'People collection preview'),
    ])
    school_imgs = ''.join([
        preview_img(previews.get('school_a'), 'mini-poster school-one', 'School posters preview'),
        preview_img(previews.get('school_b'), 'mini-poster school-two', 'School posters preview'),
    ])
    science_img = preview_img(previews.get('science_a'), 'science-preview-image', 'Science news preview')
    all_img = preview_img(previews.get('all_a'), 'all-preview-image', 'Archive preview')
    return f'''<section class="collections-hub" aria-labelledby="collections-heading">
  <div class="collections-heading-row">
    <div>
      <div class="section-kicker" data-i18n="collections_eyebrow">Start with a collection</div>
      <h2 id="collections-heading" data-i18n="collections_title">Choose a collection</h2>
      <p data-i18n="collections_intro">Carefully curated infographics and explainers for curious minds.</p>
    </div>
    <a class="text-link" href="#archive" data-i18n="collections_all_link">Browse all infographics ↓</a>
  </div>
  <div class="collection-grid illustrated-collections">
    <a class="collection-card people featured-collection" href="./?collection=people#archive" data-collection-link="people">
      <span class="collection-copy"><strong data-i18n="collection_people_title">Famous people</strong><small data-i18n="collection_people_desc">Discover the lives and big ideas of amazing people who changed our world.</small></span>
      <span class="collection-art people-art" aria-hidden="true">{people_imgs}</span>
      <span class="collection-cta">Browse people →</span>
    </a>
    <a class="collection-card school" href="./?collection=school_poster#archive" data-collection-link="school_poster">
      <span class="collection-copy"><strong data-i18n="collection_school_title">School posters</strong><small data-i18n="collection_school_desc">Bright, clear posters that make big topics easy to understand.</small></span>
      <span class="collection-art school-art" aria-hidden="true">{school_imgs}</span>
      <span class="collection-cta">Browse posters →</span>
    </a>
    <a class="collection-card science-news" href="science-news.html">
      <span class="collection-copy"><strong data-i18n="collection_science_title">Science news explained</strong><small data-i18n="collection_science_desc">Short, visual stories about the latest discoveries and what they mean.</small></span>
      <span class="collection-art science-art" aria-hidden="true">{science_img}</span>
      <span class="collection-cta">Read explainers →</span>
    </a>
    <a class="collection-card all" href="#archive" data-collection-link="all">
      <span class="collection-copy"><strong data-i18n="collection_all_title">All infographics</strong><small data-i18n="collection_all_desc">Search the complete archive by topic, collection, language and age level.</small></span>
      <span class="collection-art all-art" aria-hidden="true">{all_img}</span>
      <span class="collection-cta">Search archive ↓</span>
    </a>
  </div>
</section>'''


def render_process_note():
    return '''<section class="process-note surface" aria-labelledby="process-heading">
  <div class="section-kicker" data-i18n="process_eyebrow">How these infographics are made</div>
  <h2 id="process-heading" data-i18n="process_title">Human-supervised visual learning</h2>
  <p data-i18n="process_body">This archive is created with help from Roj swarm agents — small AI assistants that help gather sources, summarize topics, draft clear explanations and prepare visual material. Human review keeps the archive focused, reliable and useful for learning.</p>
</section>'''


def render_science_news_page(science_entries):
    updated = datetime.now().strftime('%Y-%m-%d %H:%M')
    updated_display = html.escape(format_display_datetime(updated))
    cards = '\n'.join(
        render_masonry_card(e, featured=(idx == 0), friendly_sources=True)
        for idx, e in enumerate(science_entries)
    ) or '<p class="empty">No science news explainers have been published yet.</p>'
    featured = science_entries[0] if science_entries else None
    featured_img = preview_img(featured, 'science-hero-image', 'Latest science explainer')
    featured_title = html.escape(display_title(featured.get('person', 'Latest science explainer'))) if featured else 'Latest science explainer'
    featured_sources = (featured or {}).get('sources') or []
    source_links = ''.join(render_source_link(url, index, friendly=True) for index, url in enumerate(featured_sources[:6], 1))
    topic_keys = science_topic_keys(science_entries)
    topic_pills = ''.join(
        f'<span data-topic="{html.escape(key)}"><span aria-hidden="true">{html.escape(SCIENCE_TOPICS[key][0])}</span> '
        f'<span data-topic-label="1" data-label-en="{html.escape(SCIENCE_TOPICS[key][1])}" '
        f'data-label-sl="{html.escape(SCIENCE_TOPICS[key][2])}">{html.escape(SCIENCE_TOPICS[key][1])}</span></span>'
        for key in topic_keys
    )
    source_list = (
        f'<section class="science-sources" aria-labelledby="featured-sources-heading">'
        f'<h3 id="featured-sources-heading" data-i18n="sources_heading">Sources</h3><ul>{source_links}</ul></section>'
        if source_links else
        '<section class="science-sources" aria-labelledby="featured-sources-heading">'
        '<h3 id="featured-sources-heading" data-i18n="sources_heading">Sources</h3>'
        '<p data-i18n="sources_empty">No sources listed.</p></section>'
    )
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Science news explained – Visual Learning Archive</title>
  <meta name="description" content="Source-backed science news explainers for young readers from the Visual Learning Archive.">
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400..900&family=Fraunces:opsz,wght,SOFT,WONK@9..144,600..900,50..100,1&display=swap" rel="stylesheet">
  <style>{BASE_CSS.replace('{{', '{').replace('}}', '}')}</style>
</head>
<body>
  <main class="wrap">
    <header class="nav">
      <a class="brand brand-link" href="./">
        <div class="logo"><img src="favicon.svg" alt=""></div>
        <div>
          <h1 data-i18n="brand_title">Visual Learning Archive</h1>
          <p data-i18n="brand_subtitle">Accessible infographics about people, school topics and science discoveries.</p>
        </div>
      </a>
      <div class="nav-right">
        <div class="lang-picker" role="group" aria-label="Site language" data-i18n-aria-label="lang_picker_label">
          <span class="lang-icon" aria-hidden="true">🌐</span>
          <button type="button" class="active" data-lang-option="en" aria-pressed="true">EN</button>
          <button type="button" data-lang-option="sl" aria-pressed="false">SL</button>
        </div>
      </div>
    </header>
    <section class="science-hero editorial-science-simple">
      <div class="science-hero-art">
        {featured_img}
        <div class="science-hero-caption"><span data-i18n="latest_explainer">Latest explainer</span></div>
      </div>
      <div class="science-hero-copy surface">
        <div class="section-kicker" data-i18n="science_eyebrow">Science news explained</div>
        <h2 data-i18n="science_title">Science news explained</h2>
        <p data-i18n="science_intro">Recent discoveries turned into simple visual summaries for young readers. Source details stay visible, but quiet.</p>
        <div class="topic-pills" aria-label="Topics represented by the published explainers" data-i18n-aria-label="topics_label">{topic_pills}</div>
        {source_list}
      </div>
    </section>
    <section class="archive-shell" id="science-news">
      <div class="archive-top">
        <div>
          <h2 data-i18n="archive_title">Latest science explainers</h2>
          <p data-i18n="archive_intro">Browse the science news collection separately from biographies and school posters.</p>
        </div>
      </div>
      <div class="masonry science-list">{cards}</div>
    </section>
    {render_process_note()}
    <footer class="footer surface">
      <div><span data-i18n="footer_generated_by">Made with human supervision and</span> <a href="https://roj.world/swarms/famous-people-infographic" target="_blank" rel="noopener noreferrer" data-i18n="footer_swarm">Roj swarm agents</a>.</div>
      <div data-updated="{html.escape(updated)}">Updated: {updated_display}</div>
    </footer>
  </main>
  {render_science_client_script()}
</body>
</html>'''


def render_science_client_script():
    return r'''<script>
(function () {
  const defaultLang = 'en';
  let uiLang = localStorage.getItem('archive-ui-lang') || defaultLang;
  const dict = {
    en: {
      document_title: 'Science news explained - Visual Learning Archive',
      brand_title: 'Visual Learning Archive',
      brand_subtitle: 'Accessible infographics about people, school topics and science discoveries.',
      lang_picker_label: 'Site language',
      latest_explainer: 'Latest explainer',
      science_eyebrow: 'Science news explained',
      science_title: 'Science news explained',
      science_intro: 'Recent discoveries turned into simple visual summaries for young readers. Source details stay visible, but quiet.',
      topics_label: 'Topics represented by the published explainers',
      sources_heading: 'Sources',
      sources_empty: 'No sources listed.',
      source: 'Source',
      source_kind_research_paper: 'Research paper',
      source_kind_research_record: 'Research record',
      source_kind_news_explainer: 'News explainer',
      source_kind_news_article: 'News article',
      source_kind_research_news: 'Research news',
      source_kind_website: 'Website',
      archive_title: 'Latest science explainers',
      archive_intro: 'Browse the science news collection separately from biographies and school posters.',
      process_eyebrow: 'How these infographics are made',
      process_title: 'Human-supervised visual learning',
      process_body: 'This archive is created with help from Roj swarm agents - small AI assistants that help gather sources, summarize topics, draft clear explanations and prepare visual material. Human review keeps the archive focused, reliable and useful for learning.',
      footer_generated_by: 'Made with human supervision and',
      footer_swarm: 'Roj swarm agents',
      updated: 'Updated:',
      original_article: 'Read the original article ↗',
      image_details: 'Show image details',
      open_infographic: 'Open infographic:',
      infographic: 'Infographic:',
      category_science_news: 'Science news',
      age_age_6: 'Ages 6+',
      age_age_13: 'Ages 13+',
      age_adult: 'Adults',
      sources_zero: 'No sources',
      sources_one: '1 source',
      sources_many: '{count} sources'
    },
    sl: {
      document_title: 'Razložene znanstvene novice - Arhiv vizualnega učenja',
      brand_title: 'Arhiv vizualnega učenja',
      brand_subtitle: 'Dostopne infografike o ljudeh, šolskih temah in znanstvenih odkritjih.',
      lang_picker_label: 'Jezik strani',
      latest_explainer: 'Najnovejša razlaga',
      science_eyebrow: 'Razložene znanstvene novice',
      science_title: 'Razložene znanstvene novice',
      science_intro: 'Najnovejša odkritja v preprostih vizualnih povzetkih za mlade bralce. Viri ostanejo vedno vidni.',
      topics_label: 'Teme, ki jih obravnavajo objavljene infografike',
      sources_heading: 'Viri',
      sources_empty: 'Viri niso navedeni.',
      source: 'Vir',
      source_kind_research_paper: 'Raziskovalni članek',
      source_kind_research_record: 'Zapis raziskave',
      source_kind_news_explainer: 'Poljudna razlaga',
      source_kind_news_article: 'Novinarski članek',
      source_kind_research_news: 'Novica o raziskavi',
      source_kind_website: 'Spletna stran',
      archive_title: 'Najnovejše znanstvene razlage',
      archive_intro: 'Prebrskaj zbirko znanstvenih novic ločeno od biografij in šolskih plakatov.',
      process_eyebrow: 'Kako nastajajo infografike',
      process_title: 'Vizualno učenje s človeškim pregledom',
      process_body: 'Arhiv nastaja s pomočjo Roj swarm agentov - majhnih AI pomočnikov, ki pomagajo zbrati vire, povzeti teme, pripraviti jasne razlage in vizualno gradivo. Človeški pregled skrbi, da je arhiv osredotočen, zanesljiv in uporaben za učenje.',
      footer_generated_by: 'Ustvarjeno s človeškim pregledom in pomočjo',
      footer_swarm: 'Roj swarm agentov',
      updated: 'Posodobljeno:',
      original_article: 'Preberi izvirni članek ↗',
      image_details: 'Pokaži podrobnosti slike',
      open_infographic: 'Odpri infografiko:',
      infographic: 'Infografika:',
      category_science_news: 'Znanstvena novica',
      age_age_6: '6+ let',
      age_age_13: '13+ let',
      age_adult: 'Odrasli',
      sources_zero: 'Brez virov',
      sources_one: '1 vir',
      sources_many: '{count} viri'
    }
  };

  function t(key, params) {
    let value = (dict[uiLang] && dict[uiLang][key]) || dict.en[key] || key;
    Object.entries(params || {}).forEach(([name, replacement]) => {
      value = value.replace(`{${name}}`, replacement);
    });
    return value;
  }

  function compactSourceUrl(url) {
    return url.length <= 44 ? url : `${url.slice(0, 43)}…`;
  }

  function sourceCountLabel(count) {
    if (count === 1) return t('sources_one');
    return count ? t('sources_many', {count}) : t('sources_zero');
  }

  function formatUpdated(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})/);
    if (!match) return value || '';
    return `${Number(match[3])}. ${Number(match[2])}. ${match[1]}, ${match[4]}`;
  }

  function updateTranslations() {
    document.documentElement.lang = uiLang;
    document.title = t('document_title');
    document.querySelectorAll('[data-i18n]').forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach((node) => {
      node.setAttribute('aria-label', t(node.dataset.i18nAriaLabel));
    });
    document.querySelectorAll('[data-source-index][data-source-url]').forEach((node) => {
      const name = node.dataset.sourceName || `${t('source')} ${node.dataset.sourceIndex}`;
      node.textContent = `${name} — ${t(`source_kind_${node.dataset.sourceKind || 'website'}`)}`;
    });
    document.querySelectorAll('[data-topic-label]').forEach((node) => {
      node.textContent = uiLang === 'sl' ? node.dataset.labelSl : node.dataset.labelEn;
    });
    document.querySelectorAll('[data-localized-title]').forEach((node) => {
      node.textContent = uiLang === 'sl' ? node.dataset.titleSl : node.dataset.titleEn;
    });
    document.querySelectorAll('[data-infographic-link]').forEach((node) => {
      const title = uiLang === 'sl' ? node.dataset.titleSl : node.dataset.titleEn;
      node.setAttribute('aria-label', `${t('open_infographic')} ${title}`);
      const image = node.querySelector('img');
      if (image) image.alt = `${t('infographic')} ${title}`;
    });
    document.querySelectorAll('[data-original-article-link]').forEach((node) => {
      node.textContent = t('original_article');
    });
    document.querySelectorAll('[data-info-label]').forEach((node) => {
      node.setAttribute('aria-label', t('image_details'));
    });
    document.querySelectorAll('[data-category-tag="science_news"]').forEach((node) => {
      node.textContent = t('category_science_news');
    });
    document.querySelectorAll('[data-source-count]').forEach((node) => {
      node.textContent = sourceCountLabel(Number(node.dataset.sourceCount || 0));
    });
    document.querySelectorAll('[data-age-tag]').forEach((node) => {
      const parent = node.closest('[data-age-suitability]');
      const keys = (parent?.dataset.ageSuitability || '').split(/\s+/).filter(Boolean);
      node.textContent = keys.map((key) => t(`age_${key}`)).join(', ');
    });
    const updatedNode = document.querySelector('[data-updated]');
    if (updatedNode) updatedNode.textContent = `${t('updated')} ${formatUpdated(updatedNode.dataset.updated)}`;
    document.querySelectorAll('[data-lang-option]').forEach((button) => {
      const active = button.dataset.langOption === uiLang;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => {
      uiLang = button.dataset.langOption;
      localStorage.setItem('archive-ui-lang', uiLang);
      updateTranslations();
    });
  });

  updateTranslations();
})();
</script>'''


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
      <option value="people" data-category-option="people">Famous people</option>
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

  function addCardBackdrops(root) {
    root.querySelectorAll('.thumb').forEach((thumb) => {
      const image = thumb.querySelector('img:not(.thumb-backdrop)');
      if (!image || thumb.querySelector('.thumb-backdrop')) return;
      const backdrop = image.cloneNode(false);
      backdrop.className = 'thumb-backdrop';
      backdrop.alt = '';
      backdrop.setAttribute('aria-hidden', 'true');
      image.classList.add('thumb-image');
      thumb.prepend(backdrop);
    });
  }

  addCardBackdrops(masonry);
  const initialMarkup = masonry.innerHTML;
  const defaultLang = 'en';
  let uiLang = localStorage.getItem('archive-ui-lang') || defaultLang;
  let entries = [];

  const dict = {
    en: {
      document_title: 'Visual Learning Archive',
      brand_title: 'Visual Learning Archive',
      brand_subtitle: 'Accessible infographics about people, school topics and science discoveries',
      kofi: 'Support the site author',
      hero_eyebrow: 'Visual learning archive',
      hero_title: 'Visual explanations for curious learners',
      hero_intro: 'Accessible infographics about people, school topics and science discoveries. Browse the latest image, choose a collection, or search the full archive.',
      archive_heading_home: 'Search the full archive',
      archive_heading_page: 'Archive – page {page}',
      archive_intro_home: 'Search by person, topic, collection, image language and age suitability.',
      archive_intro_page: 'Browse older infographics and explainers by page or use search and filters.',
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
      footer_text: 'Visual Learning Archive: accessible infographics about people, school topics and science discoveries.',
      footer_generated_by: 'Made with human supervision and',
      footer_swarm: 'Roj swarm agents',
      updated: 'Updated:',
      search_unavailable: 'Search and filters are currently unavailable.',
      pager_previous: '← Previous',
      pager_next: 'Next →',
      lang_picker_label: 'Site language',
      category_people: 'Famous people',
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
      collections_title: 'Choose a collection',
      collections_intro: 'Carefully curated infographics and explainers for curious minds.',
      collections_all_link: 'Browse all infographics ↓',
      collection_people_title: 'Famous people',
      collection_people_desc: 'Discover lives and big ideas',
      collection_school_title: 'School posters',
      collection_school_desc: 'Bright, clear posters that make big topics easy to understand',
      collection_science_title: 'Science news explained',
      collection_science_desc: 'Short, visual stories about the latest discoveries and what they mean',
      collection_all_title: 'All infographics',
      collection_all_desc: 'Search the complete archive by topic, collection, language and age level',
      process_eyebrow: 'How these infographics are made',
      process_title: 'Human-supervised visual learning',
      process_body: 'This archive is created with help from Roj swarm agents — small AI assistants that help gather sources, summarize topics, draft clear explanations and prepare visual material. Human review keeps the archive focused, reliable and useful for learning.'
    },
    sl: {
      document_title: 'Arhiv vizualnega učenja',
      brand_title: 'Arhiv vizualnega učenja',
      brand_subtitle: 'Dostopne infografike o ljudeh, šolskih temah in znanstvenih odkritjih',
      kofi: 'Podpri avtorja strani',
      hero_eyebrow: 'Arhiv vizualnega učenja',
      hero_title: 'Vizualne razlage za radovedneže',
      hero_intro: 'Dostopne infografike o ljudeh, šolskih temah in znanstvenih odkritjih. Oglej si najnovejšo sliko, izberi zbirko ali preišči celoten arhiv.',
      archive_heading_home: 'Preišči celoten arhiv',
      archive_heading_page: 'Arhiv – stran {page}',
      archive_intro_home: 'Išči po osebi ali temi ter filtriraj po zbirki, jeziku slike in starostni primernosti.',
      archive_intro_page: 'Prelistaj starejše infografike in razlagalnike po straneh ali uporabi iskanje in filtre.',
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
      footer_text: 'Arhiv vizualnega učenja: dostopne infografike o ljudeh, šolskih temah in znanstvenih odkritjih.',
      footer_generated_by: 'Ustvarjeno s človeškim pregledom in pomočjo',
      footer_swarm: 'Roj swarm agentov',
      updated: 'Posodobljeno:',
      search_unavailable: 'Iskanje in filtri trenutno niso na voljo.',
      pager_previous: '← Prejšnja',
      pager_next: 'Naslednja →',
      lang_picker_label: 'Jezik strani',
      category_people: 'Znani ljudje',
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
      collections_title: 'Izberi zbirko',
      collections_intro: 'Skrbno zbrane infografike in razlage za vse radovedneže.',
      collections_all_link: 'Poglej vse infografike ↓',
      collection_people_title: 'Znani ljudje',
      collection_people_desc: 'Življenja in velike ideje zanimivih ljudi',
      collection_school_title: 'Šolski plakati',
      collection_school_desc: 'Jasni plakati, ki velike teme naredijo razumljive',
      collection_science_title: 'Razložene znanstvene novice',
      collection_science_desc: 'Kratke vizualne zgodbe o novih odkritjih in njihovem pomenu',
      collection_all_title: 'Vse infografike',
      collection_all_desc: 'Preišči celoten arhiv po temi, zbirki, jeziku in starosti',
      process_eyebrow: 'Kako nastajajo infografike',
      process_title: 'Vizualno učenje s človeškim pregledom',
      process_body: 'Arhiv nastaja s pomočjo Roj swarm agentov — majhnih AI pomočnikov, ki pomagajo zbrati vire, povzeti teme, pripraviti jasne razlage in vizualno gradivo. Človeški pregled skrbi, da je arhiv osredotočen, zanesljiv in uporaben za učenje.'
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

  function displayTitle(value) {
    const title = String(value ?? '');
    return title ? title.charAt(0).toLocaleUpperCase() + title.slice(1) : '';
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

  function compactSourceUrl(url) {
    return url.length <= 44 ? url : `${url.slice(0, 43)}…`;
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
    return `<ul class="sources">${sources.slice(0, 4).map((url, index) => `<li><a href="${escapeHtml(url)}" title="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-source-index="${index + 1}" data-source-url="${escapeHtml(url)}">${escapeHtml(t('source'))} ${index + 1} (${escapeHtml(compactSourceUrl(url))})</a></li>`).join('')}</ul>`;
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
    const person = displayTitle(entry.person);
    return `<article class="card${featureClass}" data-person="${escapeHtml(entry.person)}" data-category="${escapeHtml(entry.category)}" data-language="${escapeHtml(entry.language)}" data-age-suitability="${escapeHtml(ageKeys.join(' '))}">
      <a class="thumb" href="${escapeHtml(entry.filename)}" aria-label="Open infographic: ${escapeHtml(person)}"><img src="${escapeHtml(entry.filename)}" alt="Infographic: ${escapeHtml(person)}" loading="lazy"></a>
      <div class="image-title"><h3>${escapeHtml(person)}</h3></div>
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
    document.querySelectorAll('[data-source-index][data-source-url]').forEach((node) => {
      node.textContent = `${t('source')} ${node.dataset.sourceIndex} (${compactSourceUrl(node.dataset.sourceUrl)})`;
    });
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
      if (category === 'people' && !['artist', 'scientist', 'sport'].includes(entry.category)) return false;
      if (category && category !== 'people' && entry.category !== category) return false;
      if (language && entry.language !== language) return false;
      if (age && !(entry.age_suitability_keys || []).includes(age)) return false;
      return true;
    });

    masonry.innerHTML = filtered.length
      ? filtered.map((entry, index) => renderCard(entry, index % 4 === 0)).join('')
      : `<p class="empty">${escapeHtml(t('no_results'))}</p>`;
    addCardBackdrops(masonry);
    summary.dataset.dynamic = 'true';
    summary.textContent = t('found', {count: filtered.length});
    if (pagination) pagination.classList.add('is-hidden');
    updateStaticTranslations();
  }

  function setCategoryControlForCollection(collection) {
    const exactCategory = collection && collection !== 'all' ? collection : '';
    categorySelect.value = Array.from(categorySelect.options).some((option) => option.value === exactCategory) ? exactCategory : '';
  }

  function applyQueryParams() {
    const params = new URLSearchParams(window.location.search);
    const collection = params.get('collection') || '';
    masonry.dataset.collection = collection;
    setCategoryControlForCollection(collection);
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
      setCategoryControlForCollection(masonry.dataset.collection);
      searchInput.value = '';
      const target = new URL(href || './', window.location.href);
      if (collection === 'all' || !collection) target.searchParams.delete('collection');
      target.searchParams.delete('category');
      target.searchParams.delete('q');
      target.hash = 'archive';
      history.pushState({}, '', target);
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

BASE_CSS = """
    :root {{ color-scheme:light; --bg:#f4ecd9; --paper:#fff9eb; --panel:#fffdf6; --ink:#12391f; --body:#25231d; --muted:#6f674f; --line:#dacdb4; --accent:#b87408; --forest:#12391f; --chip:#eee3cc; --shadow:0 18px 42px rgba(47,35,15,.16); --radius:28px; }}
    * {{ box-sizing:border-box; }} html {{ scroll-behavior:smooth; }}
    body {{ margin:0; background:radial-gradient(circle at 8% 18%, rgba(184,116,8,.12), transparent 24rem),radial-gradient(circle at 88% 4%, rgba(18,57,31,.10), transparent 22rem),linear-gradient(180deg,#fbf5e5,var(--bg)); color:var(--body); font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; }}
    body::before {{ content:''; position:fixed; inset:0; pointer-events:none; opacity:.34; z-index:-1; background-image:radial-gradient(rgba(80,57,23,.16) .7px,transparent .7px); background-size:5px 5px; mix-blend-mode:multiply; }}
    a {{ color:inherit; }} .wrap {{ max-width:1480px; margin:0 auto; padding:28px 26px 64px; }} .surface {{ background:rgba(255,249,235,.78); border:1px solid rgba(218,205,180,.86); border-radius:30px; box-shadow:var(--shadow); }}
    .nav {{ position:sticky; top:18px; z-index:10; display:flex; justify-content:space-between; align-items:center; gap:20px; padding:16px 20px; background:rgba(251,245,229,.82); backdrop-filter:blur(14px); border:1px solid rgba(218,205,180,.7); border-radius:24px; }}
    .brand,.nav-actions,.hero-chips,.meta-row,.pagination,.topic-pills {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }} .brand {{ gap:14px; }} .brand-link {{ text-decoration:none; }}
    .logo {{ width:52px; height:52px; flex:0 0 52px; border-radius:15px; display:grid; place-items:center; color:var(--forest); border:1px solid rgba(18,57,31,.28); background:#fff9eb; }} .logo img {{ width:46px; height:46px; display:block; }} .brand > div:last-child {{ min-width:0; }}
    .brand h1 {{ margin:0; font-family:'Fraunces',Georgia,serif; color:var(--forest); font-size:25px; line-height:1.05; letter-spacing:-.02em; }} .brand p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
    .pill {{ display:inline-flex; align-items:center; gap:8px; padding:10px 15px; border-radius:999px; background:var(--chip); border:1px solid #d8c8aa; font-size:14px; color:#453b29; text-decoration:none; }} .pill.primary {{ background:linear-gradient(135deg,#ca820d,#a95f05); border-color:#b66d06; color:#fff; font-weight:800; box-shadow:0 14px 26px rgba(184,116,8,.22); }} .pill.soft {{ background:rgba(255,249,235,.72); }}
    .support-note {{ max-width:360px; text-align:right; color:var(--muted); font-size:13px; line-height:1.35; }} .support-note a,.footer a,.text-link {{ color:var(--forest); font-weight:850; text-decoration:none; }} .support-note a:hover,.footer a:hover,.text-link:hover {{ text-decoration:underline; }} .kofi-link {{ display:inline-flex; align-items:center; gap:5px; }} .kofi-icon {{ width:22px; height:auto; display:inline-block; }} .nav-right {{ display:flex; align-items:center; justify-content:flex-end; gap:14px; flex-wrap:wrap; }}
    .lang-picker {{ display:inline-flex; align-items:center; gap:6px; padding:6px; border-radius:999px; background:#fff9eb; border:1px solid var(--line); }} .lang-icon {{ width:22px; height:22px; display:grid; place-items:center; font-size:16px; }} .lang-picker button {{ border:0; border-radius:999px; background:transparent; color:#51483f; font:inherit; font-size:12px; font-weight:800; padding:7px 9px; cursor:pointer; }} .lang-picker button.active {{ background:var(--forest); color:#fff; }}
    .hero {{ margin-top:26px; }} .hero-desk {{ position:relative; min-height:760px; padding:52px 24px 0; overflow:hidden; }} .hero-desk::after {{ content:''; position:absolute; left:-4%; right:-4%; bottom:0; height:108px; background:linear-gradient(180deg,#7a5229,#513216); border-radius:50% 50% 0 0 / 42% 42% 0 0; box-shadow:0 -18px 42px rgba(55,33,12,.18); }}
    .hero-copy {{ position:relative; z-index:2; max-width:960px; margin:0 auto; text-align:center; }} .eyebrow,.section-kicker {{ font-size:12px; font-weight:900; letter-spacing:.18em; text-transform:uppercase; color:#b87408; }}
    .hero-copy h2 {{ font-family:'Fraunces',Georgia,serif; font-size:clamp(56px,7vw,98px); line-height:.95; letter-spacing:-.055em; color:var(--forest); margin:18px auto 8px; max-width:13ch; text-wrap:balance; }} .ornament {{ color:#ba790a; display:flex; align-items:center; justify-content:center; gap:16px; margin:12px 0 14px; }} .ornament span {{ width:116px; height:1px; background:#c08a2b; display:block; }} .intro {{ margin:-8px auto 0; color:#2f2b22; font-size:19px; font-weight:500; line-height:1.55; max-width:760px; }}
    .hero-chips {{ justify-content:center; }} .hero-chip {{ min-width:230px; justify-content:space-between; display:inline-flex; align-items:center; gap:14px; margin-top:20px; padding:15px 20px; border-radius:14px; background:rgba(255,248,230,.92); border:1px solid rgba(18,57,31,.22); text-decoration:none; color:#0d331b; box-shadow:0 12px 28px rgba(47,35,15,.14),0 0 0 1px rgba(255,255,255,.65) inset; transition:transform .45s cubic-bezier(.32,.72,0,1),box-shadow .45s cubic-bezier(.32,.72,0,1),background .45s cubic-bezier(.32,.72,0,1); }} .hero-chip:hover,.hero-chip:focus-visible {{ transform:translateY(-3px); background:#fffdf4; box-shadow:0 20px 38px rgba(47,35,15,.22),0 0 0 1px rgba(255,255,255,.85) inset; outline:3px solid rgba(184,116,8,.22); outline-offset:3px; }} .hero-chip strong {{ font-family:'Fraunces',Georgia,serif; font-size:19px; font-weight:900; text-shadow:none; }}
    .poster-stage {{ position:absolute; z-index:1; left:50%; bottom:10px; width:min(1120px,94%); height:350px; transform:translateX(-50%); }} .hero-card,.hero-poster {{ position:absolute; border:1px solid rgba(203,189,164,.75); border-radius:14px; box-shadow:0 24px 40px rgba(42,30,13,.28); overflow:hidden; }} .hero-card {{ left:50%; bottom:30px; width:min(560px,55vw); height:315px; transform:translateX(-50%) rotate(-.5deg); z-index:4; background:#12391f; }} .hero-poster {{ bottom:36px; width:360px; height:260px; padding:0; object-fit:cover; object-position:center; background:transparent; }} .poster-1 {{ left:0; transform:rotate(-5deg); z-index:2; }} .poster-2 {{ right:0; transform:rotate(5deg); z-index:1; }}
    .hero-image-wrap,.thumb {{ position:absolute; inset:0; display:block; overflow:hidden; text-decoration:none; background:#fffaf0; }} .hero-image-wrap img {{ width:100%; height:100%; display:block; object-fit:cover; object-position:top center; }} .thumb img {{ position:absolute; inset:0; width:100%; height:100%; display:block; object-fit:contain; object-position:center; }} .thumb-backdrop {{ object-fit:cover; filter:blur(18px) brightness(.62) saturate(.82); transform:scale(1.12); }} .thumb-image {{ z-index:1; object-fit:contain; }} .hero-title-overlay h3 {{ font-size:26px; }}
    .collections-hub,.process-note,.science-hero {{ margin-top:30px; }} .collections-heading-row {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px; }} .collections-heading-row h2,.process-note h2,.science-hero h2 {{ margin:0; font-family:'Fraunces',Georgia,serif; color:var(--forest); font-size:clamp(42px,5vw,76px); line-height:.96; letter-spacing:-.045em; text-wrap:balance; }} .collections-heading-row p,.process-note p,.science-hero p {{ margin:12px 0 0; color:#2f2b22; font-size:18px; line-height:1.55; max-width:64ch; }}
    .collection-grid {{ display:grid; grid-template-columns:1.04fr 1fr; gap:22px; }} .collection-card {{ position:relative; min-height:280px; display:flex; flex-direction:column; justify-content:space-between; gap:16px; padding:30px; border-radius:28px; text-decoration:none; border:1px solid rgba(218,205,180,.9); background:rgba(255,249,235,.72); overflow:hidden; box-shadow:var(--shadow); transition:transform .22s ease,box-shadow .22s ease; }} .collection-card:hover,.collection-card:focus-visible {{ transform:translateY(-4px); box-shadow:0 24px 48px rgba(47,35,15,.22); outline:0; }} .collection-card:active {{ transform:translateY(-1px) scale(.99); }} .collection-card.featured-collection {{ min-height:590px; grid-row:span 2; background:linear-gradient(140deg,#10371e,#1f5130); color:#fff9eb; }} .collection-card.school,.collection-card.science-news,.collection-card.all {{ min-height:280px; }} .collection-card.school {{ background:#fff8e9; }} .collection-card.science-news {{ background:#e5ead9; }} .collection-card.all {{ background:#f8efdc; }}
    .collection-copy {{ position:relative; z-index:2; max-width:310px; }} .collection-copy strong {{ display:block; font-family:'Fraunces',Georgia,serif; color:var(--forest); font-size:clamp(34px,4vw,58px); line-height:.95; letter-spacing:-.04em; }} .featured-collection .collection-copy strong,.featured-collection .collection-copy small {{ color:#fff9eb; }} .collection-copy small {{ display:block; margin-top:14px; color:#2f2b22; font-size:17px; line-height:1.45; }} .collection-cta {{ position:relative; z-index:3; align-self:flex-start; padding:13px 18px; border-radius:10px; background:#fff9eb; color:#12391f; font-weight:900; box-shadow:0 12px 24px rgba(34,24,8,.14); }} .school .collection-cta,.science-news .collection-cta,.all .collection-cta {{ background:var(--forest); color:#fff9eb; }}
    .collection-art {{ position:absolute; inset:auto 0 0 auto; z-index:1; pointer-events:none; }} .science-art {{ inset:0; }} .people-art {{ width:78%; height:70%; right:-2%; bottom:42px; }} .people-sheet {{ position:absolute; object-fit:cover; background:#fffaf0; border:1px solid #cebfa4; border-radius:8px; box-shadow:0 18px 32px rgba(11,25,11,.36); }} .sheet-main {{ width:52%; height:78%; right:5%; bottom:10%; transform:rotate(3deg); }} .sheet-left {{ width:42%; height:62%; left:2%; bottom:0; transform:rotate(-6deg); }} .sheet-right {{ width:40%; height:58%; right:-4%; bottom:0; transform:rotate(6deg); }} .mini-poster {{ position:absolute; object-fit:cover; width:210px; height:190px; right:28px; bottom:32px; border:1px solid #cbbda4; border-radius:8px; background:#fffaf0; box-shadow:0 16px 26px rgba(47,35,15,.18); }} .school-two {{ right:160px; bottom:42px; transform:rotate(-7deg); }} .school-one {{ transform:rotate(5deg); }} .science-preview-image,.all-preview-image {{ position:absolute; right:24px; bottom:24px; width:45%; height:70%; object-fit:cover; border-radius:12px; border:1px solid #cbbda4; box-shadow:0 16px 26px rgba(47,35,15,.18); }}
    .process-note {{ padding:32px; background:linear-gradient(135deg,rgba(255,249,235,.88),rgba(229,234,217,.82)); }} .editorial-science-simple {{ display:grid; grid-template-columns:minmax(0,1.4fr) minmax(390px,.7fr); gap:34px; align-items:stretch; background:transparent; }} .science-hero-copy {{ padding:42px; box-shadow:none; display:flex; flex-direction:column; justify-content:center; }} .science-hero-copy h2 {{ font-size:clamp(50px,4vw,64px); }} .science-hero-art {{ position:relative; min-height:600px; overflow:hidden; border-radius:26px; background:#0d2d19; box-shadow:var(--shadow); }} .science-hero-art::after {{ content:''; position:absolute; inset:0; background:linear-gradient(180deg,transparent 62%,rgba(6,32,17,.78)); pointer-events:none; }} .science-hero-image {{ position:absolute; inset:0; width:100%; height:100%; object-fit:contain; object-position:center; background:#0b2c19; filter:saturate(.94) contrast(1.04); }} .science-hero-caption {{ position:absolute; z-index:2; left:28px; right:28px; bottom:24px; display:flex; align-items:center; justify-content:space-between; gap:20px; color:#fff9eb; font-size:13px; letter-spacing:.08em; text-transform:uppercase; }} .science-hero-caption strong {{ max-width:62%; text-align:right; font-family:'Fraunces',Georgia,serif; font-size:18px; line-height:1.15; letter-spacing:0; text-transform:none; }} .topic-pills {{ margin-top:22px; display:grid; grid-template-columns:1fr 1fr; }} .topic-pills span {{ display:inline-flex; justify-content:flex-start; gap:8px; padding:14px 16px; border-radius:999px; background:#eee4d0; color:#403829; }} .science-sources {{ margin-top:24px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); font-size:14px; }} .science-sources h3 {{ margin:0; color:var(--forest); font-size:15px; }} .science-sources ul {{ display:grid; gap:8px; margin:10px 0 0; padding:0; list-style:none; }} .science-sources a {{ display:block; overflow-wrap:anywhere; color:var(--forest); text-decoration:underline; text-underline-offset:2px; }}
    .archive-shell {{ margin-top:30px; padding:28px; background:rgba(255,249,235,.74); border:1px solid var(--line); border-radius:30px; box-shadow:var(--shadow); }} .archive-top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px; }} .archive-top h2 {{ margin:0; font-family:'Fraunces',Georgia,serif; color:var(--forest); font-size:42px; letter-spacing:-.04em; }} .archive-top p {{ margin:8px 0 0; color:var(--muted); font-size:17px; max-width:60ch; }}
    .masonry {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px; align-items:stretch; }} .card,.image-card {{ position:relative; isolation:isolate; margin:0; background:#fffaf0; border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:0 14px 28px rgba(47,35,15,.12); aspect-ratio:16/9; }} .card.feature {{ box-shadow:0 18px 36px rgba(47,35,15,.18); }} .image-title {{ position:absolute; left:0; right:0; bottom:0; z-index:2; padding:58px 16px 14px; color:#fff; background:linear-gradient(180deg,transparent,rgba(18,57,31,.74)); pointer-events:none; }} .image-title h3 {{ margin:0; font-family:'Fraunces',Georgia,serif; font-size:22px; line-height:1.05; letter-spacing:-.03em; text-shadow:0 1px 12px rgba(0,0,0,.38); }} .card.feature .image-title h3 {{ font-size:28px; }}
    .info-popover {{ position:absolute; top:12px; right:12px; z-index:4; max-width:calc(100% - 24px); }} .info-popover[open] {{ right:12px; bottom:auto; }} .info-popover summary {{ list-style:none; }} .info-popover summary::-webkit-details-marker {{ display:none; }} .info-button {{ width:32px; height:32px; display:grid; place-items:center; margin-left:auto; border-radius:999px; border:1px solid rgba(255,255,255,.5); background:rgba(255,249,235,.64); color:rgba(18,57,31,.82); font-weight:850; font-size:15px; box-shadow:0 6px 16px rgba(0,0,0,.10); backdrop-filter:blur(8px); cursor:pointer; }} .info-button:hover,.info-button:focus-visible {{ background:var(--forest); color:#fff; outline:0; }} .info-panel {{ position:absolute; top:42px; right:0; width:min(300px,calc(100vw - 76px)); max-height:min(148px,calc(100vh - 156px)); overflow:auto; padding:10px; border-radius:16px; background:rgba(255,253,249,.95); border:1px solid rgba(255,255,255,.9); box-shadow:0 16px 38px rgba(0,0,0,.2); backdrop-filter:blur(16px); }} .info-panel .meta-row {{ gap:7px; }} .info-panel .tag {{ padding:6px 9px; }} .info-panel .sources {{ margin-top:9px; gap:6px; }} .info-panel .sources a {{ padding:6px 9px; }}
    .original-article {{ display:flex; align-items:center; justify-content:center; margin-top:9px; padding:8px 10px; border-radius:11px; background:#edf3e4; border:1px solid #d5dfc5; color:#12391f; font-size:12px; font-weight:800; text-decoration:none; }} .original-article:hover,.original-article:focus-visible {{ background:#e2edd6; text-decoration:underline; outline:0; }} .tag {{ display:inline-flex; padding:7px 10px; border-radius:999px; background:#f1e8d6; border:1px solid #e1d1b4; font-size:12px; color:#564f47; }} .tag[hidden] {{ display:none!important; }} .tag.artist {{ background:#f3d7d1; border-color:#e8c4bc; color:#7d2a22; }} .tag.science,.tag.school-poster,.tag.science-news,.tag.source-count {{ background:#e5ead9; border-color:#ccd8bd; color:#285c33; }} .tag.sport,.tag.age {{ background:#fff4cf; border-color:#ead694; color:#6d5208; }} .tag.language {{ background:#eee3cc; border-color:#dccaa9; color:#554327; }}
    .filter-bar {{ display:grid; grid-template-columns:minmax(220px,1.6fr) repeat(3,minmax(150px,.8fr)); gap:12px; margin:0 0 18px; }} .filter-control {{ display:flex; flex-direction:column; gap:6px; }} .filter-control label {{ font-size:13px; color:var(--muted); font-weight:800; }} .filter-control input,.filter-control select {{ width:100%; padding:13px 14px; border-radius:14px; border:1px solid var(--line); background:#fffaf0; color:var(--body); font:inherit; }} .results-summary {{ margin:0 0 14px; color:var(--muted); font-size:14px; }} .sources {{ list-style:none; display:grid; gap:8px; padding:0; margin:12px 0 0; }} .sources a {{ display:block; overflow-wrap:anywhere; padding:7px 10px; border-radius:10px; text-decoration:none; background:#faf7f2; border:1px solid var(--line); color:#594e44; font-size:12px; }} .sources a:hover {{ text-decoration:underline; }} .pagination {{ margin-top:22px; justify-content:flex-end; }} .pagination.is-hidden {{ display:none; }} .footer {{ margin-top:24px; padding:18px 22px; display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:14px; }} .empty {{ color:var(--muted); font-size:16px; }}
    @media (max-width:700px) {{ .editorial-science-simple,.science-hero-copy,.archive-shell,.science-list,.science-list .card {{ min-width:0; width:100%; }} .science-hero-copy h2,.archive-top h2 {{ font-size:clamp(38px,12vw,56px); overflow-wrap:anywhere; }} .science-list .image-title {{ padding:72px 14px 13px; background:linear-gradient(180deg,transparent,rgba(12,43,24,.9)); }} .science-list .image-title h3,.science-list .card.feature .image-title h3 {{ max-width:100%; font-size:clamp(16px,5vw,20px); line-height:1.12; letter-spacing:-.02em; overflow-wrap:anywhere; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:4; overflow:hidden; }} }}
    @media (max-width:1200px) {{ .masonry {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }} @media (max-width:1000px) {{ .collection-grid {{ grid-template-columns:1fr; }} .collection-card.featured-collection {{ min-height:480px; }} .poster-stage {{ position:relative; left:auto; bottom:auto; transform:none; width:100%; margin-top:32px; }} .hero-desk {{ min-height:auto; padding-bottom:30px; }} .hero-desk::after {{ display:none; }} .editorial-science-simple {{ grid-template-columns:1fr; }} .science-hero-art {{ min-height:520px; }} }} @media (max-width:700px) {{ .nav {{ position:static; flex-direction:column; align-items:stretch; }} .brand {{ align-items:flex-start; }} .brand h1,.brand p {{ overflow-wrap:anywhere; }} .nav-right {{ justify-content:flex-start; }} .support-note {{ max-width:none; text-align:left; }} .archive-top,.footer,.collections-heading-row {{ flex-direction:column; align-items:flex-start; }} .pagination {{ justify-content:flex-start; }} .intro {{ font-size:17px; }} .hero-desk {{ padding:40px 10px 24px; }} .hero-copy {{ width:100%; min-width:0; }} .hero-copy h2 {{ width:100%; max-width:100%; font-size:clamp(38px,11.5vw,46px); line-height:.98; letter-spacing:-.06em; overflow-wrap:normal; }} .ornament span {{ width:72px; }} .wrap {{ width:100%; max-width:100%; overflow:hidden; padding:18px 14px 44px; }} .filter-bar {{ grid-template-columns:1fr; }} .masonry {{ grid-template-columns:1fr; }} .hero-chips {{ width:100%; }} .hero-chip {{ width:100%; min-width:0; margin-top:8px; }} .poster-stage {{ height:310px; }} .hero-card {{ width:78%; height:220px; }} .hero-poster {{ width:210px; height:160px; }} .poster-2 {{ display:none; }} .collection-card {{ padding:24px; min-height:330px; }} .mini-poster {{ width:155px; height:140px; }} .science-preview-image,.all-preview-image {{ width:52%; height:54%; }} .science-hero-art {{ min-height:390px; }} .science-hero-copy {{ padding:28px; }} .science-hero-caption {{ left:18px; right:18px; bottom:16px; align-items:flex-start; flex-direction:column; gap:4px; }} .science-hero-caption strong {{ max-width:100%; text-align:left; }} .topic-pills {{ grid-template-columns:1fr 1fr; }} .info-popover[open] {{ left:12px; right:12px; bottom:12px; max-width:none; }} .info-popover[open] .info-panel {{ width:min(276px,100%); max-width:100%; max-height:min(104px,calc(100% - 54px)); }} .info-panel .tag,.info-panel .sources a {{ padding:5px 8px; font-size:11px; }} }}
  """


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
  <meta name="description" content="Accessible infographics about people, school topics and science discoveries.">
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400..900&family=Fraunces:opsz,wght,SOFT,WONK@9..144,600..900,50..100,1&display=swap" rel="stylesheet">
  <style>{BASE_CSS.replace('{{', '{').replace('}}', '}')}</style>
</head>
<body>
  <main class="wrap">
    <header class="nav">
      <div class="brand">
        <div class="logo"><img src="favicon.svg" alt=""></div>
        <div>
          <h1 data-i18n="brand_title">Visual Learning Archive</h1>
          <p data-i18n="brand_subtitle">Accessible infographics about people, school topics and science discoveries</p>
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
    {render_collection_hub(collection_stats(entries), collection_preview_set(entries)) if page_num == 1 else ''}
    <section class="archive-shell" id="archive">
      <div class="archive-top">
        <div>
          <h2 data-archive-heading="1" data-page="{page_num}">{page_heading}</h2>
          <p data-archive-intro="1" data-page="{page_num}">{page_intro}</p>
        </div>
      </div>
      {filters_html}
      <div class="masonry">{cards}</div>
      {pagination}
    </section>
    {render_process_note() if page_num == 1 else ''}
    <footer class="footer surface">
      <div><span data-i18n="footer_text">Visual Learning Archive: accessible infographics about people, school topics and science discoveries.</span> <span data-i18n="footer_generated_by">Made with human supervision and</span> <a href="https://roj.world/swarms/famous-people-infographic" target="_blank" rel="noopener noreferrer" data-i18n="footer_swarm">Roj swarm agents</a>.</div>
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
(PUBLIC_ROOT / FAVICON_FILENAME).write_text(FAVICON_SVG + '\n', encoding='utf-8')

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
