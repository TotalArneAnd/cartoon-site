#!/usr/bin/env python3
"""
build.py - turn content/cartoons.json into a static site in public/.

    python3 build.py                       # build from content/ into public/
    python3 build.py --content sample      # preview with the bundled sample cartoons
    python3 -m http.server -d public 8000  # then open http://localhost:8000

Only Python's standard library is required. If Pillow is installed, images are
converted to WebP and thumbnails are made; without it the PNG files are copied.

Pages produced:
    /                    the latest cartoon (canonical link points at its own page)
    /c/<slug>/           one page per cartoon, with prev/next arrows
    /archive/            every cartoon, grouped by month
    /about/ /privacy/    from pages/*.html (edit these)
    /feed.xml /sitemap.xml /robots.txt /ads.txt /404.html /_headers   (feed and sitemap need site_url)
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # optional
    Image = None

ROOT = Path(__file__).resolve().parent
esc = html.escape

STRINGS = {
    "en": {
        "previous": "Previous", "next": "Next", "archive": "Archive", "about": "About",
        "privacy": "Privacy", "story": "What actually happened", "source": "Source",
        "disclosure": "Drawn with AI, chosen and approved by a person.",
        "how": "How these are made", "advert": "Advertisement",
        "empty_title": "The first cartoon is on its way",
        "empty_text": "Nothing has been published yet. Check back soon.",
        "archive_title": "All cartoons", "archive_empty": "No cartoons yet.",
        "not_found": "Page not found",
        "not_found_text": "This page does not exist. The latest cartoon is on the front page.",
        "home": "Go to the latest cartoon", "no": "No.", "rss": "RSS feed",
        "skip": "Skip to content", "from_archive": "Cartoon",
    },
    "da": {
        "previous": "Forrige", "next": "Næste", "archive": "Arkiv", "about": "Om",
        "privacy": "Privatliv", "story": "Hvad skete der egentlig", "source": "Kilde",
        "disclosure": "Tegnet med AI, udvalgt og godkendt af et menneske.",
        "how": "Sådan laves de", "advert": "Annonce",
        "empty_title": "Den første tegning er på vej",
        "empty_text": "Der er ikke udgivet noget endnu. Kig forbi igen snart.",
        "archive_title": "Alle tegninger", "archive_empty": "Ingen tegninger endnu.",
        "not_found": "Siden findes ikke",
        "not_found_text": "Siden findes ikke. Den nyeste tegning står på forsiden.",
        "home": "Gå til den nyeste tegning", "no": "Nr.", "rss": "RSS-feed",
        "skip": "Gå til indhold", "from_archive": "Tegning",
    },
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "da": ["januar", "februar", "marts", "april", "maj", "juni", "juli",
           "august", "september", "oktober", "november", "december"],
}
ADS_SECTION = {
    "en": ('<h2>Advertising</h2>\n<p>This site shows ads served by Google AdSense. Google and its partners may '
           'use cookies and similar technologies to show and measure ads. Visitors in the EEA, the UK and '
           'Switzerland are asked for consent before personalised ads are shown. You can read how Google uses '
           'data from sites that use its services at <a href="https://policies.google.com/technologies/partner-sites">'
           'policies.google.com/technologies/partner-sites</a> and manage your ad settings at '
           '<a href="https://adssettings.google.com">adssettings.google.com</a>.</p>'),
    "da": ('<h2>Annoncer</h2>\n<p>Dette websted viser annoncer fra Google AdSense. Google og dets partnere kan bruge '
           'cookies og lignende teknologier til at vise og måle annoncer. Besøgende i EØS, Storbritannien og '
           'Schweiz bliver bedt om samtykke, før personlige annoncer vises. Du kan læse, hvordan Google bruger '
           'data fra websteder, der bruger Googles tjenester, på <a href="https://policies.google.com/technologies/partner-sites">'
           'policies.google.com/technologies/partner-sites</a>, og styre dine annonceindstillinger på '
           '<a href="https://adssettings.google.com">adssettings.google.com</a>.</p>'),
}

warnings: list[str] = []


# --------------------------------------------------------------------------- helpers

def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"warning: {msg}", file=sys.stderr)


def typo(text: str, lang: str) -> str:
    """Typographic apostrophes and quotes for English text."""
    if lang != "en":
        return text
    text = re.sub(r"(?<=\w)'(?=\w)", "\u2019", text)
    text = re.sub(r'(^|[\s(\[])"', "\\1\u201c", text)
    text = text.replace('"', "\u201d")
    text = re.sub(r"(^|[\s(\[])'", "\\1\u2018", text)
    return text.replace("'", "\u2019")


def fmt_date(moment: dt.datetime, lang: str) -> str:
    month = MONTHS[lang][moment.month - 1]
    return f"{moment.day}. {month} {moment.year}" if lang == "da" else f"{moment.day} {month} {moment.year}"


def first_sentence(text: str) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return match.group(1) if match else text.strip()


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def json_ld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


# --------------------------------------------------------------------------- data

def load_site(path: Path) -> dict:
    site = json.loads(path.read_text(encoding="utf-8"))
    site.setdefault("language", "en")
    site.setdefault("adsense_slots", {})
    site["site_url"] = site.get("site_url", "").rstrip("/")
    if site["language"] not in STRINGS:
        sys.exit(f"Unsupported language {site['language']!r}; add it to STRINGS and MONTHS.")
    return site


REQUIRED = ("slug", "date", "title", "caption", "blurb", "alt_text", "image", "source_name", "source_url")


def load_entries(content: Path, lang: str) -> list[dict]:
    try:
        raw = json.loads((content / "cartoons.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        warn(f"{content / 'cartoons.json'} not found; building an empty site")
        return []
    entries, seen = [], set()
    for entry in raw:
        missing = [k for k in REQUIRED if not entry.get(k)]
        if missing:
            warn(f"skipping entry {entry.get('slug', '?')}: missing {', '.join(missing)}")
            continue
        if entry["slug"] in seen or not re.fullmatch(r"[a-z0-9-]+", entry["slug"]):
            warn(f"skipping entry with duplicate or invalid slug {entry['slug']!r}")
            continue
        seen.add(entry["slug"])
        try:
            entry["_dt"] = dt.datetime.fromisoformat(entry["date"])
        except ValueError:
            warn(f"skipping {entry['slug']}: bad date {entry['date']!r}")
            continue
        for key in ("title", "caption", "blurb", "alt_text"):
            entry[key] = typo(entry[key], lang)
        entries.append(entry)
    entries.sort(key=lambda e: e["_dt"])
    return entries


def process_images(entries: list[dict], content: Path, out: Path) -> list[dict]:
    """Make web images. Adds _img, _thumb, _w, _h to each entry; drops entries with no image."""
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    kept = []
    for entry in entries:
        src = content / entry["image"]
        if not src.exists():
            warn(f"skipping {entry['slug']}: image {src} not found")
            continue
        slug = entry["slug"]
        if Image is None:
            ext = src.suffix.lower() or ".png"
            shutil.copyfile(src, img_dir / f"{slug}{ext}")
            entry.update(_img=f"/img/{slug}{ext}", _thumb=f"/img/{slug}{ext}", _w=None, _h=None)
        else:
            full, thumb = img_dir / f"{slug}.webp", img_dir / f"{slug}-t.webp"
            with Image.open(src) as im:
                im.load()
                width, height = im.size
                if not (full.exists() and thumb.exists()
                        and full.stat().st_mtime >= src.stat().st_mtime):
                    rgb = im.convert("RGB")
                    if width > 1400:
                        rgb = rgb.resize((1400, round(height * 1400 / width)), Image.LANCZOS)
                    rgb.save(full, "WEBP", quality=85, method=4)
                    small = rgb.copy()
                    small.thumbnail((480, 480))
                    small.save(thumb, "WEBP", quality=80, method=4)
                with Image.open(full) as done:
                    width, height = done.size
            entry.update(_img=f"/img/{slug}.webp", _thumb=f"/img/{slug}-t.webp", _w=width, _h=height)
        kept.append(entry)
    return kept


# --------------------------------------------------------------------------- page shell

def ad_block(site: dict, S: dict, slot_key: str) -> str:
    client, slot = site.get("adsense_client"), site["adsense_slots"].get(slot_key)
    if not (client and slot):
        return ""
    return (f'<aside class="ad" aria-label="{esc(S["advert"])}"><p class="ad-label">{esc(S["advert"])}</p>'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{esc(client)}" '
            f'data-ad-slot="{esc(slot)}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
            f'<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></aside>')


def shell(site: dict, S: dict, *, title: str, description: str, path: str, body: str,
          canonical_path: str | None = None, og_image: str | None = None, head_extra: str = "",
          noindex: bool = False) -> str:
    lang, url = site["language"], site["site_url"]
    canon = f"{url}{canonical_path or path}" if url else None
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(description)}">',
        '<link rel="stylesheet" href="/style.css">',
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
        '<meta name="color-scheme" content="light dark">',
    ]
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    if canon:
        head.append(f'<link rel="canonical" href="{esc(canon)}">')
        head.append(f'<link rel="alternate" type="application/rss+xml" title="{esc(site["site_name"])}" href="{esc(url)}/feed.xml">')
        head += [
            f'<meta property="og:site_name" content="{esc(site["site_name"])}">',
            f'<meta property="og:title" content="{esc(title)}">',
            f'<meta property="og:description" content="{esc(description)}">',
            f'<meta property="og:url" content="{esc(canon)}">',
            '<meta property="og:type" content="website">',
            f'<meta name="twitter:card" content="{"summary_large_image" if og_image else "summary"}">',
        ]
        if og_image:
            head.append(f'<meta property="og:image" content="{esc(url + og_image)}">')
    if site.get("adsense_client"):
        head.append('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
                    f'{esc(site["adsense_client"])}" crossorigin="anonymous"></script>')
    head.append(head_extra)

    footer_links = (f'<a href="/archive/">{esc(S["archive"])}</a><a href="/about/">{esc(S["about"])}</a>'
                    f'<a href="/privacy/">{esc(S["privacy"])}</a>'
                    + (f'<a href="/feed.xml">{esc(S["rss"])}</a>' if url else ""))
    year = dt.date.today().year
    return f"""<!doctype html>
