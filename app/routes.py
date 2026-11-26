"""HTTP API and the single web page."""
import hmac
import logging
import random
from datetime import UTC, datetime, timedelta
from functools import wraps

import psycopg
from flask import Blueprint, current_app, jsonify, render_template, request
from psycopg_pool import PoolTimeout
from werkzeug.exceptions import HTTPException

from .observability import LOANS

bp = Blueprint("library", __name__)
log = logging.getLogger("library")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def db():
    return current_app.extensions["db"]


def require_key(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = current_app.config["LIBRARY"].api_key.encode()
        if not hmac.compare_digest(request.headers.get("X-API-Key", "").encode(), expected):
            raise ApiError(401, "missing or invalid API key")
        return view(*args, **kwargs)
    return wrapper


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "a JSON object is required")
    return data


def text(data: dict, key: str, limit: int = 200) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ApiError(400, f"'{key}' must be a non-empty string up to {limit} characters")
    return value.strip()


def integer(data: dict, key: str, low: int = 1, high: int = 2**31 - 1) -> int:
    value = data.get(key)
    if type(value) is not int or not low <= value <= high:
        raise ApiError(400, f"'{key}' must be an integer between {low} and {high}")
    return value


# --- health -----------------------------------------------------------------
@bp.get("/healthz")
def healthz():
    """Liveness: the process answers. Deliberately independent of the database."""
    return {"status": "ok", "version": current_app.config["LIBRARY"].version}


@bp.get("/readyz")
def readyz():
    """Readiness: only receive traffic when the database is reachable."""
    try:
        with db().transaction() as conn:
            conn.execute("SELECT 1 FROM books LIMIT 1")
    except (psycopg.Error, PoolTimeout):
        return {"status": "database unavailable"}, 503
    return {"status": "ready"}


@bp.get("/")
def index():
    return render_template("index.html")


# --- books ------------------------------------------------------------------
@bp.get("/api/books")
def list_books():
    fault_rate = current_app.config["LIBRARY"].fault_rate
    if fault_rate and random.random() < fault_rate:  # nosec B311 - demo fault injection
        raise ApiError(500, "injected fault")
    query = request.args.get("q", "")[:100].replace("\x00", "")
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with db().transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM books WHERE title ILIKE %s OR author ILIKE %s "
            "ORDER BY title LIMIT 200", (pattern, pattern),
        ).fetchall()
    return jsonify(rows)


@bp.post("/api/books")
@require_key
def add_book():
    data = body()
    copies = integer(data, "copies", 1, 10000)
    values = (text(data, "isbn", 20), text(data, "title"), text(data, "author"), copies, copies)
    try:
        with db().transaction() as conn:
            row = conn.execute(
                "INSERT INTO books (isbn, title, author, total_copies, available_copies) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING *", values,
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ApiError(409, "a book with this ISBN already exists") from None
    return row, 201


# --- members (personal data, so every route needs the key) ------------------
@bp.get("/api/members")
@require_key
def list_members():
    with db().transaction() as conn:
        return jsonify(conn.execute("SELECT * FROM members ORDER BY id LIMIT 500").fetchall())


@bp.post("/api/members")
@require_key
def add_member():
    data = body()
    name, email = text(data, "name"), text(data, "email").lower()
    if "@" not in email:
        raise ApiError(400, "'email' is not a valid address")
    try:
        with db().transaction() as conn:
            row = conn.execute(
                "INSERT INTO members (name, email) VALUES (%s, %s) RETURNING *", (name, email),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ApiError(409, "a member with this email already exists") from None
    return row, 201


# --- loans ------------------------------------------------------------------
@bp.get("/api/loans")
@require_key
def list_loans():
    with db().transaction() as conn:
        rows = conn.execute(
            "SELECT l.*, b.title, m.name AS member_name, "
            "       (l.returned_at IS NULL AND l.due_at < now()) AS overdue "
            "FROM loans l JOIN books b ON b.id = l.book_id "
            "JOIN members m ON m.id = l.member_id ORDER BY l.id DESC LIMIT 500"
        ).fetchall()
    return jsonify(rows)


@bp.post("/api/loans")
@require_key
def borrow():
    data = body()
    book_id, member_id = integer(data, "book_id"), integer(data, "member_id")
    due = datetime.now(UTC) + timedelta(days=current_app.config["LIBRARY"].loan_days)
    try:
        with db().transaction() as conn:
            # The conditional UPDATE locks the row, so the last copy cannot be lent twice.
            taken = conn.execute(
                "UPDATE books SET available_copies = available_copies - 1 "
                "WHERE id = %s AND available_copies > 0 RETURNING id", (book_id,),
            ).fetchone()
            if not taken:
                raise ApiError(409, "book not found or no copies available")
            row = conn.execute(
                "INSERT INTO loans (book_id, member_id, due_at) VALUES (%s, %s, %s) RETURNING *",
                (book_id, member_id, due),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ApiError(409, "this member already has this book") from None
    except psycopg.errors.ForeignKeyViolation:
        raise ApiError(404, "member not found") from None
    LOANS.labels("borrow").inc()
    return row, 201


@bp.post("/api/loans/<int:loan_id>/return")
@require_key
def give_back(loan_id: int):
    with db().transaction() as conn:
        row = conn.execute(
            "UPDATE loans SET returned_at = now() "
            "WHERE id = %s AND returned_at IS NULL RETURNING *", (loan_id,),
        ).fetchone()
        if not row:
            raise ApiError(404, "no active loan with this id")
        conn.execute(
            "UPDATE books SET available_copies = available_copies + 1 WHERE id = %s",
            (row["book_id"],),
        )
    LOANS.labels("return").inc()
    return row


# --- errors -----------------------------------------------------------------
@bp.app_errorhandler(ApiError)
def api_error(error: ApiError):
    return {"error": error.message}, error.status


@bp.app_errorhandler(PoolTimeout)
@bp.app_errorhandler(psycopg.OperationalError)
def database_down(_error):
    log.error("database unavailable")
    return {"error": "database unavailable"}, 503


@bp.app_errorhandler(Exception)
def unexpected(error: Exception):
    if isinstance(error, HTTPException):
        return {"error": error.description}, error.code
    log.exception("unhandled error")
    return {"error": "internal server error"}, 500
