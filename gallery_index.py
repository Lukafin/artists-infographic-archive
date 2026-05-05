#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter

CATEGORY_LABELS = {
    'artist': ('Umetnik', 'artist'),
    'scientist': ('Znanstvenik', 'science'),
    'sport': ('Športnik', 'sport'),
}

LANGUAGE_LABELS = {
    'sl': 'SL',
    'en': 'EN',
    'de': 'DE',
}

AGE_SUITABILITY_LEVELS = {
    'age_6': {'label_en': 'Ages 6+', 'label_sl': '6+ let'},
    'age_13': {'label_en': 'Ages 13+', 'label_sl': '13+ let'},
    'adult': {'label_en': 'Adults', 'label_sl': 'Odrasli'},
}


def classify_person(person: str) -> str:
    person_lower = (person or '').lower()
    artist_terms = [
        'chan', 'raffaello', 'raphael', 'muybridge', 'merian', 'picasso', 'monet',
        'van gogh', 'mozart', 'beethoven', 'davinci', 'da vinci', 'michelangelo',
        'kahlo', 'warhol', 'dali', 'matisse', 'rembrandt', 'caravaggio',
        'lady gaga', 'kurosawa', 'mussorgsky', 'rafael', 'sanzio',
        'mercury', 'bowie', 'madonna', 'hendrix', 'bach', 'vivaldi', 'verdi',
        'ellington', 'miró', 'miro', 'botero', 'stokowski', 'nolan',
    ]
    sport_terms = [
        'jordan', 'williams', 'biles', 'bolt', 'federer', 'nadal', 'djokovic',
        'pele', 'messi', 'ronaldo', 'bryant', 'senna', 'schumacher',
    ]
    if any(term in person_lower for term in sport_terms):
        return 'sport'
    if any(term in person_lower for term in artist_terms):
        return 'artist'
    return 'scientist'


def normalize_entry_metadata(entry: dict) -> dict:
    normalized = dict(entry)
    category = (normalized.get('category') or '').strip().lower() or classify_person(normalized.get('person', ''))
    if category not in CATEGORY_LABELS:
        category = classify_person(normalized.get('person', ''))
    category_label, category_class = CATEGORY_LABELS[category]

    language = (normalized.get('language') or 'sl').strip().lower() or 'sl'
    language_label = LANGUAGE_LABELS.get(language, language.upper())

    details = normalized.get('age_suitability_details') or {}
    if not isinstance(details, dict):
        details = {}

    explicit_keys = normalized.get('age_suitability_keys') or []
    if isinstance(explicit_keys, str):
        explicit_keys = [explicit_keys]
    age_keys = [key for key in explicit_keys if key in AGE_SUITABILITY_LEVELS]

    # The backend can include age_suitability_details for multiple reading levels
    # on the same kid-friendly image. Those are text variants, not separate image
    # suitability tags. Unless there is a narrower explicit target, treat archive
    # images as the current kid-friendly 6+ level.
    if set(age_keys) == set(AGE_SUITABILITY_LEVELS):
        age_keys = ['age_6']
    if not age_keys:
        target_key = normalized.get('age_suitability_key') or normalized.get('target_age_key')
        if target_key in AGE_SUITABILITY_LEVELS:
            age_keys = [target_key]
        else:
            # Legacy archive entries were produced before age-suitability metadata
            # existed in the backend. Those older kid-friendly Slovenian pages should
            # remain discoverable in the 6+ filter instead of disappearing entirely.
            age_keys = ['age_6']

    age_labels_en = [AGE_SUITABILITY_LEVELS[key]['label_en'] for key in age_keys]
    age_labels_sl = [AGE_SUITABILITY_LEVELS[key]['label_sl'] for key in age_keys]

    person = (normalized.get('person') or '').strip()
    search_parts = [
        person.lower(),
        category,
        category_label.lower(),
        language,
        *age_keys,
        *(label.lower() for label in age_labels_en),
        *(label.lower() for label in age_labels_sl),
    ]

    normalized.update(
        {
            'category': category,
            'category_label': category_label,
            'category_class': category_class,
            'language': language,
            'language_label': language_label,
            'age_suitability_keys': age_keys,
            'age_suitability_labels_en': age_labels_en,
            'age_suitability_labels_sl': age_labels_sl,
            'source_count': len(normalized.get('sources', [])),
            'search_text': ' '.join(part for part in search_parts if part).strip(),
        }
    )
    return normalized


def build_entries_index(entries: list[dict]) -> dict:
    normalized_entries = [normalize_entry_metadata(entry) for entry in entries]
    categories = sorted({entry['category'] for entry in normalized_entries})
    languages = sorted({entry['language'] for entry in normalized_entries})
    category_counts = Counter(entry['category'] for entry in normalized_entries)
    language_counts = Counter(entry['language'] for entry in normalized_entries)
    age_suitability_counts = Counter(
        key
        for entry in normalized_entries
        for key in entry.get('age_suitability_keys', [])
    )
    return {
        'summary': {
            'total_entries': len(normalized_entries),
            'categories': categories,
            'languages': languages,
            'age_suitability_levels': list(AGE_SUITABILITY_LEVELS.keys()),
            'age_suitability_counts': dict(age_suitability_counts),
            'category_counts': dict(category_counts),
            'language_counts': dict(language_counts),
        },
        'entries': normalized_entries,
    }
