#!/usr/bin/env python3
"""One-time script to convert Medium HTML export to markdown blog posts."""

import argparse
import html as html_mod
import json
import math
import os
import re
import ssl
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ACCENT_COLORS = [
    '#0b3954', '#415a77', '#5c3d8c', '#2d6a4f', '#9c4a1a',
    '#1a535c', '#6b2d5b', '#3d405b', '#81523f', '#1b4965',
    '#5f0f40', '#3a5a40', '#774936', '#264653', '#6d597a',
    '#355070', '#606c38',
]

WORDS_PER_MINUTE = 238

SKIP_MD_GENERATION = {'2025-goals'}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(title):
    s = title.lower()
    s = s.replace('&', 'and')
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def infer_tags(title):
    tags = []
    t = title.lower()
    if 'goal' in t:
        tags.append('Goals')
    if 'recap' in t:
        tags.append('Recap')
    if not tags:
        tags.append('Life')
    return tags


def read_time(text):
    words = len(text.split())
    minutes = max(1, math.ceil(words / WORDS_PER_MINUTE))
    return f'{minutes} min read'


def img_ext(url):
    p = url.split('?')[0].lower()
    if '.png' in p:
        return '.png'
    if '.gif' in p:
        return '.gif'
    return '.jpeg'


def transform_canonical(url):
    return re.sub(
        r'https?://medium\.com/@kayur/',
        'https://kayur.medium.com/',
        url,
    )

# ---------------------------------------------------------------------------
# Inline HTML → Markdown
# ---------------------------------------------------------------------------

def inline_md(s):
    """Convert inline HTML (a, strong, em, br) to markdown text."""
    # Links first (may contain other inline formatting)
    s = re.sub(
        r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        r'[\2](\1)',
        s,
        flags=re.DOTALL,
    )
    # Bold
    s = re.sub(r'<strong\b[^>]*>(.*?)</strong>', r'**\1**', s, flags=re.DOTALL)
    # Italic
    s = re.sub(r'<em\b[^>]*>(.*?)</em>', r'*\1*', s, flags=re.DOTALL)
    # Line breaks
    s = re.sub(r'<br\s*/?>', '\n', s)
    # Strip remaining tags
    s = re.sub(r'<[^>]+>', '', s)
    # Unescape HTML entities
    s = html_mod.unescape(s)
    return s

# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_meta(html):
    title_m = re.search(r'<h1 class="p-name">(.*?)</h1>', html, re.DOTALL)
    title = html_mod.unescape(title_m.group(1).strip()) if title_m else ''

    date_m = re.search(r'<time[^>]*datetime="([^"]*)"', html)
    date = date_m.group(1)[:10] if date_m else ''

    sub_m = re.search(
        r'<section data-field="subtitle"[^>]*>\s*(.*?)\s*</section>',
        html,
        re.DOTALL,
    )
    subtitle = ''
    if sub_m:
        subtitle = re.sub(r'<[^>]+>', '', sub_m.group(1)).strip()
        subtitle = html_mod.unescape(subtitle)

    # Fallback: first paragraph of body
    if not subtitle:
        p_m = re.search(
            r'<p\b[^>]*class="graf graf--p[^"]*"[^>]*>(.*?)</p>',
            html,
            re.DOTALL,
        )
        if p_m:
            subtitle = re.sub(r'<[^>]+>', '', p_m.group(1)).strip()
            subtitle = html_mod.unescape(subtitle)
            if len(subtitle) > 180:
                subtitle = subtitle[:177].rsplit(' ', 1)[0] + '...'

    canon_m = re.search(r'<a\s+href="([^"]*)"[^>]*class="p-canonical"', html)
    canonical = transform_canonical(canon_m.group(1)) if canon_m else ''

    return title, date, subtitle, canonical

# ---------------------------------------------------------------------------
# Body extraction and conversion
# ---------------------------------------------------------------------------

