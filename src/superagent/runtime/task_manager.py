import uuid
import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superagent.storage.database import TaskModel, MessageModel, ConversationModel
from superagent.context.engine import ContextEngine
from superagent.agent.loop import SingleAgent
from superagent.tools.builtin import save_memory


class TaskManager:
    def __init__(self, agent: SingleAgent, context_engine: ContextEngine):
        self.agent = agent
        self.context_engine = context_engine

    async def execute_task(
        self, session: AsyncSession, conversation_id: str, user_request: str
    ) -> str:
        stmt = select(ConversationModel).where(ConversationModel.conversation_id == conversation_id)
        res = await session.execute(stmt)
        conv = res.scalar_one_or_none()
        if not conv:
            conv = ConversationModel(
                conversation_id=conversation_id,
                agent_id="personal_superagent",
                title=user_request[:30],
            )
            session.add(conv)
            await session.commit()

        task_id = f"task_{uuid.uuid4().hex[:10]}"
        task = TaskModel(
            task_id=task_id,
            conversation_id=conversation_id,
            status="RUNNING",
            user_request=user_request,
        )
        session.add(task)

        user_msg = MessageModel(
            message_id=f"msg_{uuid.uuid4().hex[:10]}",
            conversation_id=conversation_id,
            task_id=task_id,
            role="user",
            content=user_request,
        )
        session.add(user_msg)
        await session.commit()

        try:
            inline_context = await self.context_engine.build_inline_context(
                session, conversation_id
            )

            final_response = await self.agent.run_task(
                session=session,
                conversation_id=conversation_id,
                task_id=task_id,
                inline_context=inline_context,
                context_engine=self.context_engine,
            )

            task.status = "COMPLETED"
            task.result_summary = final_response[:300]
            task.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await session.commit()

            await save_memory(
                content=f"Task: {user_request} | Outcome: {final_response[:200]}",
                memory_type="experience",
                session=session,
            )

            return final_response

        except Exception as e:
            task.status = "FAILED"
            task.result_summary = f"Error: {str(e)}"
            await session.commit()
            raise e