import datetime
from sqlalchemy import BigInteger, String, Float, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Balance in internal virtual currency (e.g. "Neurons")
    balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Referral system
    referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    referred_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships (lazy load to avoid pulling all data on every auth check)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", lazy="select")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user", lazy="select")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", lazy="select")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg={self.telegram_id}, balance={self.balance})>"
