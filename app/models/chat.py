import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class ChatSession(Base):
    """Represents a separate conversation thread (like 'New Chat' in ChatGPT)."""
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), default="Новый чат", nullable=False)

    # Which AI model is selected for this session
    model_id: Mapped[str] = mapped_column(String(255), default="openrouter/google/gemini-2.0-flash-001", nullable=False)

    # System prompt / persona for this session
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Telegram forum topic thread ID (for topic-per-chat mode)
    topic_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", lazy="selectin", order_by="ChatMessage.created_at"
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, user={self.user_id}, title={self.title})>"


class ChatMessage(Base):
    """Individual message in a chat session."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)

    # 'system', 'user', 'assistant'
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token counts for this specific message
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role}, session={self.session_id})>"
