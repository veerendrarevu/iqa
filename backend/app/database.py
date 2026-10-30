import os
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ---------------------------------------------------------------------------
# Load .env — prefer backend/app/.env, then backend/.env, then CWD/.env
# ---------------------------------------------------------------------------
for _candidate in (
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
):
    if _candidate.exists():
        load_dotenv(dotenv_path=_candidate, override=False)
        break
else:
    load_dotenv(override=False)


def _build_url(raw: str) -> str:
    """
    Normalise a Neon (or any Postgres) URL for use with psycopg2:

    * Replace the scheme with ``postgresql+psycopg2`` so SQLAlchemy uses the
      right driver regardless of whether the URL starts with ``postgres://`` or
      ``postgresql://``.
    * Strip ``channel_binding`` from the query string — psycopg2 does not
      understand it and will raise a ``ProgrammingError``.
    * Keep ``sslmode=require`` (and any other params).
    """
    parsed = urlparse(raw)

    # Normalise scheme
    scheme = "postgresql+psycopg2"

    # Filter query params
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("channel_binding", None)          # psycopg2 doesn't support it
    new_query = urlencode({k: v[0] for k, v in params.items()})

    normalised = urlunparse((
        scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))
    return normalised


_raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql://iqa:iqa@localhost:5432/iqa",
)
DATABASE_URL = _build_url(_raw_url)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # detect stale connections (important for Neon cold starts)
    pool_recycle=300,     # recycle connections every 5 min to avoid idle timeouts
    pool_size=5,
    max_overflow=5,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(retries: int = 20, delay: float = 1.5):
    """Create tables, retrying to handle Neon cold-start delays."""
    from . import models  # noqa: F401  (registers ORM tables with Base.metadata)

    for attempt in range(retries):
        try:
            Base.metadata.create_all(engine)
            return
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"[db] not ready ({exc.__class__.__name__}), retrying in {delay}s…")
            time.sleep(delay)
