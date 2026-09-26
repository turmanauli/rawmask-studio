"""Build the RawMask Studio website in every language.

Usage:
  python3 src/build.py                    build every page and sitemap.xml
  python3 src/build.py --allow-missing    build only the languages that have a strings file
  python3 src/build.py --check-strings ID validate src/strings/ID.json against en.json
  python3 src/build.py --preview ID DIR   render one language's pages into DIR (nothing in the repo changes)
  python3 src/build.py --check-site       verify the built site (links, hreflang, lang/dir, sitemap)

Inputs: src/locales.json, src/strings/*.json, src/store/*.json, src/icons.json,
src/*.css, assets/badges/*.svg and assets/screenshots/*/*.webp. Outputs: index.html,
support/index.html and privacy/index.html at the root (English) and under
each language folder, plus sitemap.xml.
"""
import html
import json
import os
import posixpath
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
BASE_URL = "https://turmanauli.github.io/rawmask-studio/"
APP_STORE_URL = "https://apps.apple.com/app/apple-store/id6814994539?pt=129497618&ct=GitHub%20Pages&mt=8"
APP_ID = "6814994539"
PAGES = {"home": "", "support": "support/", "privacy": "privacy/"}
SHOTS = ["01-select", "02-detect", "03-masks", "04-adjust", "05-save"]
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'"

# Characters the site copy must never contain: long dashes, horizontal bar,
# arrows, and emoji or pictographs.
FORBIDDEN = re.compile(
    "[\u2012-\u2015\u2E3A\u2E3B\uFE58\u2190-\u21FF\u27F0-\u27FF\u2900-\u297F"
    "\u2B00-\u2BFF\u2600-\u27BF\uFE0F\U0001F000-\U0001FAFF]")
