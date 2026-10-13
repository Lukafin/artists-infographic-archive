"""Availability comes from valid media; presentation refresh preserves published work."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gallery_index import build_entries_index, normalize_entry_metadata
import test_rebuild_gallery


class ArchiveFormatTests(unittest.TestCase):
    def setUp(self):
        self.entry = dict(date='2026-10-01', person='Reviewed topic', filename='Topic.png',
                          category='school_poster', language='sl', sources=[])
        self.podcast = dict(url='audio/' + 'a' * 64 + '.m4a', title='Reviewed topic',
                            language='sl', mime_type='audio/mp4', duration_seconds=120,
                            source='NotebookLM', companion_id='b' * 64)
        self.interactive = dict(url='https://example.org/experiment', title='Reviewed experiment',
                                language='sl', artifact_kind='interactive_site',
                                presentation_mode='sandboxed_iframe', companion_id='c' * 64)

    def test_overlapping_formats_count_topics_once_per_format(self):
        entries = [dict(self.entry, podcast=self.podcast, companions=[self.interactive, self.interactive]),
                   dict(self.entry, filename='Other.png')]
        index = build_entries_index(entries)
        self.assertEqual(index['summary']['total_entries'], 2)
        self.assertEqual(index['summary']['format_counts'],
                         {'infographic': 2, 'podcast': 1, 'interactive_site': 1})
        self.assertEqual(index['entries'][0]['formats'],
                         ['infographic', 'podcast', 'interactive_site'])

    def test_untrusted_format_tags_and_invalid_media_cannot_claim_availability(self):
        entry = dict(self.entry, formats=['podcast', 'interactive_site'],
                     podcast=dict(self.podcast, language='en'),
                     companions=[dict(self.interactive, url='javascript:alert(1)')])
        self.assertEqual(normalize_entry_metadata(entry)['formats'], ['infographic'])

    def test_public_refresh_preserves_existing_approved_media_order_and_latest(self):
        helper = test_rebuild_gallery.RebuildGalleryOriginalArticleTests()
        self.addCleanup(helper.doCleanups)
        entry = dict(self.entry, assignment_id='image-task')
        manifest = dict(schema='artists-reviewed-media-v1',
                        identity={key:entry[key] for key in ('date', 'filename', 'language', 'assignment_id', 'person')},
                        media=self.interactive, media_assignment_id='experiment-task', archive_entry_id='published-experiment',
                        topic_id='reviewed-topic', topic_revision=1, metadata_sha256='d'*64,
                        media_approved=True, image_approved=True, association_approved=True,
                        topic_published=True, embed_approved=True)
        public, _, _, before = helper.run_rebuild(entry, companion=manifest)
        before_latest = (public/'latest.json').read_bytes()
        env = dict(os.environ, ARTISTS_ARCHIVE_PUBLIC_ROOT=str(public),
                   ARTISTS_ARCHIVE_BASE=str(public.parent/'absent-private-stores'))
        subprocess.run([sys.executable, str(public.parent/'rebuild_gallery.py'), '--refresh-public-pages'],
                       env=env, check=True, capture_output=True)
        self.assertEqual(json.loads((public/'entries.json').read_text())['entries'], before['entries'])
        self.assertEqual((public/'latest.json').read_bytes(), before_latest)
        self.assertFalse((public.parent/'absent-private-stores').exists())
        self.assertIn('data-format="interactive_site"', (public/'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
