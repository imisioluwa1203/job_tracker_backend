from flask import Blueprint, request
from db import get_connection
from utils.response import success, error
from utils.auth import hash_password,check_password,create_access_token,require_auth,create_refresh_token,verify_refresh_token,revoke_refresh_token, revoke_all_refresh_tokens_for_user
from utils.otp import generate_otp, hash_otp, otp_expiry, check_otp
import datetime
from flask import g


auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    body = request.get_json()

    full_name = body.get("full_name")
    email = body.get("email")
    password = body.get("password")

    if not full_name or not email or not password:
        return error("VALIDATION_ERROR", "full_name, email, and password are required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_user = cur.fetchone()

    if existing_user:
        cur.close()
        conn.close()
        return error("CONFLICT", "An account with this email already exists", 409)

    password_hash = hash_password(password)

    cur.execute(
        "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id, email",
        (full_name, email, password_hash)
    )
    new_user = cur.fetchone()

    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code)

    cur.execute(
        "INSERT INTO otp_codes (user_id, code_hash, purpose, expires_at) VALUES (%s, %s, %s, %s)",
        (new_user["id"], otp_hash, "verify_email", otp_expiry())
    )
    conn.commit()

    cur.close()
    conn.close()

    print(f"[DEV ONLY] OTP for {email}: {otp_code}")

    return success(new_user, message="OTP sent to email", status=201)




@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp_route():
    body = request.get_json()

    email = body.get("email")
    otp = body.get("otp")

    if not email or not otp:
        return error("VALIDATION_ERROR", "email and otp are required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        return error("NOT_FOUND", "No account with this email", 404)

    cur.execute(
        """
        SELECT * FROM otp_codes
        WHERE user_id = %s AND purpose = 'verify_email' AND used = FALSE
        ORDER BY created_at DESC LIMIT 1
        """,
        (user["id"],)
    )
    otp_row = cur.fetchone()

    if not otp_row:
        cur.close()
        conn.close()
        return error("INVALID_OTP", "No pending verification code for this account")

    if datetime.datetime.utcnow() > otp_row["expires_at"]:
        cur.close()
        conn.close()
        return error("OTP_EXPIRED", "This code has expired, request a new one")

    if not check_otp(otp, otp_row["code_hash"]):
        cur.close()
        conn.close()
        return error("INVALID_OTP", "Incorrect code")

    cur.execute("UPDATE otp_codes SET used = TRUE WHERE id = %s", (otp_row["id"],))
    cur.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user["id"],))
    conn.commit()

    cur.close()
    conn.close()

    return success(message="Email verified successfully")





@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json()

    email = body.get("email")
    password = body.get("password")

    if not email or not password:
        return error("VALIDATION_ERROR", "email and password are required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user or not check_password(password, user["password_hash"]):
        return error("UNAUTHORIZED", "Invalid email or password", 401)

    access_token = create_access_token(user["id"], user["role"])
    refresh_token =create_refresh_token(user["id"])

    return success({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"]
        }
    }, message="Login successful")




@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, full_name, email, role, created_at FROM users WHERE id = %s",
        (g.current_user["user_id"],)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    return success(user)

@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    body = request.get_json()
    old_token = body.get("refresh_token")

    if not old_token:
        return error(code="VALIDATION_ERROR", message="refresh_token is required")

    token_row = verify_refresh_token(old_token)

    if not token_row:
        return error(code="UNAUTHORIZED", message="Invalid or expired refresh token", status=401)

    # Rotate: kill the old one, issue new ones
    revoke_refresh_token(token_row["id"])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (token_row["user_id"],))
    user = cur.fetchone()
    cur.close()
    conn.close()

    new_access_token = create_access_token(user["id"], user["role"])
    new_refresh_token = create_refresh_token(user["id"])

    return success(data={
        "access_token": new_access_token,
        "refresh_token": new_refresh_token
    })

@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    body = request.get_json()
    email = body.get("email")

    if not email:
        return error(code="VALIDATION_ERROR", message="email is required")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if user:
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)

        cur.execute(
            "INSERT INTO otp_codes (user_id, code_hash, purpose, expires_at) VALUES (%s, %s, %s, %s)",
            (user["id"], otp_hash, "reset_password", otp_expiry())
        )
        conn.commit()

        print(f"[DEV ONLY] Password reset OTP for {email}: {otp_code}")

    cur.close()
    conn.close()

    return success(message="If that email exists, an OTP has been sent")

@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    body = request.get_json()
    email = body.get("email")
    otp = body.get("otp")
    new_password = body.get("new_password")

    if not email or not otp or not new_password:
        return error(code="VALIDATION_ERROR", message="email, otp, and new_password are required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        return error(code="UNAUTHORIZED", message="Invalid or expired OTP", status=401)

    cur.execute(
        """
        SELECT * FROM otp_codes
        WHERE user_id = %s
          AND purpose = 'reset_password'
          AND used = FALSE
          AND expires_at > NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user["id"],)
    )
    otp_row = cur.fetchone()

    if not otp_row or not check_otp(otp, otp_row["code_hash"]):
        cur.close()
        conn.close()
        return error(code="UNAUTHORIZED", message="Invalid or expired OTP", status=401)

    new_password_hash = hash_password(new_password)

    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_password_hash, user["id"]))
    cur.execute("UPDATE otp_codes SET used = TRUE WHERE id = %s", (otp_row["id"],))
    conn.commit()
    cur.close()
    conn.close()

    revoke_all_refresh_tokens_for_user(user["id"])

    return success(message="Password reset successful")

@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    body = request.get_json()
    email = body.get("email")

    if not email:
        return error(code="VALIDATION_ERROR", message="email is required")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, is_verified FROM users WHERE email = %s", (email,))
    user = cur.fetchone()

    if user and not user["is_verified"]:
        # Invalidate any old unused verify_email OTPs for this user
        cur.execute(
            "UPDATE otp_codes SET used = TRUE WHERE user_id = %s AND purpose = 'verify_email' AND used = FALSE",
            (user["id"],)
        )

        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)

        cur.execute(
            "INSERT INTO otp_codes (user_id, code_hash, purpose, expires_at) VALUES (%s, %s, %s, %s)",
            (user["id"], otp_hash, "verify_email", otp_expiry())
        )
        conn.commit()

        print(f"[DEV ONLY] Resent verify_email OTP for {email}: {otp_code}")

    cur.close()
    conn.close()

    return success(message="If that email exists and is unverified, a new OTP has been sent")