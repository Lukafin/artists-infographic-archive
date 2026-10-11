"""Apply only companion UI plumbing to current generated pages, no rebuild/content changes."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
PANEL = '''<section id="companion-player" class="companion-player" role="region" aria-label="Reviewed explanation" hidden>
    <header><h2></h2><button type="button" class="companion-fullscreen">Fullscreen</button><button type="button" class="companion-dismiss" aria-label="Close and stop">×</button></header>
    <div class="companion-stage"></div><p role="status"></p>
    <a class="companion-fallback" target="_blank" rel="noopener noreferrer">Open external link</a>
  </section>
  <script src="companion-player.js"></script>
'''
DYNAMIC = '''${entry.companions?.length ? `<div class="companion-actions">${entry.companions.map(media => `<button type="button" class="companion-action" data-companion="${escapeHtml(JSON.stringify(media))}">${media.artifact_kind === 'video' ? 'Watch' : 'Explore'}</button>`).join('')}</div>` : ''}'''


def update_html(value):
    if 'companion-player.css' not in value:
        value = value.replace('</head>', '<link rel="stylesheet" href="companion-player.css">\n</head>')
    if 'id="companion-player"' not in value:
        value = value.replace('</body>', PANEL + '</body>')
    if DYNAMIC not in value:
        lines = value.splitlines(keepends=True)
        value = ''.join(line + ('      ' + DYNAMIC + '\n' if '${entry.podcast ?' in line else '') for line in lines)
    return value


if __name__ == '__main__':
    for directory in ('docs', 'site'):
        for path in (ROOT / directory).glob('*.html'):
            value = path.read_text()
            path.write_text(update_html(value))
        for name in ('companion-player.css', 'companion-player.js'):
            shutil.copyfile(ROOT / 'assets' / name, ROOT / directory / name)
