"""The landing redesign may change presentation, but must preserve page content."""

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import redesign_landings
from redesign_landings import ensure_content_preserved


ARABIC_PAGE = """<!doctype html>
<html lang="ar" dir="rtl" class="no-tracking no-caps">
<head>
  <meta charset="utf-8">
  <meta name="description" content="تحرير الصور على iPhone">
  <meta name="theme-color" content="#07110d">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'">
  <meta property="og:locale" content="ar_AR">
  <title>RawMask Studio - تحرير الصور</title>
  <link rel="canonical" href="https://example.test/ar/">
  <link rel="alternate" hreflang="en" href="https://example.test/">
  <style>body { background: black; }</style>
</head>
<body>
  <main class="wrap">
    <h1>RawMask Studio</h1>
    <p>اختر صورتك باستخدام <span class="ui" lang="en">Select</span>.</p>
    <img src="../assets/select.webp"
         srcset="../assets/select.webp 1x, ../assets/select@2x.webp 2x"
         alt="اختيار صورة" width="200" height="430" sizes="200px"
         loading="lazy" decoding="async">
    <a href="../support/" lang="ar" aria-label="الدعم">الدعم</a>
    <a href="../" hreflang="en" lang="en">English</a>
  </main>
</body>
</html>
"""


class ContentPreservationTests(unittest.TestCase):
    def assert_rejected(self, original, replacement):
        self.assertIn(original, ARABIC_PAGE)
        changed = ARABIC_PAGE.replace(original, replacement, 1)
        self.assertNotEqual(changed, ARABIC_PAGE)
        with self.assertRaises(ValueError):
            ensure_content_preserved(ARABIC_PAGE, changed)

    def test_accepts_presentation_changes_and_semantic_wrappers(self):
        redesigned = (
            ARABIC_PAGE
            .replace("background: black", "background: #081b16; color: #edf1e9")
            .replace("</style>", "h1 { -webkit-box-reflect: below 3px; }</style>")
            .replace('content="#07110d"', 'content="#081b16"')
            .replace('<main class="wrap">', '<main class="wrap"><section class="hero">')
            .replace("</main>", "</section></main>")
        )
        ensure_content_preserved(ARABIC_PAGE, redesigned)

    def test_rejects_copy_changes_including_translations_and_inline_labels(self):
        for original, replacement in (
            ("اختر صورتك باستخدام", "عدّل صورتك باستخدام"),
            (">Select<", ">Choose<"),
            ("<h1>RawMask Studio</h1>", ""),
            ("</main>", "<p>Additional copy</p></main>"),
        ):
            with self.subTest(original=original):
                self.assert_rejected(original, replacement)

    def test_rejects_changed_image_content_or_attributes(self):
        changes = {
            'src="../assets/select.webp"': 'src="../assets/other.webp"',
            'srcset="../assets/select.webp 1x, ../assets/select@2x.webp 2x"':
                'srcset="../assets/select.webp 1x"',
            'alt="اختيار صورة"': 'alt="صورة مختلفة"',
            'width="200"': 'width="201"',
            'height="430"': 'height="431"',
            'sizes="200px"': 'sizes="240px"',
            'loading="lazy"': 'loading="eager"',
            'decoding="async"': '',
            '</main>': '<img src="extra.webp" alt="Extra"></main>',
        }
        for original, replacement in changes.items():
            with self.subTest(attribute=original):
                self.assert_rejected(original, replacement)

    def test_rejects_link_destination_or_language_attribute_changes(self):
        changes = {
            'href="../support/"': 'href="../privacy/"',
            'aria-label="الدعم"': 'aria-label="المساعدة"',
            'hreflang="en" lang="en"': 'hreflang="fr" lang="fr"',
            '<a href="../support/" lang="ar"': '<a href="../support/" lang="en"',
        }
        for original, replacement in changes.items():
            with self.subTest(attribute=original):
                self.assert_rejected(original, replacement)

    def test_rejects_document_language_or_direction_changes(self):
        for original, replacement in (
            ('<html lang="ar"', '<html lang="en"'),
            ('dir="rtl"', 'dir="ltr"'),
            ('class="no-tracking no-caps"', 'class="no-tracking"'),
        ):
            with self.subTest(attribute=original):
                self.assert_rejected(original, replacement)

    def test_rejects_metadata_and_search_language_link_changes(self):
        changes = {
            'content="تحرير الصور على iPhone"': 'content="وصف مختلف"',
            'content="ar_AR"': 'content="en_US"',
            'charset="utf-8"': 'charset="iso-8859-1"',
            "content=\"default-src 'none'\"": "content=\"default-src 'self'\"",
            '<title>RawMask Studio - تحرير الصور</title>': '<title>Changed title</title>',
            'href="https://example.test/ar/"': 'href="https://example.test/"',
            'rel="alternate" hreflang="en"': 'rel="alternate" hreflang="fr"',
        }
        for original, replacement in changes.items():
            with self.subTest(metadata=original):
                self.assert_rejected(original, replacement)


class ConversionCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.locales = [{"id": "en", "slug": ""}, {"id": "ar-SA", "slug": "ar"}]
        self.originals = {}
        self.updated = {}
        for loc in self.locales:
            for page in ("home", "support", "privacy"):
                key = (loc["id"], page)
                source = (
                    '<html><head><style>body { color: black; }</style></head>'
                    '<body><h1>%s %s</h1></body></html>' % key
                )
                path = self.root / redesign_landings.build.page_dir(loc, page) / "index.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
                self.originals[path] = source
                self.updated[key] = source.replace("color: black", "color: #edf1e9")
        self.site = SimpleNamespace(
            locales=self.locales,
            render=Mock(side_effect=lambda loc, page: self.updated[(loc["id"], page)]),
        )

    def run_conversion(self, args):
        with patch.object(redesign_landings.build, "ROOT", self.root), \
                patch.object(redesign_landings.build, "Site", return_value=self.site), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return redesign_landings.main(args)

    def assert_files_unchanged(self):
        for path, original in self.originals.items():
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_pages_and_locales_filter_the_written_files(self):
        self.assertEqual(self.run_conversion(["--locales", "en", "--pages", "support", "privacy"]), 0)
        self.assertEqual(self.site.render.call_count, 2)
        for path, original in self.originals.items():
            selected = path in {self.root / page / "index.html" for page in ("support", "privacy")}
            expected = original.replace("color: black", "color: #edf1e9") if selected else original
            self.assertEqual(path.read_text(encoding="utf-8"), expected)

    def test_default_converts_every_page_for_every_locale(self):
        self.assertEqual(self.run_conversion([]), 0)
        self.assertEqual(self.site.render.call_count, 6)
        for path, original in self.originals.items():
            self.assertEqual(path.read_text(encoding="utf-8"), original.replace("color: black", "color: #edf1e9"))

    def test_check_validates_every_candidate_without_writing(self):
        self.assertEqual(self.run_conversion(["--check"]), 0)
        self.assertEqual(self.site.render.call_count, 6)
        self.assert_files_unchanged()

    def test_later_content_failure_prevents_all_writes(self):
        self.updated[("ar-SA", "privacy")] = self.updated[("ar-SA", "privacy")].replace("ar-SA privacy", "Changed copy")
        with self.assertRaises(SystemExit) as error:
            self.run_conversion([])
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(self.site.render.call_count, 6)
        self.assert_files_unchanged()


if __name__ == "__main__":
    unittest.main()
