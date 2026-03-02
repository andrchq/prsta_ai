import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class Subscription(Base):
    """User subscription plans (Free, Pro, Premium, etc.)."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Plan type: free, pro, premium
    plan: Mapped[str] = mapped_column(String(50), nullable=False)

    # Monthly virtual currency bonus included in this plan
    monthly_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    starts_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, user={self.user_id}, plan={self.plan})>"
