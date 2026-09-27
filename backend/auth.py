"""Account creation and login against the existing users table."""

from __future__ import annotations

import re
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from db import get_connection
from security import (
    burn_password_check,
    create_session_token,
    hash_password,
    read_session_token,
    verify_password,
)

MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_CHARS = 128
MAX_NAME_CHARS = 50
MAX_EMAIL_CHARS = 254
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
# Failed-login throttle: at most this many failures per email within the window.
MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
INVALID_CREDENTIALS = 'Incorrect email or password.'

router = APIRouter(prefix='/api/auth', tags=['auth'])
_failed_logins: dict[str, deque[float]] = defaultdict(deque)


# ---------- Models ----------

def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > MAX_EMAIL_CHARS or not EMAIL_PATTERN.match(email):
        raise ValueError('Enter a valid email address.')
    return email


class SignupRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    last_name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    email: str
    password: str = Field(min_length=MIN_PASSWORD_CHARS, max_length=MAX_PASSWORD_CHARS)
    confirm_password: str

    @field_validator('first_name', 'last_name')
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Name cannot be blank.')
        return v

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return _normalize_email(v)

    @model_validator(mode='after')
    def passwords_match(self) -> SignupRequest:
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match.')
        return self


class LoginRequest(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_CHARS)
    password: str = Field(max_length=MAX_PASSWORD_CHARS)

    @field_validator('email')
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class PublicUser(BaseModel):
    """The only user fields ever sent to the browser; never the password hash."""

    id: int
    first_name: str | None
    last_name: str | None
    name: str
    email: str


class AuthResponse(BaseModel):
    message: str
    token: str
    user: PublicUser


def _public_user(row: sqlite3.Row) -> PublicUser:
    return PublicUser(
        id=row['id'],
        first_name=row['first_name'],
        last_name=row['last_name'],
        name=row['name'],
        email=row['email'],
    )


# ---------- Failed-login throttle ----------

def _recent_failures(email: str) -> deque[float]:
    attempts = _failed_logins[email]
    cutoff = time.time() - FAILED_LOGIN_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


# ---------- Routes ----------

@router.post('/signup', response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> AuthResponse:
    password_hash = hash_password(body.password)
    full_name = f'{body.first_name} {body.last_name}'
    try:
        with get_connection(write=True) as conn:
            cur = conn.execute(
                'INSERT INTO users (name, email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?, ?)',
                (full_name, body.email, password_hash, body.first_name, body.last_name),
            )
            row = conn.execute(
                'SELECT id, name, email, first_name, last_name FROM users WHERE id = ?', (cur.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError:
        # users.email is UNIQUE
        raise HTTPException(status.HTTP_409_CONFLICT, 'An account with this email already exists.') from None

    user = _public_user(row)
    return AuthResponse(
        message=f'Welcome to Campus Customs, {user.first_name}! Your account has been created.',
        token=create_session_token(user.id),
        user=user,
    )


@router.post('/login', response_model=AuthResponse)
def login(body: LoginRequest) -> AuthResponse:
    failures = _recent_failures(body.email)
    if len(failures) >= MAX_FAILED_LOGINS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            'Too many failed attempts. Please wait a few minutes and try again.',
        )

    with get_connection() as conn:
        row = conn.execute(
            'SELECT id, name, email, first_name, last_name, password_hash FROM users WHERE lower(email) = ?',
            (body.email,),
        ).fetchone()

    if row is None:
        burn_password_check(body.password)
        ok = False
    else:
        ok = verify_password(body.password, row['password_hash'])

    if not ok:
        failures.append(time.time())
        # Same message whether the email or the password was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)

    _failed_logins.pop(body.email, None)
    user = _public_user(row)
    return AuthResponse(
        message=f'Welcome back, {user.first_name or user.name}!',
        token=create_session_token(user.id),
        user=user,
    )


def current_user_id(authorization: str | None) -> int | None:
    """Resolve 'Authorization: Bearer <token>' to a user id (for use by other routes later)."""
    if not authorization or not authorization.startswith('Bearer '):
        return None
    return read_session_token(authorization.removeprefix('Bearer ').strip())


@router.get('/me', response_model=PublicUser)
def me(authorization: str | None = Header(default=None)) -> PublicUser:
    user_id = current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Not logged in.')
    with get_connection() as conn:
        row = conn.execute(
            'SELECT id, name, email, first_name, last_name FROM users WHERE id = ?', (user_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Not logged in.')
    return _public_user(row)
