#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${ARTISTS_ARCHIVE_REPO_ROOT:-/opt/artists-infographic-archive}"
export ARTISTS_ARCHIVE_BASE="${ARTISTS_ARCHIVE_BASE:-/opt/artists-bridge}"
export ARTISTS_ARCHIVE_RUNS_DIR="${ARTISTS_ARCHIVE_RUNS_DIR:-$ARTISTS_ARCHIVE_BASE/runs}"
export ARTISTS_ARCHIVE_PUBLIC_ROOT="${ARTISTS_ARCHIVE_PUBLIC_ROOT:-$REPO_ROOT/docs}"
export ARTISTS_ARCHIVE_LEGACY_IMPORTED="${ARTISTS_ARCHIVE_LEGACY_IMPORTED:-$ARTISTS_ARCHIVE_BASE/imported_legacy_entries.json}"

exec python3 "$REPO_ROOT/rebuild_gallery.py"
