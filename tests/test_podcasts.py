import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from podcasts import import_companion, attach_companions, normalize_podcast


class PodcastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='podcast-test-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.public = self.tmp / 'docs'
        self.public.mkdir()
        self.store = self.tmp / 'private-podcasts'
        self.entry = dict(date='2026-10-02', filename='Topic.png', person='Topic',
                          language='en', assignment_id='assignment-1', category='scientist')
        (self.public / 'Topic.png').write_bytes(b'image fixture')
        (self.public / 'entries.json').write_text(json.dumps({'entries': [self.entry]}))
        self.audio = self.tmp / 'private.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=1', '-c:a', 'aac', str(self.audio)], check=True)
        self.manifest = dict(self.entry, image_filename='Topic.png', status='downloaded',
                             verified=True, image_approved=True, audio_approved=True,
                             local_audio_path=str(self.audio), notebook_url='PRIVATE', recipient='PRIVATE')

    def do_import(self, manifest=None, approve=True):
        return import_companion(manifest or self.manifest, self.public, self.store, approve=approve)

    def test_legacy_and_untrusted_metadata(self):
        self.assertIsNone(normalize_podcast({'url': 'https://google.com/private', 'local_path': '/private'}, self.entry))
        self.assertEqual(attach_companions([self.entry], self.store, self.public), [self.entry])

    def test_import_whitelist_idempotence_and_late_rebuild(self):
        first = self.do_import()
        self.assertEqual(first, self.do_import())
        self.assertEqual(len(list((self.store / 'records').glob('*.json'))), 1)
        attached = attach_companions([self.entry], self.store, self.public)
        podcast = attached[0]['podcast']
        self.assertEqual(podcast['language'], 'en')
        self.assertEqual(podcast['mime_type'], 'audio/mp4')
        self.assertNotIn('PRIVATE', json.dumps(podcast))
        self.assertNotIn(str(self.tmp), json.dumps(podcast))
        self.assertEqual(attach_companions([self.entry], self.store, self.public), attached)
        self.assertTrue((self.public / podcast['url']).is_file())
        # Canonical rebuild consumes original metadata, not previous output.
        runs = self.tmp / 'runs' / 'one'
        runs.mkdir(parents=True)
        (runs / 'entry.json').write_text(json.dumps(self.entry))
        env = dict(os.environ, ARTISTS_ARCHIVE_BASE=str(self.tmp),
                   ARTISTS_ARCHIVE_REPO_ROOT=str(ROOT),
                   ARTISTS_ARCHIVE_RUNS_DIR=str(runs.parent), ARTISTS_ARCHIVE_PUBLIC_ROOT=str(self.public),
                   ARTISTS_ARCHIVE_PODCAST_STORE=str(self.store),
                   ARTISTS_ARCHIVE_LEGACY_IMPORTED=str(self.tmp / 'missing.json'))
        for _ in range(2):
            subprocess.run(['bash', str(ROOT / 'bridge/rebuild_gallery.sh')], env=env, check=True, capture_output=True)
            index = json.loads((self.public / 'entries.json').read_text())
            latest = json.loads((self.public / 'latest.json').read_text())
            self.assertEqual(len(index['entries']), 1)
            self.assertEqual(index['entries'][0]['podcast'], podcast)
            self.assertEqual(latest['podcast'], podcast)
            page = (self.public / 'index.html').read_text()
            self.assertIn('data-podcast-listen=', page)
            self.assertIn('preload="none"', page)
            self.assertIn('class="hero hero-desk"', page)
            self.assertIn('class="collection-grid illustrated-collections"', page)
            self.assertIn('class="info-popover"', page)
            self.assertIn('Science news explained', (self.public / 'science-news.html').read_text())
            self.assertEqual(latest['image_filename'], index['entries'][0]['filename'])
            mirror = self.tmp / 'mirror'
            shutil.copytree(self.public, mirror, dirs_exist_ok=True)
            self.assertEqual({p.relative_to(self.public): p.read_bytes() for p in self.public.rglob('*') if p.is_file()},
                             {p.relative_to(mirror): p.read_bytes() for p in mirror.rglob('*') if p.is_file()})

    def test_identity_and_approval_rejections(self):
        for field, value in [('language', 'sl'), ('date', '2026-10-01'),
                             ('image_filename', 'Other.png'), ('assignment_id', 'other'),
                             ('person', 'Other'), ('status', 'pending'), ('verified', False),
                             ('image_approved', False), ('audio_approved', False)]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.do_import(dict(self.manifest, **{field: value}))
        with self.assertRaises(ValueError):
            self.do_import(approve=False)
        self.assertFalse(self.store.exists())

    def test_missing_empty_corrupt_audio(self):
        for filename, data in [('missing.m4a', None), ('empty.m4a', b''), ('corrupt.m4a', b'not audio')]:
            path = self.tmp / filename
            if data is not None:
                path.write_bytes(data)
            with self.assertRaises(ValueError):
                self.do_import(dict(self.manifest, local_audio_path=str(path)))
        self.assertFalse(self.store.exists())

    def test_missing_asset_private_entry_and_wrong_language_fail_closed(self):
        self.do_import()
        for changed in [dict(self.entry, language='sl'), dict(self.entry, image_approved=False),
                        dict(self.entry, status='pending_review')]:
            self.assertNotIn('podcast', attach_companions([changed], self.store, self.public)[0])
        for path in (self.store / 'audio').glob('*'):
            path.unlink()
        self.assertNotIn('podcast', attach_companions([self.entry], self.store, self.public)[0])

    def test_private_adelheid_slovenian_test_never_matches_english_image(self):
        entry = dict(self.entry, person='Adelheid Popp', filename='AdelheidPopp-en.png')
        (self.public / entry['filename']).write_bytes(b'image fixture')
        (self.public / 'entries.json').write_text(json.dumps({'entries': [entry]}))
        manifest = dict(self.manifest, person=entry['person'], image_filename=entry['filename'], language='sl')
        with self.assertRaises(ValueError):
            self.do_import(manifest)
        self.assertFalse(self.store.exists())
        self.assertFalse((self.public / 'audio').exists())

    def test_store_must_be_private_and_conflicting_replacement_rejected(self):
        with self.assertRaises(ValueError):
            import_companion(self.manifest, self.public, self.public / 'store', approve=True)
        self.do_import()
        replacement = self.tmp / 'replacement.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=660:duration=1', '-c:a', 'aac', str(replacement)], check=True)
        with self.assertRaises(ValueError):
            self.do_import(dict(self.manifest, local_audio_path=str(replacement)))

    def test_revocation_removes_public_audio_and_malformed_store_does_not_break_images(self):
        podcast = self.do_import()
        attach_companions([self.entry], self.store, self.public)
        asset = self.public / podcast['url']
        self.assertTrue(asset.exists())
        for record in (self.store / 'records').glob('*.json'):
            record.write_text('[]')
        (self.store / 'records' / 'bad.json').write_text('{broken')
        attached = attach_companions([self.entry], self.store, self.public)
        self.assertEqual(attached, [self.entry])
        self.assertFalse(asset.exists())

    def test_normalizer_strips_private_fields_and_rejects_malformed_values(self):
        podcast = self.do_import()
        clean = normalize_podcast(dict(podcast, local_audio_path='/PRIVATE', notebook_url='PRIVATE'), self.entry)
        self.assertEqual(clean, podcast)
        for changed in [dict(podcast, url=123), dict(podcast, duration_seconds=float('nan')),
                        dict(podcast, mime_type='audio/aac'), dict(podcast, language='sl')]:
            self.assertIsNone(normalize_podcast(changed, self.entry))

    def test_same_subject_different_date_language_or_image_does_not_collide(self):
        self.do_import()
        entries = [self.entry, dict(self.entry, date='2026-10-01'),
                   dict(self.entry, filename='Other.png'), dict(self.entry, language='de')]
        attached = attach_companions(entries, self.store, self.public)
        self.assertEqual([bool(e.get('podcast')) for e in attached], [True, False, False, False])


if __name__ == '__main__':
    unittest.main()
