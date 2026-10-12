"""Consume ACTUAL locally exported backend test records; never fetch or publish media."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from companions import attach_media

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('exports',type=Path)
parser.add_argument('scratch',type=Path)
args=parser.parse_args()
target=args.scratch.resolve()
if target.exists() or target==ROOT or ROOT in target.parents:
    parser.error('Fresh scratch outside repository required')
public=target/'public';public.mkdir(parents=True)
records=[json.loads(path.read_text()) for path in sorted(args.exports.glob('*.json'))]
assert len(records)==2, 'Need actual video and interactive backend fixture exports'
entries=[record['identity'] for record in records]
(public/'entries.json').write_text(json.dumps({'entries':entries}))
for entry in entries:
    # Local admission fixture only, no image production or external URL request.
    (public/entry['filename']).write_bytes(b'LOCAL ADMISSION TEST ONLY')
for record in records:
    manifest=target/f"{record['media']['artifact_kind']}.json"
    manifest.write_text(json.dumps(record))
    subprocess.run([sys.executable,str(ROOT/'companions.py'),str(manifest),'--public-root',str(public),
                    '--store',str(target/'private-store'),'--approve'],check=True)
attached=attach_media(entries,target/'private-store')
assert len(attached)==2 and all(len(e['companions'])==1 for e in attached)
for record,entry in zip(records,attached):
    assert entry['companions'][0]['url']==record['media']['url']
    assert entry['companions'][0]['presentation_mode']==record['media']['presentation_mode']
    assert 'metadata_sha256' not in entry['companions'][0]
assert len(list(public.iterdir()))==3, 'Offline importer does not publish media/UI or fetch URLs'
print(json.dumps({'actual_backend_exports_imported':len(records),'exact_identities':entries,'network_fetches':0,'publication':False}))
