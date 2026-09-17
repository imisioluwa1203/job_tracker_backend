import random
import bcrypt
import datetime


def generate_otp():
    return str(random.randint(100000, 999999))


def hash_otp(code):
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_otp(code, code_hash):
    return bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8"))


def otp_expiry():
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=10)