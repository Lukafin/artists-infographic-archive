"""Approved companion handoff. Private producer manifests never become public JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

AUDIO_TYPES = {'.m4a': 'audio/mp4', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wav': 'audio/wav'}
PUBLIC_FIELDS = ('url', 'title', 'language', 'mime_type', 'duration_seconds', 'source', 'companion_id')


def identity(entry):
    return {key: str(entry.get(key) or '') for key in ('date', 'filename', 'language', 'assignment_id', 'person')}


def eligible(entry):
    return (entry.get('image_approved') is not False and entry.get('private') is not True
            and entry.get('status') not in ('private', 'pending', 'pending_review', 'rejected', 'research_only'))


def normalize_podcast(value, entry):
    """Only stable local content-addressed assets and fixed public provenance are accepted."""
    if not isinstance(value, dict):
        return None
    url = value.get('url')
    if not isinstance(url, str):
        return None
    match = re.fullmatch(r'audio/([0-9a-f]{64})(\.m4a|\.mp3|\.ogg|\.wav)', url or '')
    duration = value.get('duration_seconds')
    if (not match or value.get('mime_type') != AUDIO_TYPES[match.group(2)]
            or value.get('language') != entry.get('language')
            or value.get('source') != 'NotebookLM'
            or not re.fullmatch(r'[0-9a-f]{64}', str(value.get('companion_id', '')))
            or not isinstance(value.get('title'), str) or not value['title'].strip()
            or not isinstance(duration, (float, int)) or isinstance(duration, bool)
            or not math.isfinite(duration) or duration <= 0):
        return None
    return {key: value[key] for key in PUBLIC_FIELDS}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def import_companion(manifest, public_root, store, *, approve=False):
    """Validate and retain downloaded audio in a private durable store; never publish directly."""
    public_root, store = Path(public_root), Path(store)
    if not isinstance(manifest, dict):
        raise ValueError('Companion manifest must be an object')
    public, private = public_root.resolve(), store.resolve()
    mirror = public.parent / 'site'
    if public == private or public in private.parents or mirror == private or mirror in private.parents:
        raise ValueError('Podcast store must be outside public docs/site')
    if (not approve or manifest.get('image_approved') is not True
            or manifest.get('audio_approved') is not True or manifest.get('verified') is not True
            or manifest.get('status') != 'downloaded'):
        raise ValueError('Explicit human image/audio approval and verified downloaded status required')
    image = manifest.get('image_filename', '')
    if not isinstance(image, str) or Path(image).name != image or image in ('', '.', '..'):
        raise ValueError('Invalid exact public image filename')
    expected = identity(dict(manifest, filename=image))
    if not all(expected[key] for key in ('date', 'filename', 'language', 'person')):
        raise ValueError('Exact date/image/language/subject required')
    entries = read_json(public_root / 'entries.json')['entries']
    matches = [entry for entry in entries if identity(entry) == expected and eligible(entry)]
    if len(matches) != 1 or not (public_root / image).is_file():
        raise ValueError('No unique approved published image with exact date/image/language/assignment/subject')
    entry = matches[0]
    audio = Path(manifest.get('local_audio_path') or '')
    extension = audio.suffix.lower()
    if extension not in AUDIO_TYPES or not audio.is_file() or audio.stat().st_size == 0:
        raise ValueError('Missing, empty or unsupported downloaded audio')
    if audio.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('Audio exceeds the 50 MiB static hosting limit')
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                 '-of', 'json', str(audio)], capture_output=True, text=True, check=True, timeout=120)
        probe = json.loads(result.stdout)
        duration = float(probe['format']['duration'])
        streams = [stream for stream in probe['streams'] if stream.get('codec_type') == 'audio']
        formats = set(probe['format']['format_name'].split(','))
        expected_formats = {'.m4a': {'mov', 'mp4', 'm4a'}, '.mp3': {'mp3'}, '.ogg': {'ogg'}, '.wav': {'wav'}}
        if not streams or not math.isfinite(duration) or duration <= 0 or not formats & expected_formats[extension]:
            raise ValueError('Audio container does not match extension or has no audio')
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(audio), '-map', '0:a:0',
                        '-f', 'null', '-'], capture_output=True, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Audio probe/decode failed (ffprobe and ffmpeg required)') from exc
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    companion_id = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    podcast = dict(url=f'audio/{digest}{extension}', title=entry['person'], language=entry['language'],
                   mime_type=AUDIO_TYPES[extension], duration_seconds=round(duration, 3),
                   source='NotebookLM', companion_id=companion_id)
    record_path = store / 'records' / f'{companion_id}.json'
    if record_path.exists():
        previous = read_json(record_path)
        if previous != dict(identity=expected, approved=True, podcast=podcast):
            raise ValueError('Companion already imported with different content; review/remove private record explicitly')
    target = store / str(podcast['url'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        pending = target.with_suffix(target.suffix + '.pending')
        shutil.copyfile(audio, pending)
        # Detect input changes during verification/copy.
        if hashlib.sha256(pending.read_bytes()).hexdigest() != digest:
            pending.unlink()
            raise ValueError('Audio changed during import')
        pending.replace(target)
    atomic_json(record_path, dict(identity=expected, approved=True, podcast=podcast))
    return podcast


def attach_companions(entries, store, public_root):
    """Fail closed for audio only; rebuild image-only entries even if audio is absent/bad."""
    store, public_root = Path(store), Path(public_root)
    records = {}
    for path in sorted((store / 'records').glob('*.json')):
        try:
            record = read_json(path)
            if not isinstance(record, dict):
                continue
            if record.get('approved') is True:
                records[json.dumps(record['identity'], sort_keys=True)] = record
        except (OSError, ValueError, KeyError, TypeError):
            continue
    result = []
    for original in entries:
        entry = dict(original)
        # Inline producer metadata is not an approval/publication capability.
        entry.pop('podcast', None)
        record = records.get(json.dumps(identity(entry), sort_keys=True))
        podcast = normalize_podcast(record.get('podcast'), entry) if record and eligible(entry) else None
        if podcast:
            asset = store / podcast['url']
            try:
                digest = Path(podcast['url']).stem
                if asset.is_file() and asset.stat().st_size and hashlib.sha256(asset.read_bytes()).hexdigest() == digest:
                    target = public_root / podcast['url']
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(asset, target)
                    entry['podcast'] = podcast
            except OSError:
                pass
        result.append(entry)
    # Remove orphaned audio so a revoked/private companion cannot remain reachable.
    keep = {entry['podcast']['url'] for entry in result if entry.get('podcast')}
    for path in (public_root / 'audio').glob('*'):
        if path.is_file() and f'audio/{path.name}' not in keep:
            path.unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--public-root', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True, help='Private durable path outside docs/site')
    parser.add_argument('--approve', action='store_true', help='Human reviewed this exact image/audio/language pair')
    args = parser.parse_args()
    public = args.public_root.resolve()
    store = args.store.resolve()
    if public == store or public in store.parents or store == public.parent / 'site' or public.parent / 'site' in store.parents:
        parser.error('Podcast store must be outside public docs/site')
    try:
        podcast = import_companion(read_json(args.manifest), public, store, approve=args.approve)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Import rejected: {exc}\n')
    print(json.dumps(podcast, ensure_ascii=False))


if __name__ == '__main__':
    main()
