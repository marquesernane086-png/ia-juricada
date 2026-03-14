"""Auth dependency — API Key authentication."""

import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_api_key() -> str:
    return os.environ.get("API_KEY", "")


async def require_api_key(key: str = Security(api_key_header)):
    """Valida API key. Se API_KEY env estiver vazia, auth fica desabilitada (dev mode)."""
    api_key = _get_api_key()
    if not api_key:
        return  # Dev mode: sem auth
    if key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inv\u00e1lida ou ausente",
            headers={"WWW-Authenticate": "ApiKey"},
        )
