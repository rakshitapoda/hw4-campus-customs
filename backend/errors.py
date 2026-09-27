"""Safe, consistent error responses for the Campus Customs API.

Every error the API returns has the same shape: {"detail": "<readable message>", "request_id": "<id>"}.
Technical details (stack traces, SQL, file paths, provider messages) are logged server-side with the
request id and never sent to the browser.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger('campus_customs')

MAX_BODY_BYTES = 64 * 1024  # largest valid request (a 2000-char message + 50 history turns) is far smaller
GENERIC_ERROR = 'Something went wrong on our side. Please try again in a moment.'
DB_UNAVAILABLE = 'The Campus Customs catalogue is temporarily unavailable. Please try again in a moment.'


def request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', '-')


def error_response(request: Request, status_code: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={'detail': detail, 'request_id': request_id(request)},
        headers=headers,
    )


def _validation_message(exc: RequestValidationError, field_labels: dict[str, str]) -> str:
    first = exc.errors()[0]
    kind = first.get('type', '')
    loc = [str(p) for p in first.get('loc', ())]
    if kind == 'json_invalid':
        return 'The request body must be valid JSON.'
    if kind == 'missing' and loc == ['body']:
        return 'A request body is required.'
    msg = str(first.get('msg', 'Invalid request.')).removeprefix('Value error, ')
    field = next((p for p in reversed(loc) if p in field_labels), None)
    if kind == 'string_pattern_mismatch':  # don't show the regex itself
        return f'{field_labels.get(field, "That value")} is not valid.'
    if field and kind != 'value_error':
        msg = f'{field_labels[field]}: {msg[0].lower()}{msg[1:]}'
        msg = msg if msg.endswith('.') else msg + '.'
    elif kind == 'missing' and loc:
        msg = f'Missing required field: {loc[-1]}.'
    return msg


def install_error_handling(app: FastAPI, field_labels: dict[str, str]) -> None:
    """Register the request-id / size-limit middleware and the exception handlers.

    Call this before adding CORSMiddleware so CORS stays the outermost layer and error responses
    still carry CORS headers.
    """

    @app.middleware('http')
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = uuid.uuid4().hex[:12]
        length = request.headers.get('content-length', '')
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            response = error_response(request, 413, 'That request is too large. Please send a shorter message.')
        else:
            try:
                response = await call_next(request)
            except Exception:  # last line of defence: never leak a traceback
                logger.exception('Unhandled error [%s] %s %s', request_id(request), request.method, request.url.path)
                response = error_response(request, 500, GENERIC_ERROR)
        response.headers['X-Request-ID'] = request_id(request)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else GENERIC_ERROR
        if exc.status_code == 404 and detail == 'Not Found':
            detail = 'That page or resource was not found.'
        elif exc.status_code == 405:
            detail = 'That action is not allowed here.'
        return error_response(request, exc.status_code, detail, dict(exc.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """One readable message (e.g. "Passwords do not match.") instead of Pydantic's error list."""
        return error_response(request, 400, _validation_message(exc, field_labels))

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
        logger.error('Database error [%s] %s %s: %r', request_id(request), request.method, request.url.path, exc)
        return error_response(request, 503, DB_UNAVAILABLE)


class RateLimiter:
    """Simple in-memory sliding-window limiter (per user id or client IP)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> int | None:
        """Record a hit; return seconds to wait if the limit is exceeded, else None."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return max(1, int(self.window_seconds - (now - hits[0])) + 1)
        hits.append(now)
        return None
