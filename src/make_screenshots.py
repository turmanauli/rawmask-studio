"""Make web-sized WebP screenshots from the App Store PNGs.

Usage: python3 src/make_screenshots.py
Writes assets/screenshots/<folder>/<name>-300.webp and -600.webp for every
locale in src/locales.json ("en" is the folder for the English site).

Usage: python3 src/make_screenshots.py devices ID [ID ...]
Writes the iPad and Mac screenshots for the given locale IDs to
assets/screenshots/<folder>/ipad/ and .../mac/. A language shows the
iPhone, iPad and Mac switch once these files exist; every language except
English also needs its captions in src/store/device_captions.json.
Needs Pillow with WebP support.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = "/Users/turmanauli/Documents/dev/rawmask-archives"
EN_SOURCE = ARCHIVE + "/appstore-1.1.0-screenshots/iphone-6.9-1320x2868"
L10N_SOURCE = ARCHIVE + "/appstore-1.1.0-l10n/screenshots"
NAMES = ["01-select", "02-detect", "03-masks", "04-adjust", "05-save"]
WIDTHS = (300, 600)
# 1.2.0 renders, one folder per App Store locale (en-US for the English site).
DEVICE_SOURCE = "/Users/turmanauli/Documents/dev/Lumina/dist/appstore/%s/out-l10n"
DEVICE_NAMES = {
    "ipad": ["01-select", "02-palettes", "03-masks", "04-style", "05-frame", "06-save", "07-options"],
    "mac": ["01-select", "02-detect", "03-frame", "04-save", "05-steps", "06-detection"],
}
# 1x and 2x widths; landscape shots are wider on the page, so they get more pixels.
DEVICE_WIDTHS = {"portrait": (300, 600), "landscape": (480, 960)}


def jobs():
    with open(os.path.join(ROOT, "src", "locales.json"), encoding="utf-8") as f:
        locales = json.load(f)["locales"]
    for loc in locales:
        if loc["id"] == "en":
            src, folder = EN_SOURCE, "en"
        else:
            src, folder = os.path.join(L10N_SOURCE, loc["id"]), loc["slug"]
        for name in NAMES:
            yield os.path.join(src, name + ".png"), os.path.join(ROOT, "assets", "screenshots", folder), name


def device_jobs(ids):
    with open(os.path.join(ROOT, "src", "locales.json"), encoding="utf-8") as f:
        locales = {loc["id"]: loc for loc in json.load(f)["locales"]}
    for loc_id in ids:
        loc = locales[loc_id]
        store_id, folder = ("en-US", "en") if loc_id == "en" else (loc_id, loc["slug"])
        for device, names in DEVICE_NAMES.items():
            src = os.path.join(DEVICE_SOURCE % device, store_id)
            for name in names:
                yield os.path.join(src, name + ".png"), os.path.join(ROOT, "assets", "screenshots", folder, device), name


def convert(job):
    src, out, name = job
    os.makedirs(out, exist_ok=True)
    image = Image.open(src).convert("RGB")
    widths = WIDTHS
    if os.path.basename(os.path.dirname(out)) != "screenshots":  # an ipad or mac folder
        orientation = "landscape" if image.width > image.height else "portrait"
        widths = DEVICE_WIDTHS[orientation]
        # Remove the other orientation's files so build.py never picks up a stale shot.
        for other in DEVICE_WIDTHS[{"landscape": "portrait", "portrait": "landscape"}[orientation]]:
            stale = os.path.join(out, "%s-%d.webp" % (name, other))
            if os.path.exists(stale):
                os.remove(stale)
    for width in widths:
        height = round(image.height * width / image.width)
        image.resize((width, height), Image.LANCZOS).save(
            os.path.join(out, "%s-%d.webp" % (name, width)), "WEBP", quality=78, method=6)
    return src


if __name__ == "__main__":
    todo = list(device_jobs(sys.argv[2:])) if sys.argv[1:2] == ["devices"] else list(jobs())
    with ProcessPoolExecutor(10) as pool:
        done = list(pool.map(convert, todo))
    print("converted", len(done), "screenshots")
