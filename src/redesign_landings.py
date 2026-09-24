"""Apply the shared site design without changing localized content.

Trial: python3 src/redesign_landings.py --locales en ar-SA
All languages: python3 src/redesign_landings.py
Selected page types: add --pages home support privacy (the default is all three).
Validate without writing: add --check to either command.
"""

import argparse
from html.parser import HTMLParser
from pathlib import Path

import build


class Content(HTMLParser):
    """Content that must survive a layout-only conversion, in document order."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.elements = []
        self.in_style = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.in_style = True
        if tag in {"html", "img", "a", "link", "meta"}:
            if tag == "meta" and dict(attrs).get("name") == "theme-color":
                return
            self.elements.append((tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if not self.in_style and data.strip():
            self.text.append(" ".join(data.split()))


def ensure_content_preserved(original, updated):
    before, after = Content(original), Content(updated)
    if before.text != after.text:
        raise ValueError("text changed; refusing a layout-only conversion")
    if before.elements != after.elements:
        raise ValueError("images, links, language attributes or metadata changed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locales", nargs="+", metavar="ID", help="locale IDs from src/locales.json; default: all")
    parser.add_argument("--pages", nargs="+", choices=tuple(build.PAGES), default=list(build.PAGES),
                        help="page types to update; default: home support privacy")
    parser.add_argument("--check", action="store_true", help="validate the conversion without writing files")
    args = parser.parse_args(argv)
    site = build.Site()
    selected = set(args.locales) if args.locales else {loc["id"] for loc in site.locales}
    unknown = selected - {loc["id"] for loc in site.locales}
    if unknown:
        parser.error("unknown locale IDs: " + ", ".join(sorted(unknown)))

    # Prepare and validate every selected page before writing any of them.
    pending = []
    for loc in site.locales:
        if loc["id"] not in selected:
            continue
        for page in dict.fromkeys(args.pages):
            path = Path(build.ROOT) / build.page_dir(loc, page) / "index.html"
            try:
                original = path.read_text(encoding="utf-8")
                updated = site.render(loc, page)
                ensure_content_preserved(original, updated)
            except (OSError, ValueError) as exc:
                parser.exit(1, "%s/%s: %s\nNo pages were written.\n" % (loc["id"], page, exc))
            pending.append((path, updated))

    if not args.check:
        for path, updated in pending:
            path.write_text(updated, encoding="utf-8")
    print("%s %d pages; localized content preserved." % (
        "Validated" if args.check else "Updated", len(pending)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
