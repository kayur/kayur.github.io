# Blog System

A self-contained blog front-end that lives under `blog/` so the homepage stays untouched. Posts are authored as Markdown files stored in this repo, while metadata lives in `posts/index.json`.

## Folder map

- `index.html` – blog landing page and React-free UI powered by vanilla JS.
- `blog.css` – responsive styling inspired by Medium (card feed, reader pane, featured hero).
- `app.js` – loads `posts/index.json`, renders the feed, and fetches Markdown on demand.
- `analytics.js` – tiny adapter that forwards events to Plausible (already embedded) and an optional custom endpoint via `navigator.sendBeacon`.
- `posts/` – Markdown bodies plus `index.json` manifest.

## Adding or migrating posts

1. Copy the Medium body into a Markdown file under `posts/`. Keep assets in `blog/images/` (or reuse `images/`).
2. Append an entry inside `posts/index.json` with:
   - `slug`: URL hash fragment and file stem.
   - `title`, `summary`, `readTime`, `published` (ISO date).
   - `tags`: array of short descriptors.
   - `origin`: canonical Medium link for SEO + attribution.
   - `source`: relative path to the Markdown file.
   - `status`: `published` renders the Markdown, `draft` shows a migration reminder.
   - Optional `pinned` to keep a story in the hero and `accent` for gradient colors.
3. Rebuild/preview with `python3 -m http.server` (or any static host) and open `/blog/`.

The reader automatically updates the URL hash (e.g., `#/2025-goals`) so you can deep link or share via the “Copy link” button.

## Analytics + short links

- Plausible is loaded via `<script data-domain="kayur.github.io" src="https://plausible.io/js/script.js">`. Custom events fire through `window.blogAnalytics.track()` inside `app.js`.
- To capture geo/IP data like Medium, point `window.BLOG_ANALYTICS_ENDPOINT` to a serverless collector (e.g., Vercel edge, Cloudflare Worker) that stores hits in BigQuery / Supabase. Example snippet:
  ```html
  <script>
    window.BLOG_ANALYTICS_ENDPOINT = 'https://analytics.yourdomain.com/collect';
  </script>
  ```
- `app.js` already copies a canonical short link (`/blog/#slug`). You can later add Netlify redirects or Cloudflare Workers for even shorter aliases if desired.

## Future enhancements

- Add a `scripts/sync-medium.mjs` helper that reads the Medium RSS feed and outputs Markdown + JSON entries.
- Move posts to a headless CMS (Sanity/Contentful) once Git-based Markdown feels limiting.
- Extend analytics.js to log scroll depth, time on page, or referrers for richer dashboards.
