
import jwt
import bcrypt
from functools import wraps
from flask import request, g
from utils.response import error
from config import JWT_SECRET
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from db import get_connection



def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return error("UNAUTHORIZED", "Missing or malformed Authorization header", 401)

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return error("UNAUTHORIZED", "Token has expired", 401)
        except jwt.InvalidTokenError:
            return error("UNAUTHORIZED", "Invalid token", 401)

        g.current_user = payload
        return f(*args, **kwargs)

    return wrapper

def hash_password(plain_password):
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(plain_password, password_hash):
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id, role):
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")




def generate_refresh_token():
    return secrets.token_urlsafe(32)


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_refresh_token(user_id):
    raw_token = generate_refresh_token()
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user_id, token_hash, expires_at)
    )
    conn.commit()
    cur.close()
    conn.close()

    return raw_token


def verify_refresh_token(raw_token):
    token_hash = hash_token(raw_token)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM refresh_tokens
        WHERE token_hash = %s
          AND revoked = FALSE
          AND expires_at > NOW()
        """,
        (token_hash,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return row


def revoke_refresh_token(token_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s",
        (token_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

def revoke_all_refresh_tokens_for_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = %s AND revoked = FALSE",
        (user_id,)
    )
    conn.commit()
    cur.close()
    conn.close()