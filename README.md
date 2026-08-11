# Artists Infographic Archive

Daily generated Slovenian artist/scientist birthday infographics for everyone.

Contents:
- `docs/` canonical GitHub-pushed static site (images + HTML + metadata)
- `site/` in-repo mirror backup of the generated static site
- `rebuild_gallery.py` canonical gallery builder used by both local and production workflows
- `bridge/rebuild_gallery.sh` production path adapter for the canonical generator
- `bridge/update_repo_after_run.sh` production publisher with a visual-design regression guard
- `sync_archive_to_repo.py` helper that mirrors docs/ into other repo files
