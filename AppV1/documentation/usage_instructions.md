# Usage instructions

## Local use

1. **Python environment**  
   Use Python 3.10+ (recommended). From the `AppV1` folder install dependencies:

   ```bash
   cd AppV1
   pip install -r requirements.txt
   ```

2. **API keys**  
   Create a `.env` file in the **repository root** or in **`AppV1/`** with:

   ```bash
   NYT_API_KEY=your_nytimes_key
   OPENAI_API_KEY=your_openai_key
   ```

   Details: see `AppV1/SETUP_ENV.md`.

3. **Run the app**

   ```bash
   cd AppV1
   shiny run app.py
   ```

   Or from the repo root:

   ```bash
   shiny run AppV1/app.py
   ```

   By default the app listens on `127.0.0.1` and port `8000` unless you set `PORT` / `HOST` in the environment (see `app.py`).

4. **First load**  
   On open, the app fetches NYT articles automatically. If the feed is empty, use the sidebar **Refresh** control after fixing `NYT_API_KEY` or network issues.

---

## Using the dashboard

- **Sidebar — Filters**  
  - **Time window:** Restricts articles by published time (wider windows may trigger more sentiment/impact work).  
  - **Sentiment:** Optional filter on AI-assigned sentiment.  
  - **Summary tone:** Informational, Opinion, or Analytical — affects card summaries.  
  - **Refresh News:** Reloads from the NYT API and clears relevant caches.

- **Category tabs**  
  Each tab shows up to six cards per page; use **Next page** / **Previous page** to move through the filtered list. Cards show breaking/trending emphasis on the first page slots.

- **Section brief**  
  At the top of each category view, a short brief summarizes that slice of the feed; it upgrades when the full agent pipeline finishes.

- **Signal Studio**  
  Open this tab for the three-agent view: cross-section links, world mood, and market validation (including live market context). The header marquee reflects the latest agent insight when available.

- **Dive deeper (research brief)**  
  On a card, use the control that opens the **Research brief** modal. The assistant may call Wikipedia and Yahoo Finance tools, then show a text brief. Requires `OPENAI_API_KEY`. Repeated requests for the same article URL may be served from cache.

---

## Deployed app

- **URL:** Use the URL your hosting provider assigns after deploy (for example `https://<app-name>.herokuapp.com` or your class platform). This repository does not hard-code a production URL.
- **Configuration:** Set `NYT_API_KEY` and `OPENAI_API_KEY` in the host’s environment or secrets UI — same names as local `.env`.
- **Start command:** If you deploy from `AppV1`, align the process with `Procfile` (`uvicorn app:app ...`) or your platform’s equivalent for a Shiny ASGI app; confirm with your platform’s Shiny/Python docs.

### Password / access control

The application **does not implement an in-app login or password** in the current codebase. Access is open to anyone who can reach the URL.

If your instructor or host requires a password (for example HTTP basic auth in front of the app, or a private network), use the credentials **they** provide; there is nothing to enter inside the Shiny UI itself.

---

## Troubleshooting (short)

| Symptom | What to check |
|--------|----------------|
| No articles | `NYT_API_KEY` set; NYT API status; click **Refresh News** |
| All sentiment neutral | `OPENAI_API_KEY` missing or empty |
| Research brief errors | OpenAI quota/network; article still in current feed after refresh |
| Empty Signal Studio | Wait for background pipeline; confirm OpenAI key; refresh feed |