<html lang="{lang}">
<head>
{chr(10).join(h for h in head if h)}
</head>
<body>
<a class="skip" href="#main">{esc(S["skip"])}</a>
<header class="site-header">
  <a class="brand" href="/">{esc(site["site_name"])}</a>
  <nav class="site-nav" aria-label="Main"><a href="/archive/">{esc(S["archive"])}</a><a href="/about/">{esc(S["about"])}</a></nav>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
  <span>&copy; {year} {esc(site["site_name"])}</span>
  <nav class="footer-links" aria-label="Footer">{footer_links}</nav>
</footer>
<script src="/nav.js" defer></script>
</body>
</html>
"""


# --------------------------------------------------------------------------- pages

CHEVRON = {
    "prev": '<path d="M15 4 7 12l8 8"/>',
    "next": '<path d="m9 4 8 8-8 8"/>',
}


def arrow(kind: str, target: dict | None, S: dict) -> str:
    label = S["previous"] if kind == "prev" else S["next"]
    icon = (f'<svg class="glyph" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
            f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">{CHEVRON[kind]}</svg>')
    inner = f'{icon}<span class="arrow-label">{esc(label)}</span>'
    if target is None:
        return f'<span class="arrow arrow-{kind} is-off" aria-hidden="true">{inner}</span>'
    return (f'<a class="arrow arrow-{kind}" rel="{kind}" href="/c/{target["slug"]}/" '
            f'aria-label="{esc(label)}: {esc(target["title"])}">{inner}</a>')


def render_cartoon(site: dict, S: dict, entries: list[dict], index: int, as_home: bool) -> str:
    e = entries[index]
    older = entries[index - 1] if index > 0 else None
    newer = entries[index + 1] if index < len(entries) - 1 else None
    lang, url = site["language"], site["site_url"]
    size = f' width="{e["_w"]}" height="{e["_h"]}"' if e["_w"] else ""
    source = (f'<p class="source">{esc(S["source"])}: <a href="{esc(e["source_url"])}" '
              f'rel="noopener" target="_blank">{esc(e["source_name"])}</a></p>')
    disclosure = ""
    if site.get("show_ai_disclosure", True):
        disclosure = (f'<p class="disclosure">{esc(S["disclosure"])} '
                      f'<a href="/about/">{esc(S["how"])}</a>.</p>')
    body = f"""<article class="cartoon">
  <div class="meta"><span>{esc(S["no"])} {index + 1}</span><time datetime="{esc(e["date"])}">{esc(fmt_date(e["_dt"], lang))}</time></div>
  <h1 class="cartoon-title">{esc(e["title"])}</h1>
  <div class="stage">
    {arrow("prev", older, S)}
    <figure class="sheet"><img src="{e["_img"]}" alt="{esc(e["alt_text"])}"{size} fetchpriority="high"></figure>
    {arrow("next", newer, S)}
  </div>
  <p class="placard">{esc(e["caption"])}</p>
  <section class="story">
    <h2>{esc(S["story"])}</h2>
    <p>{esc(e["blurb"])}</p>
    {source}
  </section>
  {ad_block(site, S, "below_story")}
  {disclosure}
