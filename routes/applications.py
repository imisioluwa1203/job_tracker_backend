from flask import Blueprint, request, g
from db import get_connection
from utils.response import success, error
from utils.auth import require_auth
from datetime import date



import csv
import io
from flask import Response


applications_bp = Blueprint("applications", __name__, url_prefix="/api/v1/applications")


@applications_bp.route("", methods=["POST"])
@require_auth
def create_application():
    body = request.get_json()

    company = body.get("company")
    role = body.get("role")
    date_applied = body.get("date_applied") or str(date.today())
    job_link = body.get("job_link")
    contact_person = body.get("contact_person")

    if not company or not role:
        return error(code="VALIDATION_ERROR", message="company and role are required")

    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO applications (user_id, company, role, date_applied, job_link, contact_person)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (user_id, company, role, date_applied, job_link, contact_person)
    )
    new_application = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return success(data=new_application, message="Application created", status=201)

@applications_bp.route("", methods=["GET"])
@require_auth
def list_applications():
    user_id = g.current_user["user_id"]

    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)

    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 10

    offset = (page - 1) * limit

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS total FROM applications WHERE user_id = %s", (user_id,))
    total = cur.fetchone()["total"]

    cur.execute(
        """
        SELECT * FROM applications
        WHERE user_id = %s
        ORDER BY date_applied DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, limit, offset)
    )
    applications = cur.fetchall()

    cur.close()
    conn.close()

    total_pages = (total + limit - 1) // limit

    return success(data={
        "applications": applications,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages
        }
    })

@applications_bp.route("/<int:application_id>", methods=["GET"])
@require_auth
def get_application(application_id):
    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    application = cur.fetchone()

    if not application:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    cur.execute(
        "SELECT * FROM application_notes WHERE application_id = %s ORDER BY created_at DESC",
        (application_id,)
    )
    notes = cur.fetchall()

    cur.close()
    conn.close()

    application["notes"] = notes

    return success(data=application)

@applications_bp.route("/<int:application_id>", methods=["PATCH"])
@require_auth
def update_application(application_id):
    user_id = g.current_user["user_id"]
    body = request.get_json()

    allowed_fields = ["company", "role", "date_applied", "job_link", "contact_person"]
    updates = {key: body[key] for key in allowed_fields if key in body}

    if not updates:
        return error(code="VALIDATION_ERROR", message="At least one field must be provided to update")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    existing = cur.fetchone()

    if not existing:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    set_clause = ", ".join(f"{field} = %s" for field in updates)
    values = list(updates.values())
    values.append(application_id)

    cur.execute(
        f"""
        UPDATE applications
        SET {set_clause}, updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        values
    )
    updated_application = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return success(data=updated_application, message="Application updated")


VALID_STATUSES = ["applied", "interviewing", "offer", "rejected"]


