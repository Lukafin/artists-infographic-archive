#!/usr/bin/env python3
import shutil
from pathlib import Path

PUBLIC_ROOT = Path('/home/lukafinzgar/projects/.caller_tasks/_public/artists')
ARTISTS_BASE = Path('/home/lukafinzgar/projects/.caller_tasks/artists')
REPO_ROOT = Path('/home/lukafinzgar/projects/.caller_tasks/artists-infographic-archive')
SITE_DIR = REPO_ROOT / 'site'

SITE_DIR.mkdir(parents=True, exist_ok=True)

# Copy public site artifacts
for path in PUBLIC_ROOT.iterdir():
    if path.is_file():
        shutil.copy2(path, SITE_DIR / path.name)

# Copy generator/support files worth preserving
for name in ['rebuild_gallery.py', 'sync_archive_to_repo.py']:
    src = ARTISTS_BASE / name
    if src.exists():
        shutil.copy2(src, REPO_ROOT / name)

readme = REPO_ROOT / 'README.md'
if not readme.exists():
    readme.write_text(
        '# Artists Infographic Archive\n\n'
        'Daily generated Slovenian kid-friendly artist/scientist birthday infographics.\n\n'
        'Contents:\n'
        '- `site/` public static archive (images + HTML + metadata)\n'
        '- `rebuild_gallery.py` gallery builder used by the local workflow\n'
        '- `sync_archive_to_repo.py` sync helper that copies the latest public artifacts into this repo\n',
        encoding='utf-8'
    )

# Small landing page note for GitHub viewers if site/index.html exists
index_src = SITE_DIR / 'index.html'
if index_src.exists():
    (REPO_ROOT / 'SITE_URL.txt').write_text(
        'Public site: https://raspberrypi.tail7e067c.ts.net/artists/\n',
        encoding='utf-8'
    )

print(f'Synced public archive into {REPO_ROOT}')
