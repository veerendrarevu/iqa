from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, DateTime, LargeBinary, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)       # original file
    thumbnail: Mapped[bytes] = mapped_column(LargeBinary)  # 320px JPEG
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis: Mapped["Analysis"] = relationship(
        back_populates="image", uselist=False, cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), unique=True
    )
    quality_score: Mapped[int] = mapped_column(Integer, index=True)
    quality_label: Mapped[str] = mapped_column(String(20), index=True)
    issues: Mapped[list] = mapped_column(JSONB, default=list)

    # raw metrics
    brisque_score: Mapped[float] = mapped_column(Float)
    musiq_score: Mapped[float] = mapped_column(Float)
    sharpness: Mapped[float] = mapped_column(Float)
    brightness: Mapped[float] = mapped_column(Float)
    noise: Mapped[float] = mapped_column(Float)
    dark_pixel_percentage: Mapped[float] = mapped_column(Float)
    bright_pixel_percentage: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    image: Mapped[Image] = relationship(back_populates="analysis")
