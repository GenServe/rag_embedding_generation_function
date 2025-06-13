from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict
from uuid import UUID
from jose import JWTError
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from datetime import datetime, timedelta, timezone
from .config import settings


from jose import JWTError, jwt


# Initialize HTTPBearer
security = HTTPBearer()

def get_current_user(auth_header: str) -> Dict:
    token = auth_header.split(" ")[1] if " " in auth_header else auth_header

    payload = decode_access_token(token)  # Will raise HTTPException if token is bad

    if not payload or "email" not in payload:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")

    try:
        payload["user_id_uuid"] = UUID(payload["user_id"])
        payload["id"] = payload["user_id"]
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid user_id format")

    return payload


def decode_access_token(token: str):
    try:
        if not token:
            print("Token is empty or None")
            return None

        payload = jwt.decode(
            token.strip(),
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="genserve.ai"
        )

        print("Decoded Payload:", payload)
        return payload
    
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )