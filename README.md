# TerraLaw BD

Informational legal assistant for Bangladeshi land law, built with RAG (retrieval-augmented generation).

## Project structure

```
TerraLaw/
├── backend/           # FastAPI server and admin dashboard
│   ├── app.py
│   └── reports/       # Runtime metrics (dashboard, request logs)
├── frontend/          # Desktop chat clients
│   ├── ui.py          # Main Tkinter app (auth + chat history)
│   ├── chat_ui.py     # Simple PyQt6 chat client
│   └── data/          # Local user/chat storage (gitignored at runtime)
├── model/             # RAG pipeline, evaluation, and MLOps
│   ├── terralaw_core.py
│   ├── rag_pipeline.py
│   ├── evaluate_rag.py
│   ├── mlops_pipeline.py
│   ├── paths.py
│   ├── benchmarks/
│   ├── reports/       # Evaluation metrics and MLOps run artifacts
│   └── vectorstore/   # Generated embeddings (build locally)
├── data/
│   ├── processed/     # Cleaned statute text (*_cleaned.txt)
│   └── raw/           # Raw statute text (*_raw.txt)
├── requirements.txt
└── .env               # API keys (not committed)
```

## Setup

1. Create a virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

2. Create `.env` in the project root:

```env
GROQ_API_KEY=your_groq_api_key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
```

3. Build the vector index from processed legal data:

```bash
python -m model.rag_pipeline
```

## Run

Start the API (from project root):

```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Start the desktop UI:

```bash
python frontend/ui.py
```

## Model tooling

Evaluate RAG quality against benchmark cases:

```bash
python -m model.evaluate_rag
```

Run the full build + evaluate MLOps pipeline:

```bash
python -m model.mlops_pipeline
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Health check and available acts |
| `GET /ask?question=...` | Ask a land-law question |
| `GET /admin/dashboard` | Admin usage dashboard (HTTP Basic auth) |

## Legal corpus

Indexed acts include the Transfer of Property Act (1882), State Acquisition and Tenancy Act (1950), Non-Agricultural Tenancy Act (1949), Acquisition and Requisition of Immovable Property Act (2017), and Land Development Tax Act (2023).