</article>"""
    description = clip(f'{e["caption"]} {first_sentence(e["blurb"])}', 158)
    path = "/" if as_home else f"/c/{e['slug']}/"
    head_extra = ""
    if older:
        head_extra += f'<link rel="prev" href="{esc(url)}/c/{older["slug"]}/">\n' if url else ""
    if newer:
        head_extra += f'<link rel="next" href="{esc(url)}/c/{newer["slug"]}/">\n' if url else ""
    if url:
        head_extra += '<script type="application/ld+json">' + json_ld({
            "@context": "https://schema.org", "@type": "ImageObject",
            "name": e["title"], "caption": e["caption"], "description": e["blurb"],
            "contentUrl": url + e["_img"], "thumbnailUrl": url + e["_thumb"],
            "datePublished": e["date"], "isBasedOn": e["source_url"], "inLanguage": lang,
        }) + "</script>"
    return shell(site, S, title=f'{e["title"]} | {site["site_name"]}', description=description,
                 path=path, canonical_path=f"/c/{e['slug']}/", body=body,
                 og_image=e["_img"], head_extra=head_extra)


def render_empty(site: dict, S: dict) -> str:
    body = (f'<div class="empty"><h1>{esc(S["empty_title"])}</h1><p>{esc(S["empty_text"])}</p></div>')
    return shell(site, S, title=site["site_name"], description=site.get("tagline", ""), path="/", body=body)


def render_archive(site: dict, S: dict, entries: list[dict]) -> str:
    lang = site["language"]
    if not entries:
        body = f'<h1 class="page-title">{esc(S["archive_title"])}</h1><p>{esc(S["archive_empty"])}</p>'
    else:
        parts, current = [f'<h1 class="page-title">{esc(S["archive_title"])}</h1><div class="archive">'], None
        for e in reversed(entries):
            key = (e["_dt"].year, e["_dt"].month)
            if key != current:
                if current is not None:
                    parts.append("</ul>")
                parts.append(f'<h2>{esc(MONTHS[lang][key[1] - 1].capitalize())} {key[0]}</h2><ul class="grid">')
                current = key
            parts.append(
                f'<li><a href="/c/{e["slug"]}/"><span class="thumb"><img src="{e["_thumb"]}" alt="" '
                f'loading="lazy" decoding="async"></span><span class="t">{esc(e["title"])}</span>'
                f'<span class="d">{esc(fmt_date(e["_dt"], lang))}</span></a></li>')
        parts.append("</ul></div>")
        body = "\n".join(parts)
    return shell(site, S, title=f'{S["archive_title"]} | {site["site_name"]}',
                 description=f'{S["archive_title"]}: {site["site_name"]}', path="/archive/", body=body)


def render_text_page(site: dict, S: dict, name: str, title: str) -> str:
    lang = site["language"]
    src = ROOT / "pages" / f"{name}.{lang}.html"
    if not src.exists():
        warn(f"{src.name} not found; using the English text")
        src = ROOT / "pages" / f"{name}.en.html"
    ads = ADS_SECTION.get(lang, ADS_SECTION["en"]) if site.get("adsense_client") else ""
    text = src.read_text(encoding="utf-8")
    values = {"site_name": esc(site["site_name"]), "contact_email": esc(site.get("contact_email", "")),
              "owner_name": esc(site.get("owner_name", "")), "site_url": esc(site["site_url"]),
              "hosting_provider": esc(site.get("hosting_provider", "")), "ads_section": ads}
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        warn(f"{src.name} has unfilled placeholders: {', '.join(sorted(set(left)))}")
    if "you@example.com" in text or "Your Name" in text:
        warn(f"{src.name}: edit contact_email and owner_name in site.json before going live")
    return shell(site, S, title=f'{title} | {site["site_name"]}', description=clip(re.sub(r"<[^>]+>", "", text), 155),
                 path=f"/{name}/", body=f'<div class="prose">\n{text}\n</div>')


def render_404(site: dict, S: dict) -> str:
    body = (f'<div class="empty"><h1>{esc(S["not_found"])}</h1><p>{esc(S["not_found_text"])}</p>'
            f'<p><a href="/">{esc(S["home"])}</a></p></div>')
    return shell(site, S, title=f'{S["not_found"]} | {site["site_name"]}', description=S["not_found"],
                 path="/404.html", body=body, noindex=True)


# --------------------------------------------------------------------------- machine files

def render_feed(site: dict, entries: list[dict]) -> str:
    url = site["site_url"]
    items = []
    for e in reversed(entries[-30:]):
        link = f'{url}/c/{e["slug"]}/'
        inner = (f'<p><img src="{esc(url + e["_img"])}" alt="{esc(e["alt_text"])}"></p>'
                 f'<p><em>{esc(e["caption"])}</em></p><p>{esc(e["blurb"])}</p>')
        items.append(
            f"<item><title>{esc(e['title'])}</title><link>{esc(link)}</link>"
            f"<guid isPermaLink=\"true\">{esc(link)}</guid>"
            f"<pubDate>{email.utils.format_datetime(e['_dt'])}</pubDate>"
            f"<description><![CDATA[{inner.replace(']]>', ']]&gt;')}]]></description></item>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0"><channel>'
            f'<title>{esc(site["site_name"])}</title><link>{esc(url)}/</link>'
            f'<description>{esc(site.get("tagline", ""))}</description><language>{site["language"]}</language>'
            + "".join(items) + "</channel></rss>\n")


def render_sitemap(site: dict, entries: list[dict]) -> str:
    url = site["site_url"]
    rows = [f"<url><loc>{url}/</loc></url>", f"<url><loc>{url}/archive/</loc></url>",
            f"<url><loc>{url}/about/</loc></url>", f"<url><loc>{url}/privacy/</loc></url>"]
    rows += [f"<url><loc>{url}/c/{e['slug']}/</loc><lastmod>{e['_dt'].date().isoformat()}</lastmod></url>"
             for e in entries]
    return ('<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(rows) + "</urlset>\n")


# --------------------------------------------------------------------------- build

def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(site_file: Path, content: Path, out: Path) -> None:
    site = load_site(site_file)
    S, lang = STRINGS[site["language"]], site["language"]
    if Image is None:
        warn("Pillow not installed: images are copied as they are (run: pip install -r requirements.txt)")
    if not site["site_url"]:
        warn("site_url is empty: no canonical links, social tags, feed or sitemap are generated")

    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():           # keep img/ so converted images are reused
        if child.name != "img":
            shutil.rmtree(child) if child.is_dir() else child.unlink()

    entries = process_images(load_entries(content, lang), content, out)
    if (out / "img").exists():            # remove images of cartoons that no longer exist
        wanted = {Path(e["_img"]).name for e in entries} | {Path(e["_thumb"]).name for e in entries}
        for f in (out / "img").iterdir():
            if f.name not in wanted:
                f.unlink()

    for f in (ROOT / "static").iterdir():
        shutil.copyfile(f, out / f.name)

    if entries:
        write(out / "index.html", render_cartoon(site, S, entries, len(entries) - 1, as_home=True))
        for i, e in enumerate(entries):
            write(out / "c" / e["slug"] / "index.html", render_cartoon(site, S, entries, i, as_home=False))
    else:
        write(out / "index.html", render_empty(site, S))
    write(out / "archive" / "index.html", render_archive(site, S, entries))
    write(out / "about" / "index.html", render_text_page(site, S, "about", S["about"]))
    write(out / "privacy" / "index.html", render_text_page(site, S, "privacy", S["privacy"]))
    write(out / "404.html", render_404(site, S))

    robots = "User-agent: *\nAllow: /\n"
    if site["site_url"]:
        robots += f"Sitemap: {site['site_url']}/sitemap.xml\n"
        write(out / "sitemap.xml", render_sitemap(site, entries))
        if entries:
            write(out / "feed.xml", render_feed(site, entries))
    write(out / "robots.txt", robots)
    if site.get("adsense_client", "").startswith("ca-pub-"):
        pub = site["adsense_client"].removeprefix("ca-")
        write(out / "ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")
    write(out / "_headers",
          "/img/*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
          "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n")

    print(f"Built {len(entries)} cartoons into {out}" + (f" ({len(warnings)} warnings)" if warnings else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", default="content", help="folder with cartoons.json and img/")
    parser.add_argument("--out", default="public")
    parser.add_argument("--site", default="site.json")
    args = parser.parse_args()
    resolve = lambda p: Path(p) if Path(p).is_absolute() else ROOT / p
    build(resolve(args.site), resolve(args.content), resolve(args.out))


if __name__ == "__main__":
    main()
