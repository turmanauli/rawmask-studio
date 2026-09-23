"""Make web-sized WebP screenshots from the App Store PNGs.

Usage: python3 src/make_screenshots.py
Writes assets/screenshots/<folder>/<name>-300.webp and -600.webp for every
locale in src/locales.json ("en" is the folder for the English site).
Needs Pillow with WebP support.
"""
import json
import os
from concurrent.futures import ProcessPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = "/Users/turmanauli/Documents/dev/rawmask-archives"
EN_SOURCE = ARCHIVE + "/appstore-1.1.0-screenshots/iphone-6.9-1320x2868"
L10N_SOURCE = ARCHIVE + "/appstore-1.1.0-l10n/screenshots"
NAMES = ["01-select", "02-detect", "03-masks", "04-adjust", "05-save"]
WIDTHS = (300, 600)


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


def convert(job):
    src, out, name = job
    os.makedirs(out, exist_ok=True)
    image = Image.open(src).convert("RGB")
    for width in WIDTHS:
        height = round(image.height * width / image.width)
        image.resize((width, height), Image.LANCZOS).save(
            os.path.join(out, "%s-%d.webp" % (name, width)), "WEBP", quality=78, method=6)
    return src


if __name__ == "__main__":
    with ProcessPoolExecutor(10) as pool:
        done = list(pool.map(convert, jobs()))
    print("converted", len(done), "screenshots")
