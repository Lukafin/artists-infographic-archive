# Artists Infographic Archive

Daily generated Slovenian artist/scientist birthday infographics for everyone.

Contents:
- `docs/` canonical GitHub-pushed static site (images + HTML + metadata)
- `site/` in-repo mirror backup of the generated static site
- `rebuild_gallery.py` canonical gallery builder used by both local and production workflows
- `bridge/rebuild_gallery.sh` production path adapter for the canonical generator
- `bridge/update_repo_after_run.sh` production publisher with a visual-design regression guard
- `sync_archive_to_repo.py` helper that mirrors docs/ into other repo files

## Optional companion podcasts

The archive does not generate audio. `podcasts.py` imports an **already downloaded,
verified, human-approved** companion into a private durable store. The canonical
builder attaches it to exactly one existing image, without adding an archive entry
or changing the latest selection. No production audio is bundled with this change.
The private Slovenian Adelheid Popp test is **not** an approved match for the English
image and must not be imported/published.

### Producer handoff (private manifest)

```json
{
  "date": "YYYY-MM-DD",
  "image_filename": "ExactPublishedImage.png",
  "person": "Exact published subject",
  "assignment_id": "Exact assignment ID (empty only for entries without one)",
  "language": "en",
  "status": "downloaded",
  "verified": true,
  "image_approved": true,
  "audio_approved": true,
  "local_audio_path": "/private/downloaded-companion.m4a"
}
```

`verified` means the producer/human has checked **spoken content, language and
subject**, not merely that a download finished. The importer cannot infer spoken
language from an audio container. Both image and audio must have passed human
review; `--approve` is the explicit publication authorization for this exact pair.
Pending/private/research-only images are ineligible. No name-only pairing, temporary
Google URL, private notebook URL, credentials, recipient or delivery state is used.
Extra manifest fields stay private and are not copied into public metadata.

```sh
python3 podcasts.py /private/companion.json \
  --public-root /opt/artists-infographic-archive/docs \
  --store /opt/artists-bridge/podcasts --approve
# Then use the normal canonical rebuild/mirror/publication flow.
ARTISTS_ARCHIVE_PODCAST_STORE=/opt/artists-bridge/podcasts \
  /opt/artists-infographic-archive/bridge/rebuild_gallery.sh
```

Local paths are configurable with `ARTISTS_ARCHIVE_BASE`, `ARTISTS_ARCHIVE_RUNS_DIR`,
`ARTISTS_ARCHIVE_LEGACY_IMPORTED`, `ARTISTS_ARCHIVE_PUBLIC_ROOT` and
`ARTISTS_ARCHIVE_PODCAST_STORE` (defaults to `$ARTISTS_ARCHIVE_BASE/podcasts`). Keep
the store outside `docs/` and `site/`, back it up, and retain it across production
resets. Import requires `ffprobe` and `ffmpeg`, checks nonempty supported audio,
container/extension agreement, positive measured duration, and complete decoding.
M4A/AAC remains `.m4a` with `audio/mp4`; there is no automatic transcoding.

Repeated import of identical content is a no-op; conflicting replacement is rejected
for explicit review. A later import uses the existing public index, then the next
rebuild reads the private record and attaches it to the original exact identity.
Raw `podcast` fields in run metadata are not publication authority: only approved
store records produce public audio. Unavailable/corrupt/revoked audio falls back to
image-only entries. Rebuild removes orphaned public audio.

### Hosting and public metadata

Approved audio is content-addressed at `docs/audio/<sha256>.<extension>` and mirrored
to `site/audio/`. This chooses stable same-origin Pages hosting over external hosts
or expiring download URLs. The cost is repository growth and duplicate mirror
storage; import is capped at **50 MiB per episode**. Reassess external object storage
before a large backfill; do not backfill automatically.

Only `url`, `title`, `language`, `mime_type`, `duration_seconds`, `source` (NotebookLM)
and opaque `companion_id` are public. `entries.json` and applicable `latest.json`
contain this optional object; missing audio is a normal image-only entry. Identity
is exact date + image filename + language + assignment (when present) + subject.
Run metadata and private companion manifests remain outside the public tree.

### Listening

The selected **persistent bottom mini-player** appears only after Listen / Poslušaj
activation. Selection does not autoplay: press the native play control to start.
One native `audio controls preload="none"` element provides play/pause, seeking and
time. Selecting another episode stops/replaces the old one; selecting the same one
preserves its position. Dismiss stops playback, releases the source and returns
focus. The thumbnail, title and actual spoken language stay visible independently
of UI language. Responsive padding includes the mobile safe area.

Search, filters, People/School collection changes, pagination and browser back/forward
within the archive keep the same player. Pagination fetches/replaces only archive
content (the surrounding page chrome stays in place); failures show a retry message
instead of navigating away. While selected, opening an infographic uses a new tab.
**Separate HTML documents** (such as the Science news page), reloads and leaving the
site stop playback; the player states this limitation. There is no background
cross-document playback or saved autoplay session.

### Verification

```sh
python3 -m unittest discover -s tests -v
node --check assets/podcast-player.js
git diff --check
```

Optional real Chromium smoke test (Node with built-in WebSocket, Chromium, ffmpeg):

```sh
# Choose a fresh path under your scratch directory, never under docs/site.
python3 tests/make_podcast_fixture.py "$TMPDIR/podcast-browser-fixture"
python3 -m http.server 8764 --bind 127.0.0.1 \
  --directory "$TMPDIR/podcast-browser-fixture/public"
# In another terminal; stop the local HTTP server afterward.
node tests/browser_podcasts.mjs http://127.0.0.1:8764/index.html "$TMPDIR"
```

The smoke test runs one headless Chromium process, checks zero initial/selection
audio requests, native playback/seek, same-element pagination/back, actual language
after UI switching, episode replacement, dismiss/focus, responsive padding and
desktop/mobile screenshots. The fixture is local-only generated sine audio and
must never be copied into the production site. Python's basic HTTP server is not
a certification of production byte-range support.

Tests generate disposable sine-wave AAC fixtures, never real/private episodes.
After an authorized production deployment, verify the exact public `entries.json`
and `latest.json`, docs/site equality, HTTP 200 and `Content-Type: audio/mp4`, a
`Range: bytes=0-1023` request returning HTTP 206 with `Content-Range`, and actual
desktop/mobile play/seek/dismiss. Local fixture tests cannot certify GitHub Pages
reachability/range behavior. Live acceptance awaits an approved language-matched
production episode and deployment; do not substitute the private Adelheid test.
