import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RebuildGalleryOriginalArticleTests(unittest.TestCase):
    def run_rebuild(self, entry) -> tuple[Path, str, dict, dict]:
        temp_dir = Path(tempfile.mkdtemp(prefix='artists-gallery-test-'))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        workspace = temp_dir / 'workspace'
        public_root = temp_dir / 'public'
        public_root.mkdir(parents=True)

        test_entries = entry if isinstance(entry, list) else [entry]
        for index, test_entry in enumerate(test_entries):
            runs_dir = workspace / 'runs' / f'test-entry-{index}'
            runs_dir.mkdir(parents=True)
            (runs_dir / 'entry.json').write_text(json.dumps(test_entry), encoding='utf-8')
            (public_root / test_entry['filename']).write_bytes(b'not-a-real-image-but-present')

        shutil.copy2(ROOT / 'rebuild_gallery.py', temp_dir / 'rebuild_gallery.py')
        (temp_dir / 'gallery_index.py').write_text(
            (ROOT / 'gallery_index.py').read_text(encoding='utf-8'),
            encoding='utf-8',
        )

        env = os.environ.copy()
        env.update({
            'ARTISTS_ARCHIVE_BASE': str(workspace),
            'ARTISTS_ARCHIVE_RUNS_DIR': str(workspace / 'runs'),
            'ARTISTS_ARCHIVE_PUBLIC_ROOT': str(public_root),
            'ARTISTS_ARCHIVE_LEGACY_IMPORTED': str(workspace / 'imported_legacy_entries.json'),
        })
        subprocess.run(
            [sys.executable, str(temp_dir / 'rebuild_gallery.py')],
            cwd=temp_dir,
            env=env,
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
        public_root, index_html, latest, entries = self.run_rebuild(
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

        science_news_html = (public_root / 'science-news.html').read_text(encoding='utf-8')
        self.assertNotIn('id="featured-info"', index_html)
        self.assertIn(f'href="{original_article}"', science_news_html)
        self.assertIn('data-original-article-link="1"', science_news_html)
        self.assertIn('Read the original article ↗', science_news_html)
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
        self.assertIn('Accessible infographics about people, school topics and science discoveries', index_html)
        self.assertIn('Choose a collection', index_html)
        self.assertIn('People', index_html)
        self.assertIn('School posters', index_html)
        self.assertIn('Science news', index_html)
        self.assertIn('.science-art { inset:0; }', index_html)
        self.assertIn('class="science-preview-image"', index_html)
        self.assertIn('All infographics', index_html)
        self.assertIn('data-i18n="category_label">Collection</label>', index_html)
        self.assertIn(
            '<option value="people" data-category-option="people">Famous people</option>',
            index_html,
        )
        self.assertIn('history.pushState', index_html)
        self.assertIn('setCategoryControlForCollection', index_html)
        self.assertIn(
            "const exactCategory = collection && collection !== 'all' ? collection : '';",
            index_html,
        )
        self.assertIn(
            "if (category === 'people' && !['artist', 'scientist', 'sport'].includes(entry.category)) return false;",
            index_html,
        )
        self.assertIn('function addCardBackdrops(root)', index_html)
        self.assertIn("backdrop.className = 'thumb-backdrop'", index_html)
        self.assertIn('.thumb img { position:absolute; inset:0; width:100%; height:100%; display:block; object-fit:contain;', index_html)
        self.assertIn('.thumb-image { z-index:1; object-fit:contain; }', index_html)
        self.assertIn('target.hash = \'archive\'', index_html)
        self.assertIn('Made with human supervision and', index_html)
        self.assertIn('Roj swarm agents', index_html)
        self.assertTrue((public_root / 'science-news.html').is_file())

    def test_people_collection_uses_three_distinct_previews(self):
        _, index_html, _, _ = self.run_rebuild(
            [
                {
                    'date': f'2026-07-{31 - index:02d}',
                    'person': person,
                    'filename': filename,
                    'category': category,
                    'language': 'en',
                    'sources': ['https://example.org/source'],
                }
                for index, (person, filename, category) in enumerate(
                    [
                        ('Ada Lovelace', 'AdaLovelace.png', 'scientist'),
                        ('Frida Kahlo', 'FridaKahlo.png', 'artist'),
                        ('Michael Jordan', 'MichaelJordan.png', 'sport'),
                    ]
                )
            ]
        )

        people_art = index_html.split(
            '<span class="collection-art people-art" aria-hidden="true">', 1
        )[1].split('</span>', 1)[0]
        self.assertEqual(people_art.count('class="people-sheet'), 3)
        self.assertEqual(
            {
                'AdaLovelace.png',
                'FridaKahlo.png',
                'MichaelJordan.png',
            },
            {
                filename
                for filename in (
                    'AdaLovelace.png',
                    'FridaKahlo.png',
                    'MichaelJordan.png',
                )
                if f'src="{filename}"' in people_art
            },
        )

    def test_card_titles_start_with_an_uppercase_letter(self):
        _, index_html, _, _ = self.run_rebuild(
            [
                {
                    'date': '2026-07-31',
                    'person': 'Featured topic',
                    'filename': 'FeaturedTopic.png',
                    'category': 'school_poster',
                    'language': 'en',
                    'sources': ['https://example.org/featured'],
                },
                {
                    'date': '2026-07-30',
                    'person': 'kemična reakcija',
                    'filename': 'KemicnaReakcija.png',
                    'category': 'school_poster',
                    'language': 'sl',
                    'sources': ['https://example.org/chemistry'],
                },
            ]
        )

        self.assertIn('<h3>Kemična reakcija</h3>', index_html)
        self.assertIn('function displayTitle(value)', index_html)

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
        self.assertNotIn('Search archive', science_page)
        self.assertNotIn('science-trust', science_page)
        self.assertNotIn('science-open', science_page)
        self.assertNotIn('<details class="science-sources">', science_page)
        self.assertIn('<section class="science-sources"', science_page)
        self.assertIn(
            '>Source 1 (https://science.nasa.gov/example-discovery/)</a>',
            science_page,
        )
        self.assertNotIn('>Source 1</a>', science_page)
        self.assertNotIn('← Home', science_page)
        self.assertNotIn('<span class="pill">1 explainers</span>', science_page)
        self.assertIn('data-lang-option="en"', science_page)
        self.assertIn('data-lang-option="sl"', science_page)
        self.assertIn("localStorage.getItem('archive-ui-lang')", science_page)
        self.assertIn("science_title: 'Razložene znanstvene novice'", science_page)
        self.assertIn("source: 'Vir'", science_page)


if __name__ == '__main__':
    unittest.main()