def extract_body(html):
    start = html.find('<section data-field="body"')
    if start == -1:
        return ''
    start = html.find('>', start) + 1
    end = html.find('<footer', start)
    if end == -1:
        return ''
    return html[start:end]


def body_to_md(body_html, slug, images_dir):
    """Convert body HTML to markdown. Returns (markdown, [(url, local_path)])."""
    b = body_html
    # Strip structural wrappers
    b = re.sub(r'</?section\b[^>]*>', '', b)
    b = re.sub(r'</?div\b[^>]*>', '', b)
    b = re.sub(r'<hr\b[^>]*/?\s*>', '', b)

    parts = []
    img_n = 0
    downloads = []

    block = re.compile(
        r'(<h3\b[^>]*>.*?</h3>)'
        r'|(<h4\b[^>]*>.*?</h4>)'
        r'|(<figure\b[^>]*>.*?</figure>)'
        r'|(<ul\b[^>]*>.*?</ul>)'
        r'|(<ol\b[^>]*>.*?</ol>)'
        r'|(<blockquote\b[^>]*>.*?</blockquote>)'
        r'|(<p\b[^>]*>.*?</p>)',
        re.DOTALL,
    )

    for m in block.finditer(b):
        el = m.group()

        # --- h3 → ## ---------------------------------------------------------
        if el.startswith('<h3'):
            if 'graf--title' in el:
                continue
            inner = re.sub(r'</?h3\b[^>]*>', '', el)
            inner = re.sub(r'</?strong\b[^>]*>', '', inner)
            text = inline_md(inner).strip()
            if text:
                parts.append(f'\n## {text}\n\n')

        # --- h4 → ### --------------------------------------------------------
        elif el.startswith('<h4'):
            inner = re.sub(r'</?h4\b[^>]*>', '', el)
            inner = re.sub(r'</?strong\b[^>]*>', '', inner)
            text = inline_md(inner).strip()
            if text:
                parts.append(f'\n### {text}\n\n')

        # --- figure → ![caption](path) *caption* ----------------------------
        elif el.startswith('<figure'):
            img_m = re.search(r'<img\b[^>]*\bsrc="([^"]*)"', el)
            if img_m:
                src = img_m.group(1)
                if 'cdn-images-1.medium.com' in src:
                    img_n += 1
                    ext = img_ext(src)
                    fname = f'{img_n}{ext}'
                    rel = f'images/{slug}/{fname}'
                    abs_path = os.path.join(images_dir, slug, fname)
                    dl_url = re.sub(r'/max/\d+/', '/max/1200/', src)
                    downloads.append((dl_url, abs_path))

                    cap = ''
                    cap_m = re.search(
                        r'<figcaption\b[^>]*>(.*?)</figcaption>',
                        el,
                        re.DOTALL,
                    )
                    if cap_m:
                        cap_raw = cap_m.group(1).strip()
                        # Strip whole-caption em wrapper Medium often adds
                        em_wrap = re.match(
                            r'^<em\b[^>]*>(.*)</em>$', cap_raw, re.DOTALL
                        )
                        if em_wrap:
                            cap_raw = em_wrap.group(1)
                        cap = inline_md(cap_raw).strip()
                    else:
                        alt_m = re.search(r'<img\b[^>]*\balt="([^"]*)"', el)
                        if alt_m and alt_m.group(1).strip():
                            cap = html_mod.unescape(alt_m.group(1)).strip()

                    parts.append(f'\n![{cap}]({rel})\n')
                    if cap:
                        parts.append(f'*{cap}*\n')
                    parts.append('\n')

        # --- ul / ol ---------------------------------------------------------
        elif el.startswith('<ul') or el.startswith('<ol'):
            is_ol = el.startswith('<ol')
            items = re.findall(r'<li\b[^>]*>(.*?)</li>', el, re.DOTALL)
            for i, raw in enumerate(items, 1):
                text = inline_md(raw).strip()
                text = re.sub(r'\n\s*', ' ', text)   # flatten multi-line
                prefix = f'{i}.' if is_ol else '-'
                parts.append(f'{prefix} {text}\n')
            parts.append('\n')

        # --- blockquote ------------------------------------------------------
        elif el.startswith('<blockquote'):
            inner = re.sub(r'</?blockquote\b[^>]*>', '', el)
            text = inline_md(inner).strip()
            for line in text.split('\n'):
                parts.append(f'> {line}\n')
            parts.append('\n')

        # --- p ---------------------------------------------------------------
        elif el.startswith('<p'):
            inner = re.sub(r'</?p\b[^>]*>', '', el)
            text = inline_md(inner).strip()
            if text:
                parts.append(f'{text}\n\n')

    return ''.join(parts).strip() + '\n', downloads

# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------

def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        return
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            data = r.read()
        with open(dest, 'wb') as f:
            f.write(data)
        print(f'  ↓ {os.path.basename(dest)}')
    except Exception as e:
        print(f'  ⚠ {url}: {e}')

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='Import Medium HTML export as markdown blog posts',
    )
    ap.add_argument('--input', required=True, help='Medium export posts/ dir')
    ap.add_argument('--output', required=True, help='blog/posts/ output dir')
    ap.add_argument('--images', required=True, help='blog/images/ output dir')
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    img_dir = Path(args.images)

    # Read existing index for entries we want to preserve
    existing_index = {}
    idx_path = out / 'index.json'
    if idx_path.exists():
        for e in json.loads(idx_path.read_text()):
            existing_index[e['slug']] = e

    html_files = sorted(
        f for f in inp.glob('*.html') if not f.name.startswith('draft_')
    )

    entries = []

    for hf in html_files:
        print(f'\n→ {hf.name}')
        raw = hf.read_text('utf-8')
        title, date, subtitle, canonical = extract_meta(raw)
        if not title:
            print('  skip (no title)')
            continue

        slug = slugify(title)

        # ---- Skip markdown generation for hand-edited posts ----
        if slug in SKIP_MD_GENERATION:
            print(f'  skip md (hand-edited)')
            if slug in existing_index:
                entry = existing_index[slug].copy()
                entry['origin'] = canonical or entry.get('origin', '')
                entry['status'] = 'published'
            else:
                md_path = out / f'{slug}.md'
                md_text = md_path.read_text() if md_path.exists() else ''
                entry = {
                    'slug': slug,
                    'title': title,
                    'summary': subtitle,
                    'published': date,
                    'readTime': read_time(md_text),
                    'tags': infer_tags(title),
                    'pinned': True,
                    'origin': canonical,
                    'source': f'posts/{slug}.md',
                    'status': 'published',
                    'accent': '#0b3954',
                }
            entries.append(entry)
            continue

        # ---- Convert body to markdown ----
        body_html = extract_body(raw)
        md, downloads = body_to_md(body_html, slug, str(img_dir))
        full_md = f'# {title}\n\n{md}'

        # Write markdown file
        md_path = out / f'{slug}.md'
        md_path.write_text(full_md, 'utf-8')
        print(f'  ✓ {slug}.md')

        # Download images
        for url, dest in downloads:
            download(url, dest)

        entries.append({
            'slug': slug,
            'title': title,
            'summary': subtitle,
            'published': date,
            'readTime': read_time(full_md),
            'tags': infer_tags(title),
            'pinned': False,
            'origin': canonical,
            'source': f'posts/{slug}.md',
            'status': 'published',
            'accent': '',
        })

    # Sort by date descending
    entries.sort(key=lambda e: e['published'], reverse=True)

    # Assign accent colors (preserve 2025-goals existing color)
    for i, e in enumerate(entries):
        if e['slug'] == '2025-goals' and e.get('accent'):
            continue
        e['accent'] = ACCENT_COLORS[i % len(ACCENT_COLORS)]

    # Write index.json
    idx_path.write_text(json.dumps(entries, indent=2) + '\n', 'utf-8')
    print(f'\n✓ index.json: {len(entries)} entries')


if __name__ == '__main__':
    main()
