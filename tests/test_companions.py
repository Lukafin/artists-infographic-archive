import copy
import json
import tempfile
import unittest
from pathlib import Path
from companions import import_media, attach_media, normalize_media


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'docs'
        self.public.mkdir()
        self.store = self.root / 'private'
        self.entry = dict(date='2026-10-11', filename='image.png', language='en', assignment_id='image-assignment', person='Exact Subject')
        (self.public / 'image.png').write_bytes(b'image fixture')
        (self.public / 'entries.json').write_text(json.dumps({'entries':[self.entry]}))
        self.manifest = dict(schema='artists-reviewed-media-v1', identity=self.entry, media_approved=True, image_approved=True,
            association_approved=True, topic_published=True, embed_approved=True, media_assignment_id='video-assignment',
            archive_entry_id='reviewed-entry', topic_id='topic', topic_revision=1, metadata_sha256='a'*64,
            media=dict(title='Reviewed explanation', url='https://example.org/video.mp4', language='en',
                       artifact_kind='video', presentation_mode='native_video', mime_type='video/mp4'))

    def test_import_exact_identity_and_late_attach(self):
        media = import_media(self.manifest, self.public, self.store, approve=True)
        self.assertEqual(import_media(self.manifest, self.public, self.store, approve=True), media)
        attached = attach_media([self.entry], self.store)
        self.assertEqual(attached[0]['companions'], [media])
        self.assertNotIn('metadata_sha256', media)
        self.assertEqual(list(self.public.iterdir()).__len__(), 2, 'Import does not publish')
        for key in self.entry:
            wrong = dict(self.entry, **{key:'wrong'})
            self.assertNotIn('companions', attach_media([wrong], self.store)[0])
        for flag in ('private', 'image_approved'):
            private = dict(self.entry, **{flag:flag == 'private'})
            self.assertNotIn('companions', attach_media([private], self.store)[0])

    def test_gates_identity_and_conflict(self):
        with self.assertRaises(ValueError):
            import_media(self.manifest, self.public, self.store)
        for key in ('image_approved','media_approved','association_approved','topic_published','embed_approved'):
            bad = dict(self.manifest, **{key:False})
            with self.assertRaises(ValueError):
                import_media(bad, self.public, self.store, approve=True)
        for key in self.entry:
            bad = copy.deepcopy(self.manifest)
            bad['identity'][key] = 'wrong'
            with self.assertRaises(ValueError):
                import_media(bad, self.public, self.store, approve=True)
        for store in (self.public, self.public/'private', self.root/'site'/'private'):
            with self.assertRaises(ValueError):
                import_media(self.manifest, self.public, store, approve=True)
        import_media(self.manifest, self.public, self.store, approve=True)
        bad = copy.deepcopy(self.manifest)
        bad['media']['url'] = 'https://example.org/replacement.mp4'
        with self.assertRaises(ValueError):
            import_media(bad, self.public, self.store, approve=True)

    def test_url_and_presentation_fail_closed(self):
        media = import_media(self.manifest, self.public, self.store, approve=True)
        for url in ('javascript:alert(1)', '//example.org/x', 'https://u:p@example.org/x.mp4', 'https://example.org/\\x.mp4', 'https://example.org/\nx.mp4', 'https://example.org/watch'):
            self.assertIsNone(normalize_media(dict(media, url=url), self.entry))
        self.assertIsNone(normalize_media(dict(media, presentation_mode='arbitrary_iframe'), self.entry))
        self.assertIsNone(normalize_media(dict(media, language='sl'), self.entry))
        self.assertIsNone(normalize_media(dict(media, mime_type='text/html'), self.entry))
        link = dict(media, url='https://example.org/watch', presentation_mode='link')
        self.assertIsNotNone(normalize_media(link, self.entry), 'Historical webpage links remain link-only')

    def test_revocation_untrusted_inline_and_ambiguity(self):
        self.assertNotIn('companions', attach_media([dict(self.entry, companions=[self.manifest['media']])], self.store)[0])
        import_media(self.manifest, self.public, self.store, approve=True)
        path = next((self.store/'records').glob('*.json'))
        record = json.loads(path.read_text())
        record['approved'] = False
        path.write_text(json.dumps(record))
        self.assertNotIn('companions', attach_media([self.entry], self.store)[0])
        record['approved'] = True
        path.write_text(json.dumps(record))
        (path.parent/'duplicate.json').write_text(json.dumps(record))
        self.assertNotIn('companions', attach_media([self.entry], self.store)[0])
        (path.parent/'malformed.json').write_text('null')
        self.assertEqual(len(attach_media([self.entry], self.store)), 1)


if __name__ == '__main__':
    unittest.main()
