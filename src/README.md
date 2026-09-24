# Shared website design

The selected Midnight design is shared by all 141 pages across 47 languages.
`src/theme.css` holds the colors, typography, header, footer and responsive site
navigation. `src/landing.css` styles landing pages, including reflections and
feature columns. `src/document.css` styles privacy and support pages with a
reading column, uppercase section headings, callouts and connected logo bullets.
`src/build.py` applies these styles automatically when building the site.

Run these commands from the website repository root:

```sh
# Validate and update support and privacy pages in two sample languages.
python3 src/redesign_landings.py --locales it ar-SA --pages support privacy

# Validate every page without writing files.
python3 src/redesign_landings.py --check

# Apply the design to all three page types in every language.
python3 src/redesign_landings.py

# Verify site links, language metadata, images and sitemap.
python3 src/build.py --check-site

# Serve the local result.
python3 -m http.server 4387 --bind 127.0.0.1
```

Use locale IDs from `src/locales.json`, such as `ar-SA`, `de-DE`, or `zh-Hans`.
Their URL folders can differ: Arabic is available at `/ar/`.

The conversion checks every selected page before writing any of them. It refuses
to overwrite a page if its text, image attributes, links, document language or
metadata would change. The browser theme color is allowed to match the new design.
The script defaults to all page types. Use `--pages home` to update only landing
pages, or `--pages support privacy` to update just the document pages. Repeated
runs produce identical files. It does not publish or change translations or images.

Normal `python3 src/build.py` builds also use the shared design, so a later content
update will retain it. Run the preservation checks with:

```sh
python3 -m unittest discover -s src -p 'test_redesign_landings.py'
```
