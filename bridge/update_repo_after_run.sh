#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${ARTISTS_ARCHIVE_REPO_ROOT:-/opt/artists-infographic-archive}"
DOCS_DIR="${ARTISTS_ARCHIVE_PUBLIC_ROOT:-$REPO_ROOT/docs}"
SITE_DIR="$REPO_ROOT/site"
CANONICAL_REBUILD="$REPO_ROOT/rebuild_gallery.py"

export ARTISTS_ARCHIVE_BASE="${ARTISTS_ARCHIVE_BASE:-/opt/artists-bridge}"
export ARTISTS_ARCHIVE_RUNS_DIR="${ARTISTS_ARCHIVE_RUNS_DIR:-$ARTISTS_ARCHIVE_BASE/runs}"
export ARTISTS_ARCHIVE_PUBLIC_ROOT="$DOCS_DIR"
export ARTISTS_ARCHIVE_LEGACY_IMPORTED="${ARTISTS_ARCHIVE_LEGACY_IMPORTED:-$ARTISTS_ARCHIVE_BASE/imported_legacy_entries.json}"

cd "$REPO_ROOT"

prune_old_backups() {
  local backup_root="${ARTISTS_ARCHIVE_BACKUP_ROOT:-/opt/artists-bridge/backups}"
  local keep="${ARTISTS_BRIDGE_BACKUP_KEEP:-10}"
  if [ -d "$backup_root" ]; then
    find "$backup_root" -maxdepth 1 -type d \( -name 'update-before-reset-*' -o -name 'update-push-retry-*' \) -printf '%T@ %p\n' \
      | sort -rn \
      | tail -n +$((keep + 1)) \
      | cut -d' ' -f2- \
      | xargs -r rm -rf --
  fi
}

backup_assets() {
  local target="$1"
  mkdir -p "$target/docs" "$target/site"
  if [ -d "$DOCS_DIR" ]; then
    find "$DOCS_DIR" -maxdepth 1 -type f \( \
      -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.svg' \
    \) -exec cp -a {} "$target/docs/" \;
  fi
  if [ -d "$SITE_DIR" ]; then
    find "$SITE_DIR" -maxdepth 1 -type f \( \
      -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.svg' \
    \) -exec cp -a {} "$target/site/" \;
  fi
}

restore_assets() {
  local source="$1"
  mkdir -p "$DOCS_DIR" "$SITE_DIR"
  cp -a "$source/docs/." "$DOCS_DIR/" 2>/dev/null || true
  cp -a "$source/site/." "$SITE_DIR/" 2>/dev/null || true
}

verify_design_contract() {
  local index="$DOCS_DIR/index.html"
  local science="$DOCS_DIR/science-news.html"
  test -s "$index"
  test -s "$science"
  grep -Fq '<title>Visual Learning Archive' "$index"
  grep -Fq 'class="hero hero-desk"' "$index"
  grep -Fq 'class="collection-grid illustrated-collections"' "$index"
  grep -Fq 'class="info-popover"' "$index"
  grep -Fq 'href="science-news.html"' "$index"
  grep -Fq 'Science news explained' "$science"
  python3 - "$DOCS_DIR/entries.json" "$DOCS_DIR/latest.json" <<'PY'
import json
import sys
from pathlib import Path
entries = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
latest = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
items = entries.get('entries') or []
if not items:
    raise SystemExit('Refusing to publish an empty archive index')
if latest.get('image_filename') != items[0].get('filename'):
    raise SystemExit('latest.json does not match the newest entries.json item')
print(json.dumps({
    'design_contract': 'visual-learning-hub-v1',
    'entries': len(items),
    'latest': latest.get('person'),
    'latest_image': latest.get('image_filename'),
}, ensure_ascii=False))
PY
}

rebuild_and_verify() {
  test -s "$CANONICAL_REBUILD"
  python3 "$CANONICAL_REBUILD"
  verify_design_contract
  mkdir -p "$SITE_DIR"
  rsync -a --delete "$DOCS_DIR/" "$SITE_DIR/"
  diff -qr "$DOCS_DIR" "$SITE_DIR" >/dev/null
}

prune_old_backups
git config user.name 'Hermes Agent'
git config user.email 'hermes@example.com'

if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ]; then
  echo 'Refusing to publish: archive repo has a rebase/merge in progress' >&2
  git status --short --branch >&2 || true
  exit 2
fi

backup_root="${ARTISTS_ARCHIVE_BACKUP_ROOT:-/opt/artists-bridge/backups}"
backup_dir="$backup_root/update-before-reset-$(TZ=Europe/Ljubljana date +%Y%m%d%H%M%S)"
backup_assets "$backup_dir"

git fetch origin main
git reset --hard origin/main
restore_assets "$backup_dir"
rebuild_and_verify

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
  git add docs site
  git commit -m "Update artists archive for $(TZ=Europe/Ljubljana date +%F)"
else
  echo 'No repo changes to commit'
fi

if [ "$(git rev-list --count origin/main..HEAD)" -gt 0 ]; then
  if ! git push origin main; then
    echo 'Push rejected; refreshing from origin/main and rebuilding generated archive once' >&2
    git fetch origin main
    retry_backup="$backup_root/update-push-retry-$(TZ=Europe/Ljubljana date +%Y%m%d%H%M%S)"
    backup_assets "$retry_backup"
    git reset --hard origin/main
    restore_assets "$retry_backup"
    rebuild_and_verify
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
      git add docs site
      git commit -m "Update artists archive for $(TZ=Europe/Ljubljana date +%F)"
      git push origin main
    else
      echo 'No repo changes to push after retry rebuild'
    fi
  fi
else
  echo 'No local commits to push'
fi

prune_old_backups
