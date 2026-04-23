# NutriSeeker

AI nutrient analysis system with a Streamlit frontend, a FastAPI backend, and local model/database helpers.

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
USDA_API_KEY=your_usda_key
NUTRISEEKER_API_URL=http://localhost:8000
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL_NAME=llava
NUTRISEEKER_ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
USER_DB_PATH=database/nutriseeker_users.db
```

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn backend.main:app --reload
```

Start the frontend in another terminal:

```bash
streamlit run frontend/app.py
```

## Security checks

Run the repo safety check before pushing:

```bash
python scripts/security_check.py
```

It scans for likely hardcoded secrets and warns about local-only files that should stay out of Git.
