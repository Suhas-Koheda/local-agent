import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from superagent.storage.database import init_db, get_db
from superagent.context.engine import ContextEngine
from superagent.agent.provider import ModelProvider
from superagent.agent.loop import SingleAgent
from superagent.runtime.task_manager import TaskManager
import superagent.tools.builtin  
import superagent.tools.browser  
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Local Personal SuperAgent API", lifespan=lifespan)

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://localhost:8080/v1")
context_engine = ContextEngine(token_budget=4000)
provider = ModelProvider(base_url=LLM_ENDPOINT)
agent = SingleAgent(provider=provider)
task_manager = TaskManager(agent=agent, context_engine=context_engine)


class ChatRequest(BaseModel):
    conversation_id: str = "default_conv"
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    response: str


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "SingleAgent runtime active"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, session: AsyncSession = Depends(get_db)):
    try:
        response_text = await task_manager.execute_task(
            session=session,
            conversation_id=req.conversation_id,
            user_request=req.message,
        )
        return ChatResponse(conversation_id=req.conversation_id, response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))