"""Verify generated UI plumbing without rebuilding real archive data."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',default='origin/main')
args=parser.parse_args()
for directory in ('docs','site'):
    for name in ('entries.json','latest.json'):
        before=subprocess.check_output(['git','show',f'{args.base}:{directory}/{name}'],cwd=ROOT)
        assert (ROOT/directory/name).read_bytes()==before, f'{directory}/{name}: content churn'
    for page in (ROOT/directory).glob('*.html'):
        text=page.read_text()
        assert text.count('id="companion-player"')==1
        assert text.count('src="companion-player.js"')==1
        assert 'fixture.webm' not in text and 'interactive-fixture' not in text
        for index,script in enumerate(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',text,re.S)):
            if not script.strip():continue
            with tempfile.TemporaryDirectory(prefix='archive-js-check-') as temp:
                path=Path(temp)/'inline.js';path.write_text(script)
                subprocess.run(['node','--check',str(path)],check=True,capture_output=True)
    for name in ('companion-player.css','companion-player.js'):
        assert (ROOT/directory/name).read_bytes()==(ROOT/'assets'/name).read_bytes()
for page in (ROOT/'docs').glob('*.html'):
    assert page.read_bytes()==(ROOT/'site'/page.name).read_bytes(),f'Mirror mismatch {page.name}'
changed=subprocess.check_output(['git','diff','--name-only',args.base],cwd=ROOT,text=True).splitlines()
assert not any(Path(name).suffix.lower() in ('.png','.jpg','.webm','.mp4','.m4a','.wav','.mp3') for name in changed),'Media content changed'
snapshot=json.loads((ROOT/'docs/entries.json').read_text())
latest=json.loads((ROOT/'docs/latest.json').read_text())
print(json.dumps({'entries_unchanged':len(snapshot['entries']),'html_pages':len(list((ROOT/'docs').glob('*.html'))),
                  'latest_unchanged':latest['image_filename'],'metadata_bytes':'unchanged','docs_site_html':'identical',
                  'all_inline_javascript':'node --check passed','production_media_changes':0}))
