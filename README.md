# TubeRank

Local YouTube SEO dashboard with Claude AI and optional Notion business context.

## Setup

1. **Python 3.9+**

2. **Environment variables** (never commit real values):

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `YOUTUBE_API_KEY` | Yes | YouTube Data API v3 key (`AIza...`) or OAuth access token |
   | `YOUTUBE_CHANNEL_ID` | Yes | Channel to analyze (`UC...`) |
   | `ANTHROPIC_API_KEY` | Yes | From [Anthropic Console](https://console.anthropic.com) |
   | `TUBERANK_PASSWORD` | Yes | Shared password to open the dashboard (team login) |
   | `NOTION_TOKEN` | No | Notion internal integration secret (`secret_...`) |
   | `NOTION_PAGE_ID` | With Notion | Page URL or UUID for business context (set in `.env` only) |

3. **Optional: auto-load `.env`**

   ```bash
   pip install -r requirements.txt
   ```

   Or export variables in your shell and skip `pip install`.

4. **Run**

   ```bash
   python3 server.py
   ```

   Open **http://localhost:8765** and sign in with **`TUBERANK_PASSWORD`**.

## Security

- Keep `.env` out of git (see `.gitignore`).
- The browser **does not** receive API keys; only `server.py` reads them.
- The login password is **lightweight** (not a full user auth system). Anyone who can reach your server can still call the proxy APIs unless you add network restrictions.

## Files

- `server.py` — static server + API proxies  
- `tuberank.html` — UI  
- `.env.example` — template for secrets  
