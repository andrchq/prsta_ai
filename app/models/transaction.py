import datetime
from sqlalchemy import BigInteger, String, Float, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Amount in virtual currency (positive = top-up, negative = spend)
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Real cost in USD (for admin analytics)
    real_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Tokens used (input + output) for detailed tracking
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Category: topup, spend_text, spend_image, spend_video, spend_voice, referral_bonus, daily_bonus
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Which model was used (e.g. "openrouter/gpt-4o", "anthropic/claude-3.5-sonnet")
    model_used: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Description / notes
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, user={self.user_id}, amount={self.amount}, cat={self.category})>"
