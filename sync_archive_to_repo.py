#!/usr/bin/env python3
import shutil
from pathlib import Path

ARTISTS_BASE = Path('/home/lukafinzgar/projects/.caller_tasks/artists')
REPO_ROOT = Path('/home/lukafinzgar/projects/.caller_tasks/artists-infographic-archive')
DOCS_DIR = REPO_ROOT / 'docs'
SITE_DIR = REPO_ROOT / 'site'
GITHUB_REPO_URL = 'https://github.com/Lukafin/artists-infographic-archive'

DOCS_DIR.mkdir(parents=True, exist_ok=True)
SITE_DIR.mkdir(parents=True, exist_ok=True)

# Mirror docs/ into site/ as an in-repo backup; no files are copied via the old RPi public root anymore.
for path in DOCS_DIR.iterdir():
    if path.is_file():
        shutil.copy2(path, SITE_DIR / path.name)

# Copy generator/support files worth preserving
for name in ['rebuild_gallery.py', 'sync_archive_to_repo.py', 'gallery_index.py']:
    src = ARTISTS_BASE / name
    if src.exists():
        shutil.copy2(src, REPO_ROOT / name)

readme = REPO_ROOT / 'README.md'
readme.write_text(
    '# Artists Infographic Archive\n\n'
    'Daily generated Slovenian artist/scientist birthday infographics for everyone.\n\n'
    'Contents:\n'
    '- `docs/` canonical GitHub-pushed static site (images + HTML + metadata)\n'
    '- `site/` in-repo mirror backup of the generated static site\n'
    '- `rebuild_gallery.py` gallery builder used by the local workflow\n'
    '- `sync_archive_to_repo.py` helper that mirrors docs/ into other repo files\n',
    encoding='utf-8'
)

(REPO_ROOT / 'SITE_URL.txt').write_text(
    f'GitHub repo: {GITHUB_REPO_URL}\n'
    f'GitHub docs folder: {GITHUB_REPO_URL}/tree/main/docs\n',
    encoding='utf-8'
)

print(f'Synced GitHub archive artifacts inside {REPO_ROOT}')
