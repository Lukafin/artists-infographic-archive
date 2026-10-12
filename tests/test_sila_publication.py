"""Ensure the reviewed, versioned Sila document survives canonical rebuilds."""
import hashlib
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
import test_rebuild_gallery

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '217faf703ea24f49c9c47f0dacc84a3b37f444d2726966e91455b426d6ca39ae'

class SilaPublicationTests(unittest.TestCase):
    def test_exact_reviewed_document_and_notice_match_both_public_trees(self):
        for tree in ('docs', 'site'):
            folder = ROOT / tree / 'interactive/sila/v1'
            self.assertEqual(hashlib.sha256((folder / 'index.html').read_bytes()).hexdigest(), EXPECTED)
            self.assertIn('Copyright (c) 2026 Ryan', (folder / 'LICENSE').read_text())
        self.assertEqual((ROOT/'docs/interactive/sila/v1/LICENSE').read_bytes(),
                         (ROOT/'site/interactive/sila/v1/LICENSE').read_bytes())

    def test_two_canonical_rebuilds_preserve_versioned_static_document(self):
        helper = test_rebuild_gallery.RebuildGalleryOriginalArticleTests()
        self.addCleanup(helper.doCleanups)
        public, _, _, _ = helper.run_rebuild(dict(date='2026-08-16', person='sila', filename='Sila.png',
            category='school_poster', language='sl', sources=['https://www.wikidata.org/wiki/Q11402']))
        target = public / 'interactive/sila/v1'
        shutil.copytree(ROOT / 'docs/interactive/sila/v1', target)
        latest = (public/'latest.json').read_bytes()
        entries = (public/'entries.json').read_bytes()
        env = dict(os.environ, ARTISTS_ARCHIVE_BASE=str(public.parent/'workspace'),
            ARTISTS_ARCHIVE_RUNS_DIR=str(public.parent/'workspace/runs'), ARTISTS_ARCHIVE_PUBLIC_ROOT=str(public),
            ARTISTS_ARCHIVE_LEGACY_IMPORTED=str(public.parent/'workspace/imported_legacy_entries.json'))
        for _ in range(2):
            subprocess.run([sys.executable, str(public.parent/'rebuild_gallery.py')], env=env,
                           check=True, capture_output=True)
            self.assertEqual(hashlib.sha256((target/'index.html').read_bytes()).hexdigest(), EXPECTED)
            self.assertEqual((public/'latest.json').read_bytes(), latest)
            self.assertEqual((public/'entries.json').read_bytes(), entries)

if __name__ == '__main__':
    unittest.main()
