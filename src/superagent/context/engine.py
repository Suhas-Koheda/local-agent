import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.superagent.storage.database import MessageModel, SpillArtifactModel, TaskModel

SPILL_DIR = Path("data/spills")


class ContextEngine:
    def __init__(self, token_budget: int = 4000):
        self.token_budget = token_budget
        SPILL_DIR.mkdir(parents=True, exist_ok=True)

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimator (~4 chars per token)."""
        return max(1, len(text) // 4)

    async def spill_content(
        self,
        session: AsyncSession,
        task_id: str | None,
        title: str,
        content: str,
        mime_type: str = "text/plain",
    ) -> str:
        artifact_id = f"art_{uuid.uuid4().hex[:10]}"
        file_path = SPILL_DIR / f"{artifact_id}.txt"
        file_path.write_text(content, encoding="utf-8")
        spill_obj = SpillArtifactModel(
            artifact_id=artifact_id,
            task_id=task_id,
            title=title,
            file_path=str(file_path),
            mime_type=mime_type,
        )
        session.add(spill_obj)
        await session.commit()
        return artifact_id

    async def read_spill(self, session: AsyncSession, artifact_id: str) -> str | None:
        stmt = select(SpillArtifactModel).where(
            SpillArtifactModel.artifact_id == artifact_id
        )
        result = await session.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact:
            path = Path(artifact.file_path)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    async def build_inline_context(
        self, session: AsyncSession, conversation_id: str
    ) -> list[dict[str, Any]]:
        inline_messages: list[dict[str, Any]] = []
        # System Grounding Prompt
        system_prompt = (
            "You are a persistent personal AI SuperAgent with direct access to system tools. "
            "You MUST invoke provided function tools to retrieve real-time data or save information. "
            "NEVER give text instructions asking the user to call functions, and NEVER output static or fake timestamps. "
            "Execute the necessary tool calls immediately."
        )
        inline_messages.append({"role": "system", "content": system_prompt})
        used_tokens = self.estimate_tokens(system_prompt)
        task_stmt = (
            select(TaskModel)
            .where(
                TaskModel.conversation_id == conversation_id,
                TaskModel.status == "completed",
            )
            .order_by(desc(TaskModel.completed_at))
            .limit(5)
        )
        task_results = await session.execute(task_stmt)
        completed_tasks = task_results.scalars().all()
        for task in completed_tasks:
            if task.result_summary:
                summary_text = (
                    f"[Past Task Memory] Request: {task.user_request} | "
                    f"Result: {task.result_summary}"
                )
                tokens = self.estimate_tokens(summary_text)
                if used_tokens + tokens <= self.token_budget:
                    inline_messages.append(
                        {"role": "assistant", "content": summary_text}
                    )
                    used_tokens += tokens
        msg_stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(desc(MessageModel.created_at))
            .limit(20)
        )
        msg_results = await session.execute(msg_stmt)
        recent_messages = msg_results.scalars().all()
        budget_messages = []
        for msg in recent_messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.name:
                msg_dict["name"] = msg.name
            if msg.tool_calls:
                msg_dict["tool_calls"] = json.loads(msg.tool_calls)

            msg_tokens = self.estimate_tokens(msg.content)
            if used_tokens + msg_tokens > self.token_budget:
                break

            used_tokens += msg_tokens
            budget_messages.append(msg_dict)

        # Preserve chronological order for the message chain
        inline_messages.extend(reversed(budget_messages))
        return inline_messages
