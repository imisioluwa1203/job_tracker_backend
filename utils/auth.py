import datetime
import jwt
import bcrypt
from functools import wraps
from flask import request, g
from utils.response import error
from config import JWT_SECRET



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
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")