TAG = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)([^<>]*?)\s*(/?)\s*>")
ATTR = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=\s*(\"[^\"]*\"|'[^']*')")
UI_SPAN = re.compile(r"<span class=\"ui\" lang=\"en\">(.*?)</span>", re.S)
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
BAD_AMP = re.compile(r"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)")
ALLOWED_TAGS = {"a", "strong", "span", "br", "em", "bdi"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_locales():
    return load_json(os.path.join(SRC, "locales.json"))["locales"]


def strings_path(loc_id):
    return os.path.join(SRC, "strings", loc_id + ".json")


# ---------------------------------------------------------------- validation

def tag_signature(fragment):
    sig = []
    for closing, name, attrs, _ in TAG.findall(fragment):
        pairs = tuple(sorted((k.lower(), v[1:-1]) for k, v in ATTR.findall(attrs)))
        sig.append((closing, name.lower(), pairs))
    return Counter(sig)


def text_only(fragment):
    return html.unescape(TAG.sub("", fragment))


def check_fragment(path, en, tr, errors, warnings):
    where = "/".join(str(p) for p in path)
    if not tr.strip():
        errors.append("%s: empty string" % where)
        return
    if FORBIDDEN.search(tr):
        chars = sorted(set(FORBIDDEN.findall(tr)))
        errors.append("%s: forbidden character(s) %s (long dashes, arrows and emoji are not allowed; rephrase or use a plain hyphen)"
                      % (where, ", ".join("U+%04X" % ord(c) for c in chars)))
    for closing, name, attrs, _ in TAG.findall(tr):
        if name.lower() not in ALLOWED_TAGS:
            errors.append("%s: tag <%s> is not allowed" % (where, name))
    if tag_signature(en) != tag_signature(tr):
        missing = tag_signature(en) - tag_signature(tr)
        extra = tag_signature(tr) - tag_signature(en)
        errors.append("%s: HTML tags differ from English. Missing: %s. Extra: %s" % (
            where, fmt_sig(missing), fmt_sig(extra)))
    if Counter(PLACEHOLDER.findall(en)) != Counter(PLACEHOLDER.findall(tr)):
        errors.append("%s: placeholders differ (English has %s)" % (where, sorted(PLACEHOLDER.findall(en))))
    en_ui = Counter(m.strip() for m in UI_SPAN.findall(en))
    tr_ui = Counter(m.strip() for m in UI_SPAN.findall(tr))
    if en_ui != tr_ui:
        errors.append("%s: app UI labels must stay in English, unchanged, inside <span class=\"ui\" lang=\"en\">. Expected %s, found %s"
                      % (where, sorted(en_ui.elements()), sorted(tr_ui.elements())))
    if BAD_AMP.search(tr):
        errors.append("%s: bare '&' found; write &amp;" % where)
    stripped = TAG.sub("", tr)
    if "<" in stripped or ">" in stripped:
        errors.append("%s: raw '<' or '>' outside a tag; write &lt; or &gt;" % where)
    if "mailto:" in en and "turmanauli.beso@gmail.com" not in tr:
        errors.append("%s: the email address is missing" % where)
    if tr == en and len(text_only(en)) > 24 and re.search("[a-z]{4}", en):
        warnings.append("%s: identical to English (is it translated?)" % where)


def fmt_sig(counter):
    if not counter:
        return "none"
    out = []
    for (closing, name, attrs), n in counter.items():
        attr_text = "".join(' %s="%s"' % kv for kv in attrs)
        out.append("<%s%s%s> x%d" % (closing, name, attr_text, n))
    return ", ".join(out)


def compare(path, en, tr, errors, warnings):
    if isinstance(en, dict):
        if not isinstance(tr, dict):
            errors.append("%s: expected an object" % "/".join(map(str, path)))
            return
        for key in en:
            if key not in tr:
                errors.append("%s: missing key" % "/".join(map(str, path + [key])))
        for key in tr:
            if key not in en:
                errors.append("%s: unexpected key" % "/".join(map(str, path + [key])))
        for key in en:
            if key in tr:
                if key == "id":
                    if tr[key] != en[key]:
                        errors.append("%s: section ids must stay exactly as in English (%r)" % (
                            "/".join(map(str, path + [key])), en[key]))
                    continue
                compare(path + [key], en[key], tr[key], errors, warnings)
    elif isinstance(en, list):
        if not isinstance(tr, list) or len(tr) != len(en):
            errors.append("%s: expected a list of %d items" % ("/".join(map(str, path)), len(en)))
            return
        for i, (a, b) in enumerate(zip(en, tr)):
            compare(path + [i], a, b, errors, warnings)
    elif isinstance(en, str):
        if not isinstance(tr, str):
            errors.append("%s: expected a string" % "/".join(map(str, path)))
            return
        check_fragment(path, en, tr, errors, warnings)


def validate_strings(loc_id):
    en = load_json(strings_path("en"))
    try:
        tr = load_json(strings_path(loc_id))
    except (OSError, ValueError) as exc:
        return ["cannot read %s: %s" % (strings_path(loc_id), exc)], []
    errors, warnings = [], []
    compare([], en, tr, errors, warnings)
    return errors, warnings


# ------------------------------------------------------------------ rendering

def page_dir(loc, page):
    return (loc["slug"] + "/" if loc["slug"] else "") + PAGES[page]


def page_url(loc, page):
    return BASE_URL + page_dir(loc, page)


def rel(from_dir, target, is_dir=True):
    """Relative link from the page folder from_dir to a site path."""
    r = posixpath.relpath("/" + target.rstrip("/"), "/" + from_dir.rstrip("/") if from_dir else "/")
    if r == ".":
        return "./"
    return r + "/" if is_dir else r


def attr(value):
    return html.escape(value, quote=True)


def plain(fragment):
    """HTML fragment to plain text, for <title> and meta attributes."""
    return re.sub(r"\s+", " ", text_only(fragment)).strip()


def fill(fragment, links):
    for key, value in links.items():
        fragment = fragment.replace("{%s}" % key, value)
    return fragment


def badge_img(loc, from_dir, height):
    path = os.path.join(ROOT, "assets", "badges", loc["badge"] + ".svg")
    with open(path, encoding="utf-8") as f:
        head = f.read(2000)
    svg = re.search(r"<svg[^>]*>", head, re.S).group(0)
    w = float(re.search(r'\bwidth="([\d.]+)', svg).group(1))
    h = float(re.search(r'\bheight="([\d.]+)', svg).group(1))
    return w * height / h, rel(from_dir, "assets/badges/%s.svg" % loc["badge"], is_dir=False)


GLOBE = ('<svg class="globe" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
         '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.3"/>'
         '<ellipse cx="8" cy="8" rx="2.8" ry="6.5" fill="none" stroke="currentColor" stroke-width="1.3"/>'
         '<path d="M1.8 5.8h12.4M1.8 10.2h12.4" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>')

CSS_BASE = """:root {
  color-scheme: dark;
  --bg: #07110d;
  --surface: #0c1a15;
  --surface-2: #10231c;
  --border: #1d3a30;
  --text: #e3f0eb;
  --muted: #9bb7ad;
  --accent: #3ee6d2;
  --accent-soft: rgba(62, 230, 210, 0.12);
  --accent-ink: #03201b;
  --radius: 14px;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
a { color: var(--accent); text-underline-offset: 3px; overflow-wrap: anywhere; }
a:hover { text-decoration-thickness: 2px; }
a:focus-visible, summary:focus-visible, .shots:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
.wrap { max-width: 44rem; margin: 0 auto; padding: 0 16px; }
header.site { border-bottom: 1px solid var(--border); }
header.site .wrap { position: relative; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 12px; min-height: 60px; padding-top: 8px; padding-bottom: 8px; }
.brand { display: flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none; font-weight: 650; letter-spacing: -0.01em; }
.brand img { flex: none; }
.header-end { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; margin-inline-start: auto; }
nav ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px; }
nav a { display: block; padding: 7px 11px; border-radius: 999px; color: var(--muted); text-decoration: none; font-size: 15px; }
nav a:hover { color: var(--text); background: var(--surface-2); }
nav a[aria-current="page"] { color: var(--accent); background: var(--accent-soft); }
.lang summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 6px 11px; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: 15px; }
.lang summary::-webkit-details-marker { display: none; }
.lang summary:hover, .lang[open] summary { color: var(--text); background: var(--surface-2); }
.lang ul { position: absolute; top: calc(100% - 2px); inset-inline-end: 16px; z-index: 10; list-style: none; margin: 0; padding: 8px; width: min(34rem, calc(100% - 32px)); max-height: min(70vh, 30rem); overflow: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr)); gap: 2px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5); }
.lang li a { display: block; padding: 6px 10px; border-radius: 8px; color: var(--text); text-decoration: none; font-size: 15px; }
.lang li a:hover { background: var(--surface-2); }
.lang li a[aria-current="page"] { color: var(--accent); background: var(--accent-soft); }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
p { margin: 0 0 14px; }
.callout { background: var(--surface); border: 1px solid var(--border); border-inline-start: 3px solid var(--accent); border-radius: var(--radius); padding: 16px 18px; margin: 24px 0; }
.callout p:last-child { margin-bottom: 0; }
.muted { color: var(--muted); }
.ui { unicode-bidi: isolate; }
.badge { display: inline-block; flex: none; line-height: 0; border-radius: 8px; }
.badge img { display: block; }
footer.site { border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; }
footer.site .wrap { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 20px; padding-top: 20px; padding-bottom: 28px; }
footer.site ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 16px; }
footer.site a { color: var(--muted); }
footer.site a:hover { color: var(--text); }
footer.site .badge { margin: 11px 0; }
html.no-tracking .brand, html.no-tracking h1, html.no-tracking h2, html.no-tracking .eyebrow { letter-spacing: normal; }
html.no-caps .eyebrow { text-transform: none; }
"""

CSS_HOME = """main.wrap { padding-top: 44px; padding-bottom: 56px; }
h1 { font-size: clamp(2rem, 7vw, 2.8rem); line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 12px; }
h2 { font-size: 1.25rem; line-height: 1.3; letter-spacing: -0.01em; margin: 44px 0 10px; }
h3 { font-size: 1.02rem; line-height: 1.35; margin: 0 0 6px; }
.eyebrow { color: var(--accent); font-size: 13px; font-weight: 650; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 12px; }
.lead { font-size: 1.15rem; color: var(--muted); max-width: 36rem; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 24px; }
.actions .badge { margin-inline-end: 4px; }
.button { display: inline-block; padding: 11px 18px; border-radius: 999px; font-weight: 600; font-size: 15px; text-decoration: none; }
.button.primary { background: var(--accent); color: var(--accent-ink); }
.button.secondary { border: 1px solid var(--border); color: var(--text); background: var(--surface); }
.button:hover { text-decoration: none; filter: brightness(1.08); }
.ui-note { margin: 16px 0 0; color: var(--muted); font-size: 15px; }
.shots { list-style: none; margin: 16px 0 0; padding: 0 0 14px; display: flex; gap: 14px; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-color: var(--border) transparent; }
.shots li { flex: none; scroll-snap-align: start; }
.shots img { display: block; width: 200px; height: auto; border-radius: 16px; border: 1px solid var(--border); background: var(--surface); }
.features { list-style: none; margin: 16px 0 0; padding: 0; display: grid; grid-template-columns: 1fr; gap: 12px; }
@media (min-width: 600px) { .features { grid-template-columns: 1fr 1fr; } }
.features > li { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; }
.features p { margin: 0; color: var(--muted); font-size: 15px; }
.features.sections { display: block; }
@media (min-width: 600px) { .features.sections { columns: 2; column-gap: 12px; } }
.features.sections > li { break-inside: avoid; margin-bottom: 12px; }
.features.sections ul { margin: 0; padding-inline-start: 1.15rem; color: var(--muted); font-size: 15px; }
.features.sections ul li { margin-bottom: 4px; }
.outro { margin-top: 12px; }
"""

CSS_SUPPORT = """body { line-height: 1.65; }
main.wrap { padding-top: 40px; padding-bottom: 56px; }
h1 { font-size: clamp(1.9rem, 6vw, 2.5rem); line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 8px; }
h2 { font-size: 1.2rem; line-height: 1.3; letter-spacing: -0.01em; margin: 40px 0 12px; scroll-margin-top: 16px; }
p, ul { margin: 0 0 12px; }
ul { padding-inline-start: 1.25rem; }
li { margin-bottom: 6px; }
.meta { color: var(--muted); font-size: 15px; }
.note { color: var(--muted); font-size: 14px; }
.faq { border-top: 1px solid var(--border); }
.faq section { border-bottom: 1px solid var(--border); padding: 18px 0 6px; }
.faq h3 { font-size: 1.02rem; line-height: 1.35; margin: 0 0 8px; }
.faq p, .faq li { color: #cfe2db; }
.path { font-weight: 600; }
"""

CSS_PRIVACY = """body { line-height: 1.65; }
main.wrap { padding-top: 40px; padding-bottom: 56px; }
h1 { font-size: clamp(1.9rem, 6vw, 2.5rem); line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 8px; }
h2 { font-size: 1.2rem; line-height: 1.3; letter-spacing: -0.01em; margin: 40px 0 10px; scroll-margin-top: 16px; }
h3 { font-size: 1.02rem; line-height: 1.35; margin: 22px 0 6px; }
p, ul { margin: 0 0 14px; }
ul { padding-inline-start: 1.25rem; }
li { margin-bottom: 6px; }
.meta { color: var(--muted); font-size: 15px; margin-bottom: 0; }
.note { color: var(--muted); font-size: 14px; margin: 10px 0 0; }
.path { font-weight: 600; }
"""

# Scripts where letter-spacing breaks joining or looks wrong, and scripts with no case.
NO_TRACKING = {"ar", "ur", "he", "hi", "mr", "bn", "gu", "pa", "or", "ta", "te", "kn", "ml", "th",
               "ja", "ko", "zh-Hans", "zh-Hant"}


class Site:
    def __init__(self, allow_missing=False, only=None):
        self.all_locales = load_locales()
        self.strings = {}
        for loc in self.all_locales:
            if only and loc["id"] not in only:
                continue
            path = strings_path(loc["id"])
            if os.path.exists(path):
                self.strings[loc["id"]] = load_json(path)
            elif not allow_missing and not only:
                raise SystemExit("missing %s (use --allow-missing for a partial build)" % path)
        self.locales = [l for l in self.all_locales if l["id"] in self.strings]
        store = os.path.join(SRC, "store")
        self.captions = {c["locale"]: c for c in load_json(os.path.join(store, "captions.json"))}
        device_path = os.path.join(store, "device_captions.json")
        self.device_captions = {c["locale"]: c for c in load_json(device_path)} if os.path.exists(device_path) else {}
        self.ui_notes = load_json(os.path.join(store, "ui_notes.json"))
        meta_path = os.path.join(store, "metadata.json")
        self.metadata = load_json(meta_path) if os.path.exists(meta_path) else {}
        self.icons = load_json(os.path.join(SRC, "icons.json"))

    # store copy for a site language; English uses en-US
    def store(self, loc):
        key = "en-US" if loc["id"] == "en" else loc["id"]
        return self.metadata.get(key)

    def caption(self, loc, i):
        if loc["id"] == "en":
            return EN_CAPTIONS[i]
        c = self.captions[loc["id"]]
        return c["titles"][i], c["subs"][i]

    def device_panels(self, loc, here):
        """The iPad and Mac screenshot panels, or [] while the language has none yet."""
        folder = "en" if loc["id"] == "en" else loc["slug"]
        if not all(os.path.isdir(os.path.join(ROOT, "assets", "screenshots", folder, d)) for d in DEVICE_SHOTS):
            return []
        if loc["id"] == "en":
            captions = EN_DEVICE_CAPTIONS
        elif loc["id"] in self.device_captions:
            c = self.device_captions[loc["id"]]
            captions = {d: list(zip(c[d]["titles"], c[d]["subs"])) for d in DEVICE_SHOTS}
        else:
            raise SystemExit("%s has iPad and Mac screenshots but no captions in src/store/device_captions.json" % loc["id"])
        out = []
        for device, (names, rows) in DEVICE_SHOTS.items():
            out.append('  <div class="device-panel device-%s" role="group" tabindex="0" aria-labelledby="screenshots tab-%s">'
                       % (device, device))
            start = 0
            for count in rows:
                out.append('    <ul>')
                for i in range(start, start + count):
                    name = names[i]
                    small, large = device_widths(folder, device, name)
                    w, h = screenshot_size(folder + "/" + device, name, small)
                    ratio = w / h
                    mobile = 300 if device == "mac" else round(260 * ratio)
                    desktop = 370 if device == "mac" else round(320 * ratio)
                    base = rel(here, "assets/screenshots/%s/%s/%s" % (folder, device, name), is_dir=False)
                    cap_title, cap_sub = captions[device][i]
                    out.append('      <li style="--ar: %.4f"><img src="%s-%d.webp" srcset="%s-%d.webp %dw, %s-%d.webp %dw" sizes="(max-width: 660px) %dpx, %dpx" width="%d" height="%d" alt="%s" loading="lazy" decoding="async"></li>' % (
                        ratio, base, small, base, small, small, base, large, large, mobile, desktop, w, h,
                        attr("%s %s" % (cap_title, cap_sub))))
                out.append('    </ul>')
                start += count
            out.append('  </div>')
        return out

    def head(self, loc, page, title, description):
        out = ['<!doctype html>',
               '<html lang="%s"%s%s>' % (loc["lang"], ' dir="rtl"' if loc["dir"] == "rtl" else "", self.html_class(loc)),
               '<head>',
               '<meta charset="utf-8">',
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
               '<meta http-equiv="Content-Security-Policy" content="%s">' % CSP,
               '<meta name="color-scheme" content="dark">',
               '<meta name="theme-color" content="#081b16">',
               '<meta name="description" content="%s">' % attr(description),
               '<meta name="apple-itunes-app" content="app-id=%s">' % APP_ID,
               '<title>%s</title>' % html.escape(title, quote=False),
               '<link rel="canonical" href="%s">' % page_url(loc, page)]
        for other in self.locales:
            for code in other["hreflang"]:
                out.append('<link rel="alternate" hreflang="%s" href="%s">' % (code, page_url(other, page)))
        out += ['<meta property="og:type" content="website">',
                '<meta property="og:site_name" content="RawMask Studio">',
                '<meta property="og:title" content="%s">' % attr(title),
                '<meta property="og:description" content="%s">' % attr(description),
                '<meta property="og:url" content="%s">' % page_url(loc, page),
                '<meta property="og:locale" content="%s">' % loc["og_locale"],
                '<meta name="twitter:card" content="summary">',
                '<link rel="icon" type="image/png" href="%s">' % self.icons["favicon"]]
        css = CSS_BASE + {"home": CSS_HOME, "support": CSS_SUPPORT, "privacy": CSS_PRIVACY}[page]
        design_css = []
        for stylesheet in ("theme.css", "landing.css" if page == "home" else "document.css"):
            with open(os.path.join(SRC, stylesheet), encoding="utf-8") as f:
                design_css.append(f.read())
        css += '\n/* Site design */\n:root { --bullet-logo: url("%s"); }\n%s\n/* End site design */\n' % (
            self.icons["logo"], "\n".join(design_css))
        out += ['<style>', css.rstrip("\n"), '</style>', '</head>', '<body>']
        return "\n".join(out)

    def html_class(self, loc):
        classes = []
        if loc["lang"] in NO_TRACKING:
            classes += ["no-tracking", "no-caps"]
        return ' class="%s"' % " ".join(classes) if classes else ""

    def header(self, loc, page):
        s = self.strings[loc["id"]]["common"]
        here = page_dir(loc, page)
        nav = []
        for key, label in (("home", s["nav_home"]), ("privacy", s["nav_privacy"]), ("support", s["nav_support"])):
            current = ' aria-current="page"' if key == page else ""
            nav.append('        <li><a href="%s"%s>%s</a></li>' % (rel(here, page_dir(loc, key)), current, label))
        langs = []
        for other in self.locales:
            current = ' aria-current="page"' if other is loc else ""
            name = html.escape(other["name"])
            if other["dir"] == "rtl":
                name = '<span dir="rtl">%s</span>' % name
            langs.append('        <li><a href="%s" hreflang="%s" lang="%s"%s>%s</a></li>' % (
                rel(here, page_dir(other, page)), other["hreflang"][0], other["lang"], current, name))
        return "\n".join([
            '<header class="site">',
            '  <div class="wrap">',
            '    <a class="brand" href="%s">' % rel(here, page_dir(loc, "home")),
            '      <img src="%s" width="28" height="28" alt="">' % self.icons["logo"],
            '      RawMask Studio',
            '    </a>',
            '    <div class="header-end">',
            '    <nav aria-label="%s">' % attr(plain(s["nav_label"])),
            '      <ul>',
            *nav,
            '      </ul>',
            '    </nav>',
            '    <details class="lang">',
            '      <summary>%s<span class="visually-hidden">%s </span>%s</summary>' % (
                GLOBE, html.escape(plain(s["lang_label"])), html.escape(loc["name"])),
            '      <ul>',
            *langs,
            '      </ul>',
            '    </details>',
            '    </div>',
            '  </div>',
            '</header>'])

    def badge(self, loc, page, height, indent):
        s = self.strings[loc["id"]]["common"]
        width, src = badge_img(loc, page_dir(loc, page), height)
        return '%s<a class="badge" href="%s"><img src="%s" width="%s" height="%d" alt="%s"></a>' % (
            indent, attr(APP_STORE_URL), src, ("%.1f" % width).rstrip("0").rstrip("."), height, attr(plain(s["badge_alt"])))

    def footer(self, loc, page):
        s = self.strings[loc["id"]]["common"]
        here = page_dir(loc, page)
        links = []
        for key, label in (("home", s["nav_home"]), ("privacy", s["nav_privacy"]), ("support", s["nav_support"])):
            if key != page:
                links.append('      <li><a href="%s">%s</a></li>' % (rel(here, page_dir(loc, key)), label))
        parts = ['<footer class="site">', '  <div class="wrap">', '    <span>%s</span>' % s["copyright"]]
        if page != "home":
            parts.append(self.badge(loc, page, 40, "    "))
        parts += ['    <ul>', *links, '    </ul>', '  </div>', '</footer>', '</body>', '</html>', '']
        return "\n".join(parts)

    def links(self, loc, page):
        here = page_dir(loc, page)
        en = self.en_locale()
        return {"support_url": rel(here, page_dir(loc, "support")),
                "privacy_url": rel(here, page_dir(loc, "privacy")),
                "english_url": rel(here, page_dir(en, page))}

    def en_locale(self):
        return next(l for l in self.all_locales if l["id"] == "en")

    def blocks(self, blocks, links, indent):
        out = []
        for block in blocks:
            (kind, value), = block.items()
            if kind == "p":
                out.append("%s<p>%s</p>" % (indent, fill(value, links)))
            elif kind == "h3":
                out.append("%s<h3>%s</h3>" % (indent, fill(value, links)))
            elif kind == "ul":
                out.append("%s<ul>" % indent)
                out += ["%s  <li>%s</li>" % (indent, fill(item, links)) for item in value]
                out.append("%s</ul>" % indent)
        return out

    def translation_notice(self, loc, links):
        if loc["id"] == "en":
            return []
        return ['  <p class="note">%s</p>' % fill(self.strings[loc["id"]]["common"]["translation_notice"], links)]

    # ------------------------------------------------------------------ pages

    def render_home(self, loc):
        s = self.strings[loc["id"]]["home"]
        links = self.links(loc, "home")
        store = self.store(loc)
        here = page_dir(loc, "home")
        description = plain(s["description"])
        if not store:
            raise SystemExit("no store copy for %s in src/store/metadata.json" % loc["id"])
        lead = html.escape(store["promotionalText"].strip())
        title = "RawMask Studio - %s" % store["subtitle"].strip()
        out = [self.head(loc, "home", title, description), self.header(loc, "home"), "",
               '<main class="wrap">',
               '<section class="hero">',
               '  <p class="eyebrow">%s</p>' % s["eyebrow"],
               '  <h1>RawMask Studio</h1>',
               '  <p class="lead">%s</p>' % lead,
               '  <div class="actions">',
               self.badge(loc, "home", 44, "    "),
               '    <a class="button secondary" href="%s">%s</a>' % (links["support_url"], s["btn_support"]),
               '    <a class="button secondary" href="%s">%s</a>' % (links["privacy_url"], s["btn_privacy"]),
               '  </div>']
        if loc["id"] != "en":
            out.append('  <p class="ui-note">%s</p>' % html.escape(self.ui_notes[loc["id"]]))
        devices = self.device_panels(loc, here)
        out += ['</section>', '<section class="showcase">',
                '  <h2 id="screenshots">%s</h2>' % s["screenshots_heading"]]
        if devices:
            # A radio button per device switches the panels in CSS; the site allows no scripts.
            # Each radio covers its own label, so focusing it never scrolls the page.
            out.append('  <div class="device-tabs" role="radiogroup" aria-labelledby="screenshots">')
            out += ['    <label id="tab-%s"><input type="radio" name="device" id="device-%s"%s>%s</label>' % (
                d, d, " checked" if d == "iphone" else "", name)
                for d, name in (("iphone", "iPhone"), ("ipad", "iPad"), ("mac", "Mac"))]
            out += ['  </div>',
                    '  <ul class="shots device-iphone" tabindex="0" aria-labelledby="screenshots tab-iphone">']
        else:
            out.append('  <ul class="shots" tabindex="0" aria-labelledby="screenshots">')
        folder = "en" if loc["id"] == "en" else loc["slug"]
        for i, name in enumerate(SHOTS):
            base = rel(here, "assets/screenshots/%s/%s" % (folder, name), is_dir=False)
            w, h = screenshot_size(folder, name, 300)
            cap_title, cap_sub = self.caption(loc, i)
            lazy = "" if i < 2 else ' loading="lazy"'
            out.append('    <li><img src="%s-300.webp" srcset="%s-300.webp 300w, %s-600.webp 600w" sizes="200px" width="%d" height="%d" alt="%s"%s decoding="async"></li>' % (
                base, base, base, w, h, attr("%s %s" % (cap_title.strip(), cap_sub.strip())), lazy))
        out += ['  </ul>', *devices, '</section>']
        news = s["whats_new"]
        out += ['<section class="capabilities whats-new">',
                '  <h2 id="whats-new">%s</h2>' % news["heading"],
                '  <p>%s</p>' % news["intro"],
                '  <ul class="features sections">']
        for item in news["items"]:
            out += ['    <li>', '      <h3>%s</h3>' % item["h3"], '      <p>%s</p>' % item["p"], '    </li>']
        out += ['  </ul>', '</section>']
        out += ['<section class="capabilities">',
                '  <h2>%s</h2>' % s["features_heading"]]
        intro, sections, outro = split_description(store["description"])
        if len(sections) != len(s["store_headings"]):
            raise SystemExit("%s: store description has %d sections but store_headings has %d"
                             % (loc["id"], len(sections), len(s["store_headings"])))
        out += ['  <p>%s</p>' % "<br>\n".join(html.escape(l) for l in para) for para in intro]
        out.append('  <ul class="features sections">')
        for heading, (_, bullets) in zip(s["store_headings"], sections):
            out += ['    <li>', '      <h3>%s</h3>' % heading, '      <ul>']
            out += ['        <li>%s</li>' % html.escape(b) for b in bullets]
            out += ['      </ul>', '    </li>']
        out += ['  </ul>', '</section>', '<section class="closing">', '  <div class="closing-copy">']
        out += ['  <p class="outro">%s</p>' % "<br>\n".join(html.escape(l) for l in para) for para in outro]
        out += ['  </div>', '  <div class="callout">',
                '    <p>%s</p>' % s["requirements"],
                '    <p class="muted">%s</p>' % fill(s["help"], links),
                '  </div>', '</section>', '</main>', '', self.footer(loc, "home")]
        return "\n".join(out)

    def render_support(self, loc):
        s = self.strings[loc["id"]]["support"]
        links = self.links(loc, "support")
        out = [self.head(loc, "support", plain(s["title"]), plain(s["description"])), self.header(loc, "support"), "",
               '<main class="wrap document">',
               '  <h1>%s</h1>' % s["h1"],
               '  <p class="meta">%s</p>' % s["meta"]]
        out += self.translation_notice(loc, links)
        out += ['', '  <div class="callout" id="contact">',
                '    <p>%s</p>' % s["contact"],
                '    <p>%s</p>' % s["contact_note"]]
        if loc["id"] != "en":
            note = self.ui_notes[loc["id"]]
            gap = "" if note.endswith("\u3002") else " "  # no space after an ideographic full stop
            out.append('    <p class="muted">%s%s%s</p>' % (html.escape(note), gap, s["ui_labels_note"]))
        out += ['  </div>', '', '  <h2 id="faq">%s</h2>' % s["faq_heading"], '  <div class="faq">']
        for i, item in enumerate(s["faq"]):
            if i:
                out.append('')
            out += ['    <section>', '      <h3>%s</h3>' % item["q"]]
            out += self.blocks(item["blocks"], links, "      ")
            out.append('    </section>')
        out += ['  </div>', '', '  <h2>%s</h2>' % s["still_heading"], '  <p>%s</p>' % s["still_text"],
                '</main>', '', self.footer(loc, "support")]
        return "\n".join(out)

    def render_privacy(self, loc):
        s = self.strings[loc["id"]]["privacy"]
        links = self.links(loc, "privacy")
        out = [self.head(loc, "privacy", plain(s["title"]), plain(s["description"])), self.header(loc, "privacy"), "",
               '<main class="wrap document">',
               '  <h1>%s</h1>' % s["h1"],
               '  <p class="meta">%s</p>' % s["meta"]]
        out += self.translation_notice(loc, links)
        out += ['', '  <div class="callout">', '    <p>%s</p>' % s["summary"], '  </div>']
        for section in s["sections"]:
            out += ['', '  <h2 id="%s">%s</h2>' % (section["id"], section["h2"])]
            out += self.blocks(section["blocks"], links, "  ")
        out += ['</main>', '', self.footer(loc, "privacy")]
        return "\n".join(out)

    def render(self, loc, page):
        return {"home": self.render_home, "support": self.render_support, "privacy": self.render_privacy}[page](loc)

    def write_all(self, out_root=ROOT, only=None):
        written = []
        for loc in self.locales:
            if only and loc["id"] != only:
                continue
            for page in PAGES:
                path = os.path.join(out_root, page_dir(loc, page), "index.html")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.render(loc, page))
                written.append(path)
        return written

    def sitemap(self):
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
        for page in PAGES:
            for loc in self.locales:
                out.append('  <url>')
                out.append('    <loc>%s</loc>' % page_url(loc, page))
                for other in self.locales:
                    for code in other["hreflang"]:
                        out.append('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (code, page_url(other, page)))
                out.append('  </url>')
        out.append('</urlset>')
        return "\n".join(out) + "\n"


EN_CAPTIONS = [
    ("Edit only what you select.", "Masks for RAW photos on iPhone."),
    ("Let it find the subject.", "On-device detection masks cars, people and animals for you."),
    ("Draw a mask any way you like.", "Radial, linear, brush or rectangle. Then add, subtract or feather."),
    ("Tune light and color inside it.", "Each mask gets its own exposure, color, detail and focus."),
    ("Save to Photos. Revert anytime.", "Edits stay reversible, and nothing leaves your iPhone."),
]

# Screenshot names and how many go in each row (rows of one height on wide screens).
DEVICE_SHOTS = {
    "ipad": (["01-select", "02-palettes", "03-masks", "04-style", "05-frame", "06-save", "07-options"], [3, 4]),
    "mac": (["01-select", "02-detect", "03-frame", "04-save", "05-steps", "06-detection"], [3, 3]),
}
EN_DEVICE_CAPTIONS = {
    "ipad": [
        ("Edit only what you select.", "Masks for RAW photos on iPad."),
        ("Every tool floats over your photo.", "Drag the palettes anywhere, in either orientation."),
        ("Draw a mask any way you like.", "Radial, linear, brush or rectangle. Then add, subtract or feather."),
        ("Give it a look.", "Film, black and white, vintage, noir, grunge and retro styles."),
        ("Crop, straighten and frame.", "Eight borders, from a thin line to a film edge."),
        ("Save to Photos. Revert anytime.", "Edits stay reversible, and nothing leaves your iPad."),
        ("Make the editor yours.", "Save presets, and keep only the steps you use, in your order."),
    ],
    "mac": [
        ("Edit only what you select.", "Masks for RAW photos on Mac."),
        ("Let it find the subject.", "On-device detection masks cars, people and animals for you."),
        ("Crop, straighten and frame.", "Eight borders, from a thin line to a film edge."),
        ("Save to Photos. Revert anytime.", "Edits stay reversible, and nothing leaves your Mac."),
        ("Make the editor yours.", "Save presets, and keep only the steps you use, in your order."),
        ("Tune what it detects.", "Set confidence, mask edge and object count. It all runs on your Mac."),
    ],
}


def device_widths(folder, device, name):
    """The 1x and 2x widths make_screenshots.py wrote: 300/600 portrait, 480/960 landscape."""
    for widths in ((300, 600), (480, 960)):
        if os.path.exists(os.path.join(ROOT, "assets", "screenshots", folder, device, "%s-%d.webp" % (name, widths[0]))):
            return widths
    raise SystemExit("missing screenshot %s/%s/%s" % (folder, device, name))

_SIZES = {}


def screenshot_size(folder, name, width):
    key = (folder, name, width)
    if key not in _SIZES:
        path = os.path.join(ROOT, "assets", "screenshots", folder, "%s-%d.webp" % (name, width))
        with open(path, "rb") as f:
            data = f.read(64)
        _SIZES[key] = webp_size(data)
    return _SIZES[key]


def webp_size(data):
    """Width and height from a WebP header (VP8, VP8L or VP8X)."""
    chunk = data[12:16]
    if chunk == b"VP8 ":
        return (int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF)
    if chunk == b"VP8L":
        b = int.from_bytes(data[21:25], "little")
        return ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X":
        return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
    raise ValueError("not a WebP file")


BULLET = re.compile(r"^\s*(?:[-*\u2022\u25CF\u25AA\u30FB\u00B7])\s+")


def split_description(text):
    """Split App Store description text into intro paragraphs, headed bullet
    sections and closing paragraphs. Each paragraph is a list of lines; a
    section is a heading line followed only by bullet lines."""
    intro, sections, outro = [], [], []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in para.split("\n") if l.strip()]
        if len(lines) > 1 and not BULLET.match(lines[0]) and all(BULLET.match(l) for l in lines[1:]):
            sections.append((lines[0], [BULLET.sub("", l).strip() for l in lines[1:]]))
        elif any(BULLET.match(l) for l in lines):
            raise SystemExit("unexpected description paragraph: %r" % para[:80])
        else:
            (outro if sections else intro).append(lines)
    return intro, sections, outro


