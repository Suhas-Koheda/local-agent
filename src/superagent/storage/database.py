import os
from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy import String, Text, ForeignKey, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

DB_PATH = Path("data/superagent.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

class ConversationModel(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class TaskModel(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.conversation_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp())
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

class MessageModel(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.conversation_id"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String, ForeignKey("tasks.task_id"), nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp())

class SpillArtifactModel(Base):
    __tablename__ = "spill_artifacts"

    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String, ForeignKey("tasks.task_id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, default="text/plain")
    created_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp())

class MemoryModel(Base):
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    memory_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=func.current_timestamp())

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Fix: exec_driver_sql works directly on conn (Connection)
        await conn.exec_driver_sql("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            memory_id, content
        );
        """)