@applications_bp.route("/<int:application_id>/status", methods=["PATCH"])
@require_auth
def update_application_status(application_id):
    user_id = g.current_user["user_id"]
    body = request.get_json()

    new_status = body.get("status")

    if not new_status:
        return error(code="VALIDATION_ERROR", message="status is required")

    if new_status not in VALID_STATUSES:
        return error(
            code="VALIDATION_ERROR",
            message=f"status must be one of: {', '.join(VALID_STATUSES)}"
        )

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    existing = cur.fetchone()

    if not existing:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    cur.execute(
        """
        UPDATE applications
        SET status = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (new_status, application_id)
    )
    updated_application = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return success(data=updated_application, message="Status updated")

@applications_bp.route("/<int:application_id>", methods=["DELETE"])
@require_auth
def delete_application(application_id):
    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    existing = cur.fetchone()

    if not existing:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    cur.execute("DELETE FROM applications WHERE id = %s", (application_id,))
    conn.commit()
    cur.close()
    conn.close()

    return success(message="Application deleted")

@applications_bp.route("/<int:application_id>/notes", methods=["POST"])
@require_auth
def add_note(application_id):
    user_id = g.current_user["user_id"]
    body = request.get_json()

    content = body.get("content")

    if not content:
        return error(code="VALIDATION_ERROR", message="content is required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    existing = cur.fetchone()

    if not existing:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    cur.execute(
        "INSERT INTO application_notes (application_id, content) VALUES (%s, %s) RETURNING *",
        (application_id, content)
    )
    new_note = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return success(data=new_note, message="Note added", status=201)


@applications_bp.route("/<int:application_id>/notes/<int:note_id>", methods=["DELETE"])
@require_auth
def delete_note(application_id, note_id):
    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM applications WHERE id = %s AND user_id = %s",
        (application_id, user_id)
    )
    existing_app = cur.fetchone()

    if not existing_app:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Application not found", status=404)

    cur.execute(
        "SELECT id FROM application_notes WHERE id = %s AND application_id = %s",
        (note_id, application_id)
    )
    existing_note = cur.fetchone()

    if not existing_note:
        cur.close()
        conn.close()
        return error(code="NOT_FOUND", message="Note not found", status=404)

    cur.execute("DELETE FROM application_notes WHERE id = %s", (note_id,))
    conn.commit()
    cur.close()
    conn.close()

    return success(message="Note deleted")

@applications_bp.route("/stale", methods=["GET"])
@require_auth
def get_stale_applications():
    user_id = g.current_user["user_id"]

    days = request.args.get("days", default=30, type=int)

    if days < 1:
        days = 30

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT * FROM applications
        WHERE user_id = %s
          AND status = 'applied'
          AND updated_at < NOW() - (%s * INTERVAL '1 day')
        ORDER BY updated_at ASC
        """,
        (user_id, days)
    )
    stale_applications = cur.fetchall()

    cur.close()
    conn.close()

    return success(data={
        "applications": stale_applications,
        "days_threshold": days,
        "count": len(stale_applications)
    })

@applications_bp.route("/stats", methods=["GET"])
@require_auth
def get_dashboard_stats():
    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'applied') AS applied,
            COUNT(*) FILTER (WHERE status = 'interviewing') AS interviewing,
            COUNT(*) FILTER (WHERE status = 'offer') AS offer,
            COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
            COUNT(*) FILTER (WHERE date_applied >= NOW() - INTERVAL '7 days') AS this_week,
            COUNT(*) FILTER (WHERE date_applied >= NOW() - INTERVAL '30 days') AS this_month
        FROM applications
        WHERE user_id = %s
        """,
        (user_id,)
    )
    stats = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) AS stale_count FROM applications
        WHERE user_id = %s
          AND status = 'applied'
          AND updated_at < NOW() - INTERVAL '30 days'
        """,
        (user_id,)
    )
    stale = cur.fetchone()

    cur.close()
    conn.close()

    total = stats["total"]
    responded = stats["interviewing"] + stats["offer"] + stats["rejected"]
    response_rate = round((responded / total * 100), 1) if total > 0 else 0

    return success(data={
        "total_applications": total,
        "by_status": {
            "applied": stats["applied"],
            "interviewing": stats["interviewing"],
            "offer": stats["offer"],
            "rejected": stats["rejected"]
        },
        "this_week": stats["this_week"],
        "this_month": stats["this_month"],
        "stale_count": stale["stale_count"],
        "response_rate_percent": response_rate
    })


@applications_bp.route("/export", methods=["GET"])
@require_auth
def export_applications_csv():
    user_id = g.current_user["user_id"]

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT company, role, status, date_applied, job_link, contact_person, created_at
        FROM applications
        WHERE user_id = %s
        ORDER BY date_applied DESC
        """,
        (user_id,)
    )
    applications = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Company", "Role", "Status", "Date Applied", "Job Link", "Contact Person", "Created At"])

    for app in applications:
        writer.writerow([
            app["company"],
            app["role"],
            app["status"],
            app["date_applied"],
            app["job_link"],
            app["contact_person"],
            app["created_at"]
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications_export.csv"}
    )