# News for People in Hurry

A Shiny for Python app that fetches NYT Top Stories, categorizes and scores news (breaking, trending, sentiment), and displays them with AI-generated summaries.

## Setup

### 1. Install Python packages

```bash
pip install -r requirements.txt
```

Or with uv:

```bash
uv pip install -r requirements.txt
```

### 2. API keys

Add your API keys to the **project root** `.env` file:

```
NYT_API_KEY=your_nytimes_api_key
OPENAI_API_KEY=your_openai_api_key
```

- **NYT API key**: Get one at [developer.nytimes.com](https://developer.nytimes.com/)
- **OpenAI API key**: Get one at [platform.openai.com](https://platform.openai.com/)

### 3. Run the app

From the project root or from `AppV1`:

```bash
cd AppV1
python app.py
```

The app opens in your default browser automatically.

The app loads `.env` from the project root (parent of AppV1).

## Features

- **Categories**: ALL, business, sports, arts, technology, world, politics
- **Card order**: First 6 cards prioritize breaking (2) → trending (2) → latest (2); pagination continues with latest only
- **Time filter**: Show articles from the past 6–48 hours
- **Sentiment filter**: positive, negative, neutral (optional)
- **Summary tone**: Informational, Opinion, or Analytical

## Project structure

```
AppV1/
├── app.py           # Main Shiny app
├── config.py        # Load .env from root, API keys
├── buildplan.md     # Implementation plan
├── requirements.txt
├── modules/
│   ├── data_fetch.py      # NYT API
│   ├── categorization.py  # Breaking, trending, latest
│   ├── ai_services.py     # OpenAI sentiment & summary
│   └── news_cards.py      # Card UI
└── www/
    └── placeholder.svg    # Fallback image
```
