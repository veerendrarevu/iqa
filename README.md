# Image Quality Inspector

React (Vite) + FastAPI + PostgreSQL (Neon serverless).  
Uploaded images are analysed for blur, noise, and exposure; results are saved to Neon.

---

## Quick start (Docker — recommended)

```powershell
# 1. Copy and fill in your Neon URL
Copy-Item backend\.env.example backend\.env
# Edit backend\.env and set DATABASE_URL

# 2. Build and run
docker compose up --build
```

Open http://localhost:8080 (API docs: http://localhost:8000/docs).  
The first start downloads BRISQUE/MUSIQ weights (~500 MB) into the `model_cache` volume — this takes a minute.

---

## Run locally on Windows (PowerShell)

### Backend

```powershell
# 1. Create and activate a virtual environment (Python 3.11 or 3.12 recommended)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install PyTorch first (CPU build is much smaller)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Install remaining dependencies
pip install -r requirements.txt

# 4. Create your .env with your Neon DATABASE_URL
Copy-Item .env.example app\.env
# Edit backend\app\.env — set DATABASE_URL to your Neon connection string

# 5. Start the dev server
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
```

---

## Configuration

| Variable        | Default                          | Description                                         |
|-----------------|----------------------------------|-----------------------------------------------------|
| `DATABASE_URL`  | _(required)_                     | Neon Postgres URL (`postgresql://...?sslmode=require`) |
| `MAX_UPLOAD_MB` | `10`                             | Per-file upload size limit (MB)                     |
| `CORS_ORIGINS`  | `http://localhost:5173`          | Comma-separated list of allowed frontend origins    |

Put these in `backend/app/.env` (local dev) or `backend/.env` (Docker). The file is auto-loaded at startup.

---

## API

| Method | Path | Purpose |
|---|---|---|
| POST | /api/images | Upload one or more files (`files` form field); analyses and stores them |
| GET | /api/images?label=&limit=&offset= | List results, newest first |
| GET | /api/images/{id} | One result |
| GET | /api/images/{id}/file | Original image bytes |
| GET | /api/images/{id}/thumbnail | 320 px JPEG |
| DELETE | /api/images/{id} | Remove image and analysis |
| GET | /api/stats | Counts per verdict and average score |
| GET | /api/storage | Total bytes / MB stored (Neon quota tracking) |
| GET | /api/health | DB + device check |

---

## Troubleshooting

### `uvicorn` is not recognized

PowerShell does not add the venv `Scripts` folder to `PATH` when you activate with `Activate.ps1` in some setups. Use the module form instead:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

If you get `No module named uvicorn`, your venv is not active or you haven't run `pip install -r requirements.txt` yet.

---

### `no pq wrapper available` / `Could not load the psycopg2 library`

This means the `DATABASE_URL` scheme is wrong. The backend expects a `postgresql://` or `postgres://` URL and converts it to `postgresql+psycopg2://` automatically. If you paste a pgBouncer URL (which sometimes starts with `postgresql+asyncpg://` or similar), replace the scheme with just `postgresql://`.

Also ensure `psycopg2-binary` is installed:

```powershell
pip install psycopg2-binary
```

---

### Neon cold-start delays / `connection refused` on first request

Neon free-tier projects suspend after 5 minutes of inactivity. The first request after a cold start can take 2–5 seconds while the compute wakes up. The `init_db` retry loop (20 attempts, 1.5 s apart) handles this at startup. For runtime requests the `pool_pre_ping=True` engine setting detects stale connections and reconnects transparently.

If you see repeated cold-start timeouts, consider upgrading to a Neon paid plan or keeping the project warm with a scheduled health-check ping.

---

### `channel_binding` error with psycopg2

Neon connection strings from the dashboard sometimes include `channel_binding=require` in the query string. psycopg2 does not support this parameter and raises a `ProgrammingError`. The `database.py` in this project strips it automatically. If you bypass `database.py` and connect with a raw URL, remove `channel_binding=require` manually.
