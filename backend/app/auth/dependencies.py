from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.directory import touch_account
from app.auth.jwt import AuthenticatedUser, verify_access_token
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")
    user = verify_access_token(credentials.credentials)
    await touch_account(db, user.id, user.email)
    return user
