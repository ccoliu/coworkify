import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API_KEY_NAME = "X-API-Key" # metadata
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

#讀取允許的 API Keys
ALLOWED_API_KEYS = {k.strip() for k in os.getenv("API_KEYS", "changeme_local_dev_key").split(",") if k.strip()}

def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key"
        )
    
    if api_key not in ALLOWED_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )
    return api_key

