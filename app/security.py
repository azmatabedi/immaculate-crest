import time, bcrypt, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from .config import SECRET_KEY

def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()

def check_pw(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode()[:72], h.encode())
    except ValueError:
        return False

def make_token(username: str) -> str:
    return jwt.encode({"sub": username, "exp": int(time.time()) + 8 * 3600}, SECRET_KEY, "HS256")

bearer = HTTPBearer(auto_error=False)

def admin_required(cred=Depends(bearer)):
    try:
        return jwt.decode(cred.credentials, SECRET_KEY, ["HS256"])["sub"]
    except Exception:
        raise HTTPException(401, "Not authenticated")
