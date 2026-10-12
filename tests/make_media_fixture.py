"""Generate disposable real video + interactive controls; NEVER publish this directory."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companions import import_media, attach_media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    target = args.directory.resolve()
    subprocess.run([sys.executable, str(ROOT/'tests/make_podcast_fixture.py'), str(target)], check=True)
    public = target/'public'
    for name in ('companion-player.js','companion-player.css'):
        shutil.copyfile(ROOT/'assets'/name, public/name)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=12',
                    '-c:v','libvpx','-b:v','180k','-an',str(public/'fixture.webm')],check=True)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=12',
                    '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(public/'fixture.mp4')],check=True)
    (public/'interactive-fixture.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Local sandbox fixture</title>
<style>body{font:20px system-ui;margin:20px}button{padding:12px}input{display:block;margin:20px 0}</style>
<button id="increment">Change mechanism</button><input aria-label="Energy" type="range" min="0" max="100" value="20"><output id="count">0</output>
<script>let isolated=false;try{parent.document.body.dataset.unsafe='yes'}catch(e){isolated=true}let count=0;
function report(){parent.postMessage({fixture:true,isolated,count,energy:document.querySelector('input').value},'*')}
document.querySelector('button').onclick=()=>{document.querySelector('output').textContent=++count;report()};document.querySelector('input').oninput=report;report();</script></html>''')
    snapshot = json.loads((public/'entries.json').read_text())
    episodes = [e for e in snapshot['entries'] if e.get('podcast')]
    for i, entry in enumerate(episodes):
        for kind in (('video','interactive_site') if i == 0 else ('video',)):
            mode = 'native_video' if kind == 'video' else 'sandboxed_iframe'
            video_name = 'fixture.webm' if i == 0 else 'fixture.mp4'
            media = dict(title='LOCAL TEST ONLY '+entry['person'], url=f'http://127.0.0.1:{args.port}/'+(video_name if kind=='video' else 'interactive-fixture.html'),
                         artifact_kind=kind, language=entry['language'], presentation_mode=mode)
            if kind == 'video': media['mime_type']='video/webm' if i == 0 else 'video/mp4'
            manifest=dict(schema='artists-reviewed-media-v1',identity={k:str(entry.get(k) or '') for k in ('date','filename','language','assignment_id','person')},
                media=media, media_approved=True,image_approved=True,association_approved=True,topic_published=True,embed_approved=True,
                media_assignment_id=f'LOCAL-TEST-{kind}-{i}',archive_entry_id='LOCAL-TEST',topic_id='LOCAL-TEST',topic_revision=1,metadata_sha256='a'*64)
            # Existing historical images can lack an assignment; choose modern fixture entries only.
            import_media(manifest,public,target/'media-store',approve=True)
    attached=attach_media(snapshot['entries'],target/'media-store')
    (public/'entries.json').write_text(json.dumps(dict(snapshot,entries=attached),ensure_ascii=False))
    print(f'LOCAL TEST ONLY: {public}')


if __name__=='__main__': main()
