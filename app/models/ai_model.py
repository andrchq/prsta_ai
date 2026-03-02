"""AI Model registry — stores enabled/disabled models parsed from OpenRouter."""

import datetime
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class AIModel(Base):
    """AI model from OpenRouter with enable/disable toggle."""
    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # OpenRouter model ID (e.g. "google/gemini-2.0-flash-001")
    model_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Human-readable name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Short description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pricing per token (USD)
    price_prompt: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_completion: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Context window
    context_length: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)

    # Capabilities: comma-separated (e.g. "text,image" or "text,image,audio")
    input_modalities: Mapped[str] = mapped_column(String(255), default="text", nullable=False)
    output_modalities: Mapped[str] = mapped_column(String(255), default="text", nullable=False)

    # Admin toggle: shown to users or not
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Display order (lower = first)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AIModel({self.model_id}, enabled={self.is_enabled})>"

    @property
    def full_id(self) -> str:
        """LiteLLM-compatible model ID."""
        return f"openrouter/{self.model_id}"

    @property
    def modality_emoji(self) -> str:
        """Emoji representing model capabilities."""
        inp = self.input_modalities or ""
        out = self.output_modalities or ""
        parts = []
        if "text" in inp:
            parts.append("💬")
        if "image" in inp:
            parts.append("🖼")
        if "audio" in inp:
            parts.append("🎤")
        if "image" in out:
            parts.append("→🎨")
        return "".join(parts) or "💬"

    @property
    def price_display(self) -> str:
        """Human-readable price per 1M tokens."""
        p_in = self.price_prompt * 1_000_000
        p_out = self.price_completion * 1_000_000
        return f"${p_in:.2f}/${p_out:.2f} per 1M"
