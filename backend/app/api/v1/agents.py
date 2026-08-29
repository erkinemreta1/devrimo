from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.session import get_db
from app.schemas import AgentOut

router = APIRouter()


@router.get("/me", response_model=AgentOut)
async def get_my_agent(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await manager.get_agent_or_404(db, user.id)
    return AgentOut.from_model(agent)


@router.post("/provision", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def provision_agent(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await manager.provision(db, user.id)
    return AgentOut.from_model(agent)


@router.post("/start", response_model=AgentOut)
async def start_agent(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await manager.get_agent_or_404(db, user.id)
    agent = await manager.start(db, agent)
    return AgentOut.from_model(agent)


@router.post("/stop", response_model=AgentOut)
async def stop_agent(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await manager.get_agent_or_404(db, user.id)
    agent = await manager.stop(db, agent)
    return AgentOut.from_model(agent)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    agent = await manager.get_agent_or_404(db, user.id)
    await manager.destroy(db, agent)
