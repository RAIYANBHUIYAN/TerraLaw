# TerraLaw BD

Informational legal assistant for Bangladeshi land law, built with RAG (retrieval-augmented generation).

## Project structure

```
TerraLaw/
├── backend/                 # FastAPI API server
│   ├── app.py               # Routes, CORS, admin dashboard
│   ├── config.py            # LLM, retrieval, rerank settings
│   ├── services/            # RAG, reranker, vectorstore, users
│   └── templates/           # Admin dashboard HTML
│
├── frontend/                # Next.js web app
│   └── src/
│       ├── app/             # Pages: login, register, chat
│       ├── components/      # UI components
│       └── lib/             # API client, session, types
│
├── model/                   # Domain logic & ML pipeline
│   ├── paths.py             # Shared path constants
│   ├── core/
│   │   └── terralaw_core.py # Statute parsing, chunking, routing
│   ├── pipeline/
│   │   ├── rag_pipeline.py  # Index builder
│   │   ├── evaluate_rag.py  # Benchmark evaluation
│   │   └── mlops_pipeline.py
│   ├── benchmarks/          # Eval test cases
│   └── vectorstore/         # Embeddings (gitignored, built locally)
│
├── data/
│   ├── processed/           # Cleaned statutes (*_cleaned.txt) — index input
│   ├── raw/                 # Source statute archives
│   └── app/                 # Runtime users + chat history (gitignored)
│
├── scripts/
│   ├── run_backend.py       # Start API on :8000
│   ├── run_frontend.py      # Start Next.js on :3000
│   ├── build_index.py       # Build vector index from processed data
│   ├── run_eval.py          # Run benchmark evaluation
│   └── run_mlops.py         # Build index + evaluate pipeline
│
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
cd frontend && npm install
```

Create `.env` in the project root:

```env
GROQ_API_KEY=your_groq_api_key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
LLM_TEMPERATURE=0.1
RERANK_ENABLED=true
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Build the vector index:

```bash
python scripts/build_index.py
```

### Pinecone (integrated index — matches your console setup)

Create the index in the Pinecone console with:

| Setting | Value |
|---------|-------|
| Name | `terralaw-bd` |
| Model | `llama-text-embed-v2` |
| Field map | `text` |
| Dimension | 1024 |
| Metric | cosine |

Add to `.env`:

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=terralaw-bd
PINECONE_INDEX_HOST=your-index-host.pinecone.io
PINECONE_TEXT_FIELD=text
PINECONE_INTEGRATED=true
VECTORSTORE_BACKEND=pinecone
```

Verify the index and print the host:

```bash
python scripts/setup_pinecone.py
```

Upload statute chunks (Pinecone embeds the `text` field automatically):

```bash
python scripts/build_index.py
```

`build_index.py` saves local pickle backups **and** upserts to Pinecone when `PINECONE_API_KEY` is set.

With `VECTORSTORE_BACKEND=auto`, the backend prefers Pinecone and falls back to local pickle for development.

### PostgreSQL (users + chat history — required for Render)

Without a database, user accounts and chat history are stored in local JSON files (`data/app/`), which **do not persist** on Render redeploys.

**Option A — Neon (recommended)**

1. Create a free project at [neon.tech](https://neon.tech)
2. Copy the connection string from the dashboard
3. Add to `.env`:

```env
DATABASE_URL=postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

**Option B — Render Postgres**

1. Render Dashboard → **New** → **PostgreSQL**
2. Copy **Internal Database URL** (for Render backend) or **External** (for local setup)
3. Add as `DATABASE_URL` in Render environment variables

**Initialize tables:**

```bash
python scripts/setup_postgres.py
```

**Test connection:**

```bash
python scripts/test_postgres.py
```

Tables created: `users`, `conversations`, `messages`. The backend auto-runs schema setup on startup when `DATABASE_URL` is set.

## Run

Terminal 1 — backend:

```bash
python scripts/run_backend.py
```

Terminal 2 — frontend:

```bash
python scripts/run_frontend.py
```

Open http://localhost:3000

Default admin login: `admin` / `123`

## Deploy (Vercel + Render)

### Frontend — Vercel

1. Push this repo to GitHub.
2. Import the repo in [Vercel](https://vercel.com).
3. Set **Root Directory** to `frontend`.
4. Add environment variable:

```env
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

5. Deploy. Copy your Vercel URL (e.g. `https://terralaw-bd.vercel.app`).

### Backend — Render

1. Create a **Web Service** from the same GitHub repo.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
4. Add environment variables from `.env.example` (never commit `.env`).
5. Set `CORS_ORIGINS` to your Vercel URL.
6. Run once locally: `python scripts/upload_pinecone.py` and `python scripts/setup_postgres.py`

## Scripts

| Command | Description |
|---------|-------------|
| `python scripts/build_index.py` | Build vector index from `data/processed/` |
| `python scripts/setup_pinecone.py` | Create or verify Pinecone index |
| `python scripts/upload_pinecone.py` | Upload chunks to Pinecone only |
| `python scripts/test_pinecone.py` | Test Pinecone connection and search |
| `python scripts/setup_postgres.py` | Create PostgreSQL tables |
| `python scripts/test_postgres.py` | Test PostgreSQL connection |
| `python scripts/run_eval.py` | Evaluate RAG against benchmark cases |
| `python scripts/run_mlops.py` | Full build + evaluate pipeline |

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS |
| Backend | FastAPI, Uvicorn |
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Embeddings | Pinecone `llama-text-embed-v2` (integrated) or local MiniLM for dev pickle |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Vector store | Pinecone (production) or local pickle (dev) |
| App data | PostgreSQL (production) or local JSON (dev) |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /ask?question=...` | RAG query |
| `POST /api/auth/login` | User login |
| `POST /api/auth/register` | User registration |
| `GET /api/conversations` | List saved chats |
| `GET /admin/dashboard` | Admin metrics dashboard |
