import datetime
import uuid
from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superagent.tools.registry import registry
from superagent.storage.database import MemoryModel


@registry.register(
    name="get_current_time",
    description="Returns the current timestamp in ISO format.",
    parameters={"type": "object", "properties": {}, "required": []},
)
async def get_current_time() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@registry.register(
    name="save_memory",
    description="Persists important fact, user preference, or experience memory across sessions.",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact or experience description to store."},
            "memory_type": {
                "type": "string",
                "enum": ["information", "experience"],
                "description": "Category of memory.",
            },
        },
        "required": ["content", "memory_type"],
    },
)
async def save_memory(
    content: str, memory_type: str, session: AsyncSession, **kwargs
) -> str:
    memory_id = f"mem_{uuid.uuid4().hex[:10]}"
    memory = MemoryModel(
        memory_id=memory_id,
        memory_type=memory_type,
        content=content,
    )
    session.add(memory)
    
    # Fix: Use session.execute(text(...)) instead of session.exec_driver_sql(...)
    await session.execute(
        text("INSERT INTO memories_fts (memory_id, content) VALUES (:id, :content)"),
        {"id": memory_id, "content": content},
    )
    await session.commit()
    return f"Memory successfully saved with ID: {memory_id}"


@registry.register(
    name="read_spill",
    description="Reads full content from an externalized spill artifact using its artifact_id.",
    parameters={
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "description": "Artifact ID (e.g., art_12345)"}
        },
        "required": ["artifact_id"],
    },
)
async def read_spill(
    artifact_id: str, session: AsyncSession, context_engine: Any, **kwargs
) -> str:
    content = await context_engine.read_spill(session, artifact_id)
    if content is None:
        return f"Spill artifact '{artifact_id}' not found."
    return content