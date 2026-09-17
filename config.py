import os
from dotenv import load_dotenv

load_dotenv()

DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_NAME = os.environ.get("DB_NAME")
DB_PORT = os.environ.get("DB_PORT")

JWT_SECRET = os.environ.get("JWT_SECRET")