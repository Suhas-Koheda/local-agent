import json
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from superagent.agent.provider import ModelProvider
from superagent.storage.database import MessageModel
from superagent.tools.registry import registry


class SingleAgent:
    def __init__(self, provider: ModelProvider, max_iterations: int = 5):
        self.provider = provider
        self.max_iterations = max_iterations

    async def run_task(
        self,
        session: AsyncSession,
        conversation_id: str,
        task_id: str,
        inline_context: List[Dict[str, Any]],
        context_engine: Any,
    ) -> str:
        working_messages = list(inline_context)
        tool_defs = registry.get_tool_definitions()
        executed_tool_calls = set()

        for step in range(self.max_iterations):
            assistant_msg = await self.provider.chat_completion(
                messages=working_messages,
                tools=tool_defs if tool_defs else None,
            )

            tool_calls = assistant_msg.get("tool_calls")
            content = assistant_msg.get("content") or ""

            # Check if model generated tool calls
            if tool_calls:
                # Prevent repeating identical tool calls indefinitely
                tool_signatures = [
                    f"{c['function']['name']}:{c['function'].get('arguments')}"
                    for c in tool_calls
                ]
                signature_key = "|".join(tool_signatures)

                if signature_key in executed_tool_calls:
                    # Duplicate tool call detected: force a final text response pass without tools
                    final_msg = await self.provider.chat_completion(
                        messages=working_messages,
                        tools=None,  # Suppress tools to force text generation
                    )
                    final_text = (
                        final_msg.get("content")
                        or "Tool executions completed successfully."
                    )

                    db_msg = MessageModel(
                        message_id=f"msg_{uuid.uuid4().hex[:10]}",
                        conversation_id=conversation_id,
                        task_id=task_id,
                        role="assistant",
                        content=final_text,
                    )
                    session.add(db_msg)
                    await session.commit()
                    return final_text

                executed_tool_calls.add(signature_key)
                working_messages.append(assistant_msg)

                db_msg = MessageModel(
                    message_id=f"msg_{uuid.uuid4().hex[:10]}",
                    conversation_id=conversation_id,
                    task_id=task_id,
                    role="assistant",
                    content=content,
                    tool_calls=json.dumps(tool_calls),
                )
                session.add(db_msg)
                await session.commit()

                for call in tool_calls:
                    fn_name = call["function"]["name"]
                    raw_args = call["function"].get("arguments", "{}")

                    try:
                        args = (
                            json.loads(raw_args)
                            if isinstance(raw_args, str)
                            else raw_args
                        )
                    except json.JSONDecodeError:
                        args = {}

                    # Guard against hallucinated placeholder spill IDs
                    if fn_name == "read_spill" and args.get("artifact_id") in ["spill_abc123", "spill_12345", "artifact_id"]:
                        continue

                    try:
                        tool_result = await registry.execute(
                            fn_name,
                            arguments=args,
                            session=session,
                            task_id=task_id,
                            context_engine=context_engine,
                        )
                        result_str = (
                            json.dumps(tool_result)
                            if not isinstance(tool_result, str)
                            else tool_result
                        )
                    except Exception as e:
                        result_str = f"Error executing tool '{fn_name}': {str(e)}"

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": fn_name,
                        "content": result_str,
                    }
                    working_messages.append(tool_msg)

                    db_tool_msg = MessageModel(
                        message_id=f"msg_{uuid.uuid4().hex[:10]}",
                        conversation_id=conversation_id,
                        task_id=task_id,
                        role="tool",
                        name=fn_name,
                        content=result_str,
                    )
                    session.add(db_tool_msg)
                    await session.commit()
            else:
                # No tool calls - return final text
                final_text = (
                    content if content.strip() else "Task completed successfully."
                )
                db_msg = MessageModel(
                    message_id=f"msg_{uuid.uuid4().hex[:10]}",
                    conversation_id=conversation_id,
                    task_id=task_id,
                    role="assistant",
                    content=final_text,
                )
                session.add(db_msg)
                await session.commit()
                return final_text

        # If loop reaches max iterations, execute one final text synthesis call
        final_msg = await self.provider.chat_completion(
            messages=working_messages,
            tools=None,
        )
        final_text = final_msg.get("content") or "Task completed tool executions."
        db_msg = MessageModel(
            message_id=f"msg_{uuid.uuid4().hex[:10]}",
            conversation_id=conversation_id,
            task_id=task_id,
            role="assistant",
            content=final_text,
        )
        session.add(db_msg)
        await session.commit()
        return final_text
