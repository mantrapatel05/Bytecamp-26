import os
import datetime
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("AUTH_SECRET", "depgraph-secret-key-2024")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "depgraph123")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=7)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_credentials(username: str, password: str) -> bool:
    # Check hardcoded admin account first
    if username == AUTH_USERNAME and password == AUTH_PASSWORD:
        return True
    # Then check registered users in the database
    try:
        from backend.chat_db import verify_user
        return verify_user(username, password)
    except Exception:
        return False