# ---------------------------------------------------------------- site check

def check_site(allow_missing=False):
    """Verify the built site: files, links, hreflang, lang/dir, canonical, sitemap."""
    from html.parser import HTMLParser

    class Page(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.html_attrs, self.links, self.alternates, self.canonical, self.hrefs, self.srcs = {}, [], [], None, [], []
            self.metas, self.ids, self.text = {}, set(), []
            self.in_style = False

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if "id" in a:
                self.ids.add(a["id"])
            if tag == "html":
                self.html_attrs = a
            elif tag == "link" and a.get("rel") == "alternate":
                self.alternates.append((a.get("hreflang"), a.get("href")))
            elif tag == "link" and a.get("rel") == "canonical":
                self.canonical = a.get("href")
            elif tag == "a" and "href" in a:
                self.hrefs.append(a["href"])
            elif tag == "img":
                self.srcs.append(a.get("src"))
                for part in (a.get("srcset") or "").split(","):
                    if part.strip():
                        self.srcs.append(part.strip().split()[0])
            elif tag == "meta":
                key = a.get("name") or a.get("property") or a.get("http-equiv")
                if key:
                    self.metas[key] = a.get("content")
            elif tag == "style":
                self.in_style = True

        def handle_endtag(self, tag):
            if tag == "style":
                self.in_style = False

        def handle_data(self, data):
            if not self.in_style:
                self.text.append(data)

    site = Site(allow_missing=allow_missing)
    problems = []
    expected_alternates = None
    parsed = {}
    for loc in site.locales:
        for page in PAGES:
            rel_dir = page_dir(loc, page)
            path = os.path.join(ROOT, rel_dir, "index.html")
            if not os.path.exists(path):
                problems.append("missing page %s" % path)
                continue
            p = Page()
            with open(path, encoding="utf-8") as f:
                source = f.read()
            p.feed(source)
            parsed[(loc["id"], page)] = p
            where = "/" + rel_dir
            if p.html_attrs.get("lang") != loc["lang"]:
                problems.append("%s: html lang %r, expected %r" % (where, p.html_attrs.get("lang"), loc["lang"]))
            if (p.html_attrs.get("dir") == "rtl") != (loc["dir"] == "rtl"):
                problems.append("%s: dir attribute wrong" % where)
            if p.canonical != page_url(loc, page):
                problems.append("%s: canonical %r" % (where, p.canonical))
            if p.metas.get("og:url") != page_url(loc, page):
                problems.append("%s: og:url wrong" % where)
            if p.metas.get("apple-itunes-app") != "app-id=%s" % APP_ID:
                problems.append("%s: Smart App Banner missing" % where)
            if p.metas.get("Content-Security-Policy") != CSP:
                problems.append("%s: CSP differs" % where)
            for key in ("description", "og:title", "og:description", "og:locale"):
                if not p.metas.get(key):
                    problems.append("%s: meta %s missing" % (where, key))
            alts = sorted(p.alternates)
            want = sorted((code, page_url(other, page)) for other in site.locales for code in other["hreflang"])
            if alts != want:
                problems.append("%s: hreflang set differs from expected (%d vs %d)" % (where, len(alts), len(want)))
            if len({code for code, _ in alts}) != len(alts):
                problems.append("%s: duplicate hreflang codes" % where)
            if ("x-default", page_url(site.en_locale(), page)) not in alts:
                problems.append("%s: x-default missing" % where)
            if not any(h == APP_STORE_URL for h in p.hrefs):
                problems.append("%s: no App Store link" % where)
            for href in p.hrefs:
                if href.startswith(("http://", "https://", "mailto:")):
                    continue
                target, _, frag = href.partition("#")
                if not target:
                    if frag and frag not in p.ids:
                        problems.append("%s: anchor #%s not found" % (where, frag))
                    continue
                resolved = posixpath.normpath(posixpath.join("/" + rel_dir, target))
                file_path = os.path.join(ROOT, resolved.lstrip("/"), "index.html") if href.endswith("/") else os.path.join(ROOT, resolved.lstrip("/"))
                if not os.path.exists(file_path):
                    problems.append("%s: broken link %s" % (where, href))
            for src in p.srcs:
                if src.startswith("data:"):
                    continue
                resolved = posixpath.normpath(posixpath.join("/" + rel_dir, src))
                if not os.path.exists(os.path.join(ROOT, resolved.lstrip("/"))):
                    problems.append("%s: missing image %s" % (where, src))
            lang_links = [h for h in p.hrefs]
            for other in site.locales:
                if rel(rel_dir, page_dir(other, page)) not in lang_links:
                    problems.append("%s: language switcher has no link to %s" % (where, other["id"]))
            text = "".join(p.text)
            bad = FORBIDDEN.findall(text) + FORBIDDEN.findall(" ".join(v or "" for v in p.metas.values()))
            if bad:
                problems.append("%s: forbidden characters %s" % (where, sorted({"U+%04X" % ord(c) for c in bad})))
    sitemap_path = os.path.join(ROOT, "sitemap.xml")
    if not os.path.exists(sitemap_path):
        problems.append("sitemap.xml missing")
    else:
        import xml.etree.ElementTree as ET
        tree = ET.parse(sitemap_path)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
        urls = tree.getroot().findall("s:url", ns)
        locs = {u.find("s:loc", ns).text for u in urls}
        want = {page_url(l, p) for l in site.locales for p in PAGES}
        if locs != want:
            problems.append("sitemap: %d urls, expected %d" % (len(locs), len(want)))
        for u in urls:
            if len(u.findall("x:link", ns)) != sum(len(l["hreflang"]) for l in site.locales):
                problems.append("sitemap: wrong alternate count for %s" % u.find("s:loc", ns).text)
                break
    return problems


def main(argv):
    if argv[:1] == ["--check-strings"]:
        errors, warnings = validate_strings(argv[1])
        for w in warnings:
            print("warning:", w)
        for e in errors:
            print("error:", e)
        print("%s: %d error(s), %d warning(s)" % (argv[1], len(errors), len(warnings)))
        return 1 if errors else 0
    if argv[:1] == ["--preview"]:
        site = Site(only={"en", argv[1]})
        files = site.write_all(out_root=argv[2], only=argv[1])
        print("\n".join(files))
        return 0
    if argv[:1] == ["--check-site"]:
        problems = check_site(allow_missing="--allow-missing" in argv)
        print("\n".join(problems) if problems else "site check passed")
        return 1 if problems else 0
    site = Site(allow_missing="--allow-missing" in argv)
    failed = False
    for loc in site.locales:
        if loc["id"] != "en":
            errors, _ = validate_strings(loc["id"])
            if errors:
                failed = True
                print("%s has %d string error(s); run --check-strings %s" % (loc["id"], len(errors), loc["id"]))
    if failed:
        return 1
    files = site.write_all()
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(site.sitemap())
    print("wrote %d pages for %d languages and sitemap.xml" % (len(files), len(site.locales)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
