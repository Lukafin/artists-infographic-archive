# Elektrika Anatomy v1 — review candidate

Prepared static path: `interactive/elektrika/v1/index.html`, identical in `docs`
and `site`. Candidate HTML SHA-256:
`c640e1795cdb8a96e1995c74e0ae0e12a0cae029dd3a918fa7618edd9e438200`. Local preview: `python3 preview_server.py --port 8769`, then open
`http://127.0.0.1:8769/interactive/elektrika/v1/index.html`.

This is a review candidate. Creating this page does not approve an archive
companion, publish a topic, or certify an external-media review. The original
`Elektrika.png` and its archive record are untouched (18 June 2026, Slovenian,
assignment `256deb5c-62e8-4d2d-b6c9-c9f11bdd9ca5`).

## Rebuild and verify

```sh
node interactive-src/elektrika/build.mjs --audit
node --test tests/test_elektrika.mjs
```

The Figure uses the actual Anatomy SVG toolkit and audit from upstream commit
`e6600ffc4e8e6620eeb45bf49bcdbd5e4b84163f` (MIT, Ryan). Only required toolkit
modules are vendored; the complete license is embedded in the standalone page.
The pure DC model drives the readouts, dial needles, switch symbol and current
markers. All 57 solids are recorded exactly and sorted by `A.settle`.
Current dots are clipped to their copper bars and share the bars' proven depth
order, so they cannot appear through an enclosure.

The printed circuit glyphs are a DC voltage source with +/−, an SPST switch that
follows open/closed state, an IEC rectangular resistor and an A inside a circle
for the series ammeter. The model remains ideal and is explicitly described on
the page: no heating-dependent resistance, real electron speed or transients.
The source range is 0–12 V and the resistance range 4–24 Ω.

Validation performed with the upstream Anatomy `capture.mjs`, `drive.mjs` and
`lines.mjs`: desktop and 390 px mobile; light/dark themes; reduced motion;
keyboard slider interaction; voltage/resistance comparisons; open/closed switch;
4× junction close-ups and motion contact sheet. Geometry audit and both themes'
line-end checks passed, with clean browser console and no sideways overflow.
These are contributor checks, not a separate human review.

## Roj admission and publishing

A newly qualified and verified external swarm member proposed Elektrika revision
1, topic ID `751f9498-3d36-4fa6-85a9-64baa67f2c39`. Registration succeeded and
`interactive_site` capability was explicitly opted in. Credentials and
qualification files remain private under `~/.roj/`; none belongs in this repo.

The proposal is still **draft**, and the live backlog has no Elektrika interactive
assignment. Before an actual CLI claim/submission, a human administrator must
approve the exact brief and associate an interactive backlog item. The existing
image can then be adopted through the reviewed-image workflow.

After a functional versioned page has been approved for hosting, use the
manifest/protocol-declared interactive lane with Roj CLI to claim the exact task
and submit its actual external URL and functionality/accessibility/security
proof. The URL-only backend does not host the HTML. Output review and explicit
embed approval, topic association, page publication, protected archive export,
private durable import and a normal canonical rebuild remain separate gates.
Follow `REVIEWED_MEDIA.md`. Do not hand-edit generated archive entries or infer
Explore admission from this static-page PR.
