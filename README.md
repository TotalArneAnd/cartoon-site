# cartoon-site

Static site for the cartoon flows. `build.py` turns `content/cartoons.json` into plain HTML in `public/`. No framework, no server, no third-party requests (system fonts only).

## What you get

- `/` shows the latest cartoon. `/c/<slug>/` is one page per cartoon, with left/right arrows (also arrow keys and swipe) to older and newer ones.
- The caption is real text on the page, followed by "What actually happened" (the blurb) and a source link.
- `/archive/` lists every cartoon by month. `/about/` and `/privacy/` come from `pages/`.
- Also generated: `feed.xml`, `sitemap.xml`, `robots.txt`, `404.html`, social preview tags, structured data, and `ads.txt` once AdSense is configured. The feed and sitemap need `site_url`.
- Images are converted to WebP (1400 px max) with 480 px thumbnails if Pillow is installed; otherwise the PNGs are copied.
- Light and dark mode, responsive down to phones, visible keyboard focus.
- English and Danish text (`"language": "da"` in `site.json`). Danish `about`/`privacy` text is not written yet; the English text is used until you add `pages/about.da.html` and `pages/privacy.da.html`.

## Try it locally

```
pip install -r requirements.txt           # optional, enables WebP
python3 build.py --content sample         # builds 5 sample cartoons into public/
python3 -m http.server -d public 8000     # open http://localhost:8000
```

`python3 build.py` (no flag) builds your real `content/`. It starts empty and shows a "first cartoon is on its way" page.

## Before going live

1. Edit `site.json`: `site_name`, `tagline`, `site_url` (for example `https://example.com`, no trailing slash), `owner_name`, `contact_email`, `hosting_provider`. The build warns while the placeholder name and email are still there.
2. Read and edit `pages/about.en.html` and `pages/privacy.en.html`. They describe how the pipeline works today (AI-written ideas, captions and summaries; a person picks and approves the drawings; no analytics, no own cookies). If you add analytics or anything else that sets cookies, update the privacy page. I am not a lawyer; have the text checked if you need certainty.
3. Pages use root-relative links (`/c/...`), so the site must be served at the root of a domain, not at a sub-path such as `user.github.io/repo/`.

## Hosting (Cloudflare Pages example)

Create a Pages project from the git repo with:

- Build command: `pip install -r requirements.txt && python3 build.py`
- Output directory: `public`
- If the build cannot install Pillow, `python3 build.py` alone also works (images are then copied as PNG). If the build uses too old a Python, set a `PYTHON_VERSION` environment variable (check Cloudflare's docs for the supported values). The script needs Python 3.9 or newer.

The generated `_headers` file makes images cache for a year. Netlify understands the same file. Other hosts: run `python3 build.py` locally and upload `public/`.

## Connecting it to cartoon.py

1. Clone this repo to the path set as `publish.local_path` in `cartoon-flows/flows/absurd-en.yaml`.
2. Leave `publish.build_command` as `null`; the host builds on every push.
3. `cartoon.py publish-next` then writes `content/img/<slug>.png` and appends to `content/cartoons.json`. Each entry has `slug`, `date`, `title`, `caption`, `blurb`, `alt_text`, `image`, `source_name`, `source_url` and `panel_count`. Entries that miss a field, or point to a missing image, are skipped with a warning.

## AdSense

Set `adsense_client` (`ca-pub-...`) and `adsense_slots.below_story` (an ad unit id) in `site.json`. The build then adds the AdSense script to every page, one ad unit below the story, an `ads.txt` file, and an advertising section on the privacy page. The ad unit sits well away from the arrows, with an "Advertisement" label, to avoid accidental clicks.

Visitors in the EEA, UK and Switzerland need a consent message from a Google-certified consent tool before personalised ads are shown. The simplest route is Google's own consent message in your AdSense account (Privacy & messaging). This site has no cookie banner of its own, because it sets no cookies. Check Google's current requirements when you apply.

## Layout of the folder

```
build.py            the generator
site.json           names, URL, language, AdSense ids
content/            cartoons.json + img/   (written by cartoon.py)
pages/              about.en.html, privacy.en.html (edit these)
static/             style.css, nav.js, favicon.svg
sample/             five fake cartoons for previewing
public/             build output (not committed)
```

## Known limits

- The cartoon number ("No. 12") is the cartoon's position by date. Deleting an old cartoon renumbers the later ones.
- No search, comments or pagination in the archive; with hundreds of cartoons the archive page gets long.
- The visual design was checked in headless Chromium (desktop, phone, dark mode) with sample drawings, not with real cartoons from the image model.

