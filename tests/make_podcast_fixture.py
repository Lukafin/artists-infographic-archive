"""Build a LOCAL-ONLY browser fixture with generated sine-wave AAC, never publish it."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from podcasts import import_companion, attach_companions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Fresh scratch directory outside the repository')
    args = parser.parse_args()
    target = args.directory.resolve()
    if target == ROOT or ROOT in target.parents or target.exists():
        parser.error('Choose a fresh directory outside the repository; fixture must never be published')
    target.mkdir(parents=True)
    public = target / 'public'
    public.mkdir()
    snapshot = json.loads((ROOT / 'docs/entries.json').read_text())
    for name in ['index.html', 'page-2.html', 'science-news.html', 'podcast-player.js',
                 'podcast-player.css', 'entries.json', 'latest.json', 'favicon.svg', 'kofi_stroke_cup.svg']:
        shutil.copyfile(ROOT / 'docs' / name, public / name)
    for entry in snapshot['entries']:
        image = public / entry['filename']
        if not image.exists():
            image.symlink_to(ROOT / 'docs' / entry['filename'])
    # Older archive thumbnails provide representative UI; these sine waves are NOT companions.
    candidates = [entry for entry in snapshot['entries'][2:] if entry['person'] != 'Adelheid Popp'][:2]
    if len(candidates) < 2:
        parser.error('Need at least two archive entries for the smoke fixture')
    for i, entry in enumerate(candidates):
        audio = target / f'sine-fixture-{i}.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        f'sine=frequency={440 + 220 * i}:duration=12', '-c:a', 'aac', str(audio)], check=True)
        manifest = dict(entry, image_filename=entry['filename'], status='downloaded', verified=True,
                        image_approved=True, audio_approved=True, local_audio_path=str(audio))
        import_companion(manifest, public, target / 'private-store', approve=True)
    attached = attach_companions(snapshot['entries'], target / 'private-store', public)
    (public / 'entries.json').write_text(json.dumps(dict(snapshot, entries=attached), ensure_ascii=False))
    print(f'LOCAL TEST ONLY: {public}; never copy/publish these fixtures into docs/site')


if __name__ == '__main__':
    main()
