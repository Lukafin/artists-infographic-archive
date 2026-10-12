# Reviewed in-page video and interactive companions

Watch / Explore open a persistent in-page panel, outside the replaceable archive grid. Search, filters and same-document pagination retain the active video or interactive document. Separate HTML-document navigation/reload stops playback. Listen remains the existing persistent podcast player. Starting one media player pauses/releases the other; closing the companion panel stops/releases video and unloads the iframe, with focus returned to its trigger when still present.

## Admission and durable offline handoff

Backend companion PR58 supplies **URLs, not uploads or fetched content**. The submission defaults to `presentation_mode: "link"`: existing webpage URLs are never inferred to be video files or automatically embedded.

- Video: request `presentation_mode: "native_video"`, a direct credential-free HTTP(S) `.mp4` / `.webm` URL and matching `mime_type: "video/mp4"` / `"video/webm"`. Native controls, `playsinline`, `preload="none"`; Watch selects the video without autoplay or loading it. Native Play starts transfer.
- Interactive: request `presentation_mode: "sandboxed_iframe"` with a credential-free HTTP(S) URL. Explore deliberately activates/loading the iframe, with **`sandbox="allow-scripts"` only** and `referrerpolicy="no-referrer"`. No same-origin, popup, navigation, download, camera, microphone, geolocation or parent-DOM privilege is granted. Some interactive sites require permissions/storage unavailable here; those sites are not eligible for embedded approval without changes to the site itself.
- Human media approval must separately include `embed_approved: true` for either non-link mode. The review covers the exact URL/mode/MIME, rights, factual content, keyboard/accessibility, framing policy and restrictive-sandbox compatibility. Contributor self-reports alone do not grant approval.
- Topic association review and topic-page publication are additional gates, not consequences of media approval. The exporter requires current approved **image and media** associations in the same published topic revision.

An authenticated operator calls backend
`POST /api/v1/admin/topics/{topic_id}/archive-media-export/{video|interactive}`
with the exact image identity copied from the current archive's `entries.json`:

```json
{"date":"YYYY-MM-DD","filename":"EXACT.png","language":"en","assignment_id":"EXACT-IMAGE-ASSIGNMENT-ID","person":"EXACT SUBJECT"}
```

The backend verifies image filename, language, assignment and subject against its reviewed image association. It cannot know the archive's date; the archive importer checks **all five strings exactly**, including date, against one eligible published image and verifies that image exists. No title/fuzzy-name matching or fallback association is allowed; entries without an image assignment cannot use this handoff. This is deliberate, not an excuse to invent an assignment.

Save the protected JSON response outside the repository/public trees, then explicitly review/import it:

```sh
python3 companions.py /private/export.json \
  --public-root /path/to/current/archive/docs \
  --store /private/durable/reviewed-media --approve
```

This writes only a private durable record, never public assets/JSON or network requests. It requires schema `artists-reviewed-media-v1`, explicit image/media/association/page approval, backend assignment/entry/topic/revision/fingerprint provenance, and an explicit embed gate for non-link modes. **The JSON is not cryptographically signed:** it is a trusted protected-backend export handled by an authorized human, not an arbitrary contributor upload. Do not accept records from an untrusted source.

Configure `ARTISTS_ARCHIVE_MEDIA_STORE` for the canonical rebuild. Default: `$ARTISTS_ARCHIVE_BASE/reviewed-media`, outside docs/site and the repo reset scope when using the tracked production wrappers. A normal authorized rebuild attaches only exact matches and emits a narrow public `companions` projection. It does not serialize private review notes, assignment provenance or metadata hashes. Conflicting replacement requires explicit private revocation/removal and fresh review; multiple records for one image/lane fail closed. Inline producer `companions` grants no admission.

Do not run a production rebuild just to trial imports; use scratch fixtures. The existing tracked bridge wrappers invoke the canonical builder and mirror docs to site; no live wrappers/server/cron have been changed here.

## Hosting and revocation boundaries

The backend continues storing URLs only; it does not fetch, execute, upload or host video/sites. Backend topic HTML remains intentionally link-only with its restrictive CSP unchanged; the **archive** is the in-page presentation consumer. The public topic JSON includes a narrow approved presentation mode/MIME for a separately authorized consumer.

For external hosting, the origin must serve the correct playable video MIME/container and permit framing (CSP `frame-ancestors`, X-Frame-Options). HTTPS pages need HTTPS media to avoid mixed-content blocking. Arbitrary sites cannot be guaranteed to embed. The panel always offers an explicit optional outgoing fallback; browsers cannot reliably distinguish a blocked cross-origin iframe from every other load failure. Never claim that an iframe's load event proves functionality.

A reviewed static interactive can be hosted by a separate human-reviewed archive PR at `interactive/<id>/<version>/index.html`, then supply its final HTTPS Pages URL to the same backend contract. **This PR intentionally provides no automatic bundle importer, dependency runner, or hosting platform**: URL-only remote/static hosting is sufficient for the requested in-page consumption. No arbitrary package execution, fixture assets, or executable bundles are committed to docs/site. Static-bundle ingestion, if later requested, must separately reject traversal, symlinks, oversized bundles and unreviewed executables; sandbox restrictions must not be relaxed to make a bundle work.

External contents can change after review. Offline records are snapshots, not a live revocation subscription. Before any real publication, re-export/recheck current backend gates and human approval; revoke a stored companion by setting its private record `approved` to false (or remove it), then rebuild/mirror through the normal authorized publication flow. The next rebuild omits its button/public URL, but cannot revoke the external origin or cached pages. No production import/publication was performed for this implementation.

## Verification

```sh
python3 -m unittest discover -s tests -v
node --check assets/companion-player.js
python3 tests/make_media_fixture.py /fresh/private/scratch --port 8765
python3 -m http.server 8765 --bind 127.0.0.1 --directory /fresh/private/scratch/public
node tests/browser_media.mjs http://127.0.0.1:8765/index.html /fresh/private/scratch
node tests/browser_podcasts.mjs http://127.0.0.1:8765/index.html /fresh/private/scratch
```

The fixture generates actual VP8/WebM and H.264/MP4 video and AAC sine audio via ffmpeg; interactive controls are disposable local HTML. It never belongs in repository docs/site. Browser checks cover both real video containers' decode/playback/seek, fullscreen, native conservative loading, desktop1440/mobile390 overflow, interactive button and keyboard slider, parent-DOM isolation, restrictive permissions, releases/focus, audio exclusion, language, filters and pagination, and accessible failed-video fallback. Podcast regression covers native playback/seek, no initial loading, language, filtering, pagination/back and replacement/dismiss. Actual iOS/Safari and production-origin MIME/range/framing policies remain deployment acceptance checks.

For an actual local backend-export → archive-import check, run backend `tests/test_external_media_export.py` with `ARTISTS_TEST_EXPORT_DIR` pointing to private scratch, then:

```sh
python3 tests/verify_backend_handoff.py /private/backend-exports /fresh/private/admission-test
```

This consumes real TestClient endpoint results, not invented API responses; it still fetches/publishes no media. The generator's isolated rebuild test confirms durable records survive regeneration and title escaping.

Browser/security reference: MDN's [iframe element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe) and [video element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video). `preload` is a browser hint, not a universal network guarantee; zero pre-activation media requests were additionally measured in the tested Chromium.
