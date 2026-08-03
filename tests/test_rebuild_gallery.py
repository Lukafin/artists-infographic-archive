import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RebuildGalleryOriginalArticleTests(unittest.TestCase):
    def run_rebuild(self, entry: dict) -> tuple[Path, str, dict, dict]:
        temp_dir = Path(tempfile.mkdtemp(prefix='artists-gallery-test-'))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        workspace = temp_dir / 'workspace'
        runs_dir = workspace / 'runs' / 'test-entry'
        public_root = temp_dir / 'public'
        runs_dir.mkdir(parents=True)
        public_root.mkdir(parents=True)

        (runs_dir / 'entry.json').write_text(json.dumps(entry), encoding='utf-8')
        (public_root / entry['filename']).write_bytes(b'not-a-real-image-but-present')

        script = (ROOT / 'rebuild_gallery.py').read_text(encoding='utf-8')
        script = script.replace(
            "BASE = Path('/home/lukafinzgar/projects/.caller_tasks/artists')",
            f'BASE = Path({str(workspace)!r})',
        ).replace(
            "PUBLIC_ROOT = Path('/home/lukafinzgar/projects/.caller_tasks/artists-infographic-archive/docs')",
            f'PUBLIC_ROOT = Path({str(public_root)!r})',
        )
        (temp_dir / 'rebuild_gallery.py').write_text(script, encoding='utf-8')
        (temp_dir / 'gallery_index.py').write_text(
            (ROOT / 'gallery_index.py').read_text(encoding='utf-8'),
            encoding='utf-8',
        )

        subprocess.run(
            [sys.executable, str(temp_dir / 'rebuild_gallery.py')],
            cwd=temp_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        index_html = (public_root / 'index.html').read_text(encoding='utf-8')
        latest = json.loads((public_root / 'latest.json').read_text(encoding='utf-8'))
        entries = json.loads((public_root / 'entries.json').read_text(encoding='utf-8'))
        return public_root, index_html, latest, entries

    def test_science_news_entry_links_to_original_article(self):
        original_article = 'https://science.nasa.gov/example-discovery/'
        _, index_html, latest, entries = self.run_rebuild(
            {
                'date': '2026-07-31',
                'person': 'A surprising space discovery',
                'filename': 'SpaceDiscovery.png',
                'category': 'science_news',
                'language': 'en',
                'original_article_url': original_article,
                'sources': [
                    original_article,
                    'https://www.nature.com/articles/example',
                ],
                'age_suitability_details': {
                    'age_6': 'A simple explanation.',
                    'age_13': 'A more detailed explanation.',
                    'adult': 'The evidence and uncertainty.',
                },
            }
        )

        self.assertIn(f'href="{original_article}"', index_html)
        self.assertIn('data-original-article-link="1"', index_html)
        self.assertIn('Read the original article ↗', index_html)
        self.assertIn("original_article: 'Preberi izvirni članek ↗'", index_html)
        self.assertEqual(latest['original_article_url'], original_article)
        self.assertEqual(entries['entries'][0]['original_article_url'], original_article)

    def test_non_science_entry_does_not_render_original_article_link(self):
        unrelated_url = 'https://science.nasa.gov/should-not-render/'
        _, index_html, latest, _ = self.run_rebuild(
            {
                'date': '2026-07-31',
                'person': 'Gravity',
                'filename': 'Gravity.png',
                'category': 'school_poster',
                'language': 'en',
                'original_article_url': unrelated_url,
                'sources': ['https://science.nasa.gov/universe/gravity/'],
            }
        )

        self.assertNotIn(f'href="{unrelated_url}"', index_html)
        self.assertIsNone(latest['original_article_url'])

    def test_homepage_frames_archive_as_visual_learning_hub(self):
        public_root, index_html, _, _ = self.run_rebuild(
            {
                'date': '2026-07-31',
                'person': 'Climate change',
                'filename': 'ClimateChange.png',
                'category': 'school_poster',
                'language': 'en',
                'sources': ['https://science.nasa.gov/climate-change/evidence/'],
            }
        )

        self.assertIn('Visual Learning Archive', index_html)
        self.assertIn('Kid-friendly infographics about people, school topics and science discoveries', index_html)
        self.assertIn('Choose a collection', index_html)
        self.assertIn('People', index_html)
        self.assertIn('School posters', index_html)
        self.assertIn('Science news', index_html)
        self.assertIn('All infographics', index_html)
        self.assertIn('data-i18n="category_label">Collection</label>', index_html)
        self.assertIn('history.pushState', index_html)
        self.assertIn('setCategoryControlForCollection', index_html)
        self.assertIn('target.hash = \'archive\'', index_html)
        self.assertIn('Made with human supervision and', index_html)
        self.assertIn('Roj swarm agents', index_html)
        self.assertTrue((public_root / 'science-news.html').is_file())

    def test_science_news_collection_page_is_generated(self):
        public_root, _, _, _ = self.run_rebuild(
            {
                'date': '2026-07-31',
                'person': 'A surprising space discovery',
                'filename': 'SpaceDiscovery.png',
                'category': 'science_news',
                'language': 'en',
                'original_article_url': 'https://science.nasa.gov/example-discovery/',
                'sources': ['https://science.nasa.gov/example-discovery/'],
            }
        )
        science_page = (public_root / 'science-news.html').read_text(encoding='utf-8')

        self.assertIn('Science news explained', science_page)
        self.assertIn('Recent discoveries turned into simple visual summaries for young readers.', science_page)
        self.assertIn('Archaeology', science_page)
        self.assertIn('A surprising space discovery', science_page)
        self.assertIn('Read the original article ↗', science_page)


if __name__ == '__main__':
    unittest.main()
