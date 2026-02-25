# Environment setup for the news dashboard

## 1. Create `.env` with your API keys

Create a file named **`.env`** in **one** of these places (the app loads from both):

- Project root: `DS-AIforSystemsEng-Project/.env`
- Or: `DS-AIforSystemsEng-Project/AppV1/.env`

Put this in the file (replace the values with your real keys):

```bash
# Get NYT key: https://developer.nytimes.com/get-started
# Get OpenAI key: https://platform.openai.com/api-keys

NYT_API_KEY=your_actual_nyt_api_key
OPENAI_API_KEY=your_actual_openai_api_key
```

- **NYT_API_KEY** – required for loading articles. Get one at https://developer.nytimes.com/get-started  
- **OPENAI_API_KEY** – required for sentiment (and impact) classification. Get one at https://platform.openai.com/api-keys  
  - If you leave it empty, all articles are treated as “neutral”; the sentiment filter still works (e.g. “neutral” shows all).

## 2. Run the app and refresh

1. From the project root:  
   `shiny run AppV1/app.py`  
   (or run from `AppV1/`: `shiny run app.py`)

2. When the app opens, it runs an **initial load** and will fetch articles if `NYT_API_KEY` is set.

3. If you add or change keys later, click **Refresh** in the sidebar to reload articles and re-run classification.

## 3. Quick copy-paste (empty keys)

If you only want the variable names and will fill keys later, use:

```
NYT_API_KEY=
OPENAI_API_KEY=
```

Save as `.env` in project root or in `AppV1/`, then add your key values on the right of the `=`.
