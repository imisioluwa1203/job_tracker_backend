import psycopg2
import psycopg2.extras
from config import DB_PASSWORD, DB_HOST, DB_USER, DB_NAME, DB_PORT


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor
    )