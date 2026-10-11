"""Offline import of reviewed backend URL records; no remote fetching or execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from podcasts import identity, eligible, read_json, atomic_json

MODES = {'video': 'native_video', 'interactive_site': 'sandboxed_iframe'}


def safe_url(value):
    if not isinstance(value, str) or len(value) > 4000 or any(c.isspace() or unicodedata.category(c) == 'Cc' for c in value) or '\\' in value or value != value.strip():
        raise ValueError('Invalid URL')
    url = urlsplit(value)
    _ = url.port  # Raises for malformed/out-of-range ports rather than repairing spelling.
    if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password or '@' in url.netloc:
        raise ValueError('Credential-free HTTP(S) required')
    return value


def normalize_media(value, entry):
    if not isinstance(value, dict):
        return None
    try:
        kind = value['artifact_kind']
        mode = value['presentation_mode']
        url = safe_url(value['url'])
        if (kind not in MODES or mode not in ('link', MODES[kind]) or value['language'] != entry['language']
                or not isinstance(value['title'], str) or not 1 <= len(value['title'].strip()) <= 300
                or not re.fullmatch('[0-9a-f]{64}', value['companion_id'])):
            return None
        mime = value.get('mime_type')
        if mode == 'native_video' and (mime not in ('video/mp4', 'video/webm') or not urlsplit(url).path.lower().endswith('.mp4' if mime == 'video/mp4' else '.webm')):
            return None
        return dict(url=url, artifact_kind=kind, presentation_mode=mode, title=value['title'],
                    language=value['language'], companion_id=value['companion_id'], **({'mime_type': mime} if mode == 'native_video' else {}))
    except (ValueError, KeyError, TypeError):
        return None


def import_media(manifest, public_root, store, *, approve=False):
    public_root, store = Path(public_root).resolve(), Path(store).resolve()
    mirror = public_root.parent / 'site'
    if store == public_root or public_root in store.parents or store == mirror or mirror in store.parents:
        raise ValueError('Store must remain private outside docs/site')
    if (not approve or manifest.get('schema') != 'artists-reviewed-media-v1'
            or any(manifest.get(k) is not True for k in ('media_approved', 'image_approved', 'association_approved', 'topic_published'))):
        raise ValueError('Reviewed backend export and explicit human import approval required')
    expected = manifest.get('identity')
    if not isinstance(expected, dict) or set(expected) != set(identity({})) or not all(isinstance(v, str) and v for v in expected.values()):
        raise ValueError('Exact date/image/language/image-assignment/subject required')
    image = expected['filename']
    if Path(image).name != image or image in ('.', '..') or not (public_root / image).is_file():
        raise ValueError('Missing or unsafe image')
    entries = read_json(public_root / 'entries.json')['entries']
    if len([e for e in entries if identity(e) == expected and eligible(e)]) != 1:
        raise ValueError('No unique eligible image with exact identity')
    for key in ('media_assignment_id', 'archive_entry_id', 'topic_id', 'topic_revision', 'metadata_sha256'):
        if not manifest.get(key):
            raise ValueError('Missing backend approval provenance')
    if not re.fullmatch('[0-9a-f]{64}', str(manifest['metadata_sha256'])):
        raise ValueError('Invalid review fingerprint')
    raw = dict(manifest.get('media') or {})
    raw['companion_id'] = hashlib.sha256(json.dumps(dict(identity=expected, assignment=manifest['media_assignment_id']), sort_keys=True).encode()).hexdigest()
    media = normalize_media(raw, expected)
    if not media or (media['presentation_mode'] != 'link' and manifest.get('embed_approved') is not True):
        raise ValueError('Invalid or unapproved presentation contract')
    record = dict(identity=expected, approved=True, media=media, provenance=manifest)
    target = store / 'records' / f"{media['companion_id']}.json"
    if target.exists() and read_json(target) != record:
        raise ValueError('Existing companion differs; explicitly revoke/remove and re-review before replacement')
    atomic_json(target, record)
    return media


def attach_media(entries, store):
    records = {}
    for path in sorted((Path(store) / 'records').glob('*.json')):
        try:
            record = read_json(path)
            if record.get('approved') is True:
                records.setdefault(json.dumps(record['identity'], sort_keys=True), []).append(record)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    result = []
    for original in entries:
        entry = dict(original)
        entry.pop('companions', None)  # Inline producer metadata grants no approval.
        kinds = {}
        if eligible(entry):
            for record in records.get(json.dumps(identity(entry), sort_keys=True), []):
                media = normalize_media(record.get('media'), entry)
                provenance = record.get('provenance', {})
                if media and all(provenance.get(k) is True for k in ('media_approved', 'image_approved', 'association_approved', 'topic_published')) and (media['presentation_mode'] == 'link' or provenance.get('embed_approved') is True):
                    kinds.setdefault(media['artifact_kind'], []).append(media)
        companions = [values[0] for values in kinds.values() if len(values) == 1]  # Ambiguous lane fails closed.
        if companions:
            entry['companions'] = companions
        result.append(entry)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--public-root', required=True, type=Path)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--approve', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(import_media(read_json(args.manifest), args.public_root, args.store, approve=args.approve)))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Import rejected: {exc}\n')


if __name__ == '__main__':
    main()
