import os
from contextlib import asynccontextmanager
from typing import List, Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer, joinedload

from . import pipeline
from .database import get_db, init_db
from .models import Analysis, Image

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pipeline.load_models()  # warm up so the first upload isn't slow
    yield


app = FastAPI(title="Image Quality API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize(img: Image) -> dict:
    a = img.analysis
    return {
        "id": img.id,
        "filename": img.filename,
        "size_bytes": img.size_bytes,
        "width": img.width,
        "height": img.height,
        "created_at": img.created_at.isoformat(),
        "quality_score": a.quality_score,
        "quality_label": a.quality_label,
        "issues": a.issues,
        "metrics": {
            "brisque_score": a.brisque_score,
            "musiq_score": a.musiq_score,
            "sharpness": a.sharpness,
            "brightness": a.brightness,
            "noise": a.noise,
            "dark_pixel_percentage": a.dark_pixel_percentage,
            "bright_pixel_percentage": a.bright_pixel_percentage,
        },
    }


def make_thumbnail(bgr: np.ndarray, side: int = 320) -> bytes:
    h, w = bgr.shape[:2]
    s = side / max(h, w)
    if s < 1:
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes()


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "device": str(pipeline.DEVICE)}


@app.post("/api/images", status_code=201)
def upload_images(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload one or more images; each is analysed and stored with its results."""
    created, errors = [], []
    for f in files:
        name = f.filename or "unnamed"
        raw = f.file.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            errors.append({
                "filename": name,
                "error": (
                    f"File exceeds the {MAX_UPLOAD_MB} MB upload limit. "
                    f"Resize the image or raise MAX_UPLOAD_MB in your .env."
                ),
            })
            continue
        if f.content_type not in ALLOWED:
            errors.append({"filename": name, "error": "Unsupported type. Use JPEG, PNG, WebP, BMP or TIFF."})
            continue
        bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            errors.append({"filename": name, "error": "File could not be read as an image."})
            continue

        try:
            result = pipeline.evaluate_image_quality(bgr)
        except Exception as exc:  # keep one bad file from failing the batch
            errors.append({"filename": name, "error": f"Analysis failed: {exc}"})
            continue

        h, w = bgr.shape[:2]
        img = Image(
            filename=name, content_type=f.content_type, size_bytes=len(raw),
            width=w, height=h, data=raw, thumbnail=make_thumbnail(bgr),
            analysis=Analysis(
                quality_score=result["quality_score"],
                quality_label=result["quality_label"],
                issues=result["issues"],
                **result["metrics"],
            ),
        )
        db.add(img)
        db.commit()
        created.append(serialize(img))

    if not created and errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"created": created, "errors": errors}


@app.get("/api/images")
def list_images(
    label: Optional[str] = Query(None, pattern="^(ACCEPTABLE|DEGRADED|DEFECTIVE)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        select(Image)
        .options(joinedload(Image.analysis), defer(Image.data), defer(Image.thumbnail))
        .join(Analysis)
        .order_by(Image.created_at.desc())
    )
    count_q = select(func.count()).select_from(Analysis)
    if label:
        q = q.where(Analysis.quality_label == label)
        count_q = count_q.where(Analysis.quality_label == label)
    total = db.scalar(count_q)
    rows = db.scalars(q.limit(limit).offset(offset)).unique().all()
    return {"total": total, "items": [serialize(r) for r in rows]}


@app.get("/api/images/{image_id}")
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = db.scalar(
        select(Image).options(joinedload(Image.analysis), defer(Image.data), defer(Image.thumbnail))
        .where(Image.id == image_id)
    )
    if not img:
        raise HTTPException(404, "Image not found")
    return serialize(img)


@app.get("/api/images/{image_id}/file")
def get_file(image_id: int, db: Session = Depends(get_db)):
    img = db.scalar(select(Image).options(defer(Image.thumbnail)).where(Image.id == image_id))
    if not img:
        raise HTTPException(404, "Image not found")
    return Response(img.data, media_type=img.content_type,
                    headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/images/{image_id}/thumbnail")
def get_thumbnail(image_id: int, db: Session = Depends(get_db)):
    img = db.scalar(select(Image).options(defer(Image.data)).where(Image.id == image_id))
    if not img:
        raise HTTPException(404, "Image not found")
    return Response(img.thumbnail, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@app.delete("/api/images/{image_id}", status_code=204)
def delete_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    db.delete(img)
    db.commit()
    return Response(status_code=204)


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Analysis.quality_label, func.count()).group_by(Analysis.quality_label)
    ).all()
    counts = {"ACCEPTABLE": 0, "DEGRADED": 0, "DEFECTIVE": 0}
    counts.update({k: v for k, v in rows})
    avg = db.scalar(select(func.avg(Analysis.quality_score)))
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "average_score": round(float(avg), 1) if avg is not None else None,
    }


@app.get("/api/storage")
def storage(db: Session = Depends(get_db)):
    """Return total bytes currently stored across all uploaded images."""
    total_bytes = db.scalar(select(func.sum(Image.size_bytes))) or 0
    return {
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1_048_576, 2),
    }
