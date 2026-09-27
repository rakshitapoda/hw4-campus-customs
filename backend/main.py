"""Campus Customs backend: catalogue, images, authentication, and the PydanticAI chat agent.

Run from the backend folder:
    cd backend
    ../.venv/bin/uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Header, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic_ai.exceptions import UsageLimitExceeded

import agent as chat_agent
import memory
from auth import current_user_id
from auth import router as auth_router
from db import DATA_DIR, get_connection
from errors import DB_UNAVAILABLE, RateLimiter, install_error_handling
from models import (
    MAX_HISTORY_TURNS,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    CustomerContext,
    ProductDetail,
    ProductSummary,
)
from tools import build_product_cards, load_inventory, product_summary

PRODUCTS_IMAGE_DIR = DATA_DIR / 'products'
MEDIA_URL_PREFIX = '/media/products'
FRONTEND_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']
PRODUCT_ID_PATTERN = r'^[a-z0-9]+(?:-[a-z0-9]+)*$'
CHAT_TIMEOUT_SECONDS = 60  # the whole agent run, including tool calls
CHAT_RATE_LIMIT = 15  # messages per shopper (user id or IP) ...
CHAT_RATE_WINDOW_SECONDS = 60  # ... per minute

logger = logging.getLogger('campus_customs')

app = FastAPI(title='Campus Customs API')

FIELD_LABELS = {
    'first_name': 'First name',
    'last_name': 'Last name',
    'email': 'Email',
    'password': 'Password',
    'confirm_password': 'Confirm password',
    'message': 'Message',
    'history': 'Chat history',
    'page_context': 'Page context',
    'product_id': 'Product id',
    'q': 'Search',
}

# Error handling first, so CORS (added next) is the outermost layer and errors keep CORS headers.
install_error_handling(app, FIELD_LABELS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=['GET', 'POST', 'DELETE'],
    allow_headers=['Content-Type', 'Authorization'],
    expose_headers=['X-Request-ID', 'Retry-After'],
)
chat_limiter = RateLimiter(CHAT_RATE_LIMIT, CHAT_RATE_WINDOW_SECONDS)

app.include_router(auth_router)

# Only the product photo folder is exposed, never the data/ folder that holds the database.
app.mount(MEDIA_URL_PREFIX, StaticFiles(directory=PRODUCTS_IMAGE_DIR), name='product-images')

@app.get('/api/health')
def health() -> JSONResponse:
    """Liveness plus a real database check, so the frontend (and ops) can tell what is down."""
    try:
        with get_connection() as conn:
            conn.execute('SELECT 1 FROM catalogue LIMIT 1').fetchone()
        database = 'ok'
    except Exception:
        logger.exception('Health check: database unavailable')
        database = 'unavailable'
    body = {'status': 'ok' if database == 'ok' else 'degraded', 'database': database,
            'chat_model': chat_agent.model_description()}
    if database != 'ok':
        body['detail'] = DB_UNAVAILABLE
    return JSONResponse(status_code=200 if database == 'ok' else 503, content=body)


# ---------- Catalogue ----------

@app.get('/api/products', response_model=list[ProductSummary])
def list_products(
    q: str | None = Query(default=None, max_length=100, description='Search name, type, tags'),
) -> list[ProductSummary]:
    sql = 'SELECT * FROM catalogue'
    params: list[str] = []
    if q:
        like = f'%{q.strip()}%'
        sql += ' WHERE name LIKE ? OR garment_type LIKE ? OR search_tags LIKE ? OR colors LIKE ?'
        params = [like, like, like, like]
    sql += ' ORDER BY name'
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        stock = load_inventory(conn)
    return [product_summary(r, stock.get(r['product_id'], [])) for r in rows]


@app.get('/api/products/{product_id}', response_model=ProductDetail)
def get_product(
    product_id: str = Path(max_length=100, pattern=PRODUCT_ID_PATTERN,
                           description='Lowercase slug, e.g. basic-hoodie-big-yale'),
) -> ProductDetail:
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM catalogue WHERE product_id = ?', (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail='We couldn’t find that product. It may no longer be in the catalogue.')
        sizes = load_inventory(conn, [product_id]).get(product_id, [])
    return ProductDetail(**product_summary(row, sizes).model_dump(), inventory=sizes)


# ---------- Chat (PydanticAI agent + customer memory) ----------

def _authenticated_customer(authorization: str | None) -> tuple[int, CustomerContext] | None:
    """Return (user_id, customer) for a valid session, None for guests, and 401 for a bad/expired token."""
    if not authorization:
        return None
    user_id = current_user_id(authorization)
    customer = memory.get_customer(user_id) if user_id is not None else None
    if user_id is None or customer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Your session has expired. Please log in again.')
    return user_id, customer


@app.post('/api/chat', response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest, authorization: str | None = Header(default=None)) -> ChatResponse:
    """Send the shopper's message to the PydanticAI agent with customer, history, and page context."""
    auth = _authenticated_customer(authorization)
    limit_key = f'user:{auth[0]}' if auth else f'ip:{request.client.host if request.client else "unknown"}'
    if (wait := chat_limiter.check(limit_key)) is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f'You’re sending messages very quickly. Please wait about {wait} seconds and try again.',
            headers={'Retry-After': str(wait)},
        )
    page = memory.resolve_page_context(body.page_context)
    if auth:
        user_id, customer = auth
        history = memory.recent_turns(user_id, MAX_HISTORY_TURNS)  # server-side history, not client-sent
    else:
        customer, history = None, body.history  # guests: in-tab history only, never stored

    try:
        response = await asyncio.wait_for(
            chat_agent.run_chat(body.message, history, customer=customer, page=page), CHAT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning('Chat timed out after %ss [%s]', CHAT_TIMEOUT_SECONDS, request.state.request_id)
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            'The assistant took too long to answer. Please try again, or ask a shorter question.',
        ) from None
    except chat_agent.AgentNotConfigured:
        logger.error('Chat agent not configured (no model API key) [%s]', request.state.request_id)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            'The shopping assistant is offline right now. You can still browse all products.',
        ) from None
    except chat_agent.MessageBlocked:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'That message was blocked by the AI provider’s safety filter. '
            'Please rephrase your question about Campus Customs products.',
        ) from None
    except UsageLimitExceeded:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            'The assistant needed too many steps to answer. Please try a simpler question.',
        ) from None
    except Exception:
        logger.exception('Chat agent run failed [%s]', request.state.request_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            'The shopping assistant is temporarily unavailable. Please try again in a moment.',
        ) from None

    if auth:
        # Save the exchange only after the agent answered. Search replies keep their top results as cards.
        cards = response.products
        if not cards and response.search_results:
            cards, _ = build_product_cards([p.product_id for p in response.search_results.products], 6)
        try:
            memory.save_exchange(auth[0], body.message, response.reply, cards)
            response.saved = True
        except Exception:
            logger.exception('Could not save chat history')
    return response


@app.get('/api/chat/history', response_model=ChatHistoryResponse)
def chat_history(authorization: str | None = Header(default=None)) -> ChatHistoryResponse:
    """The logged-in shopper's saved conversation (most recent messages, oldest first)."""
    auth = _authenticated_customer(authorization)
    if auth is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Log in to see saved chat history.')
    messages, total = memory.load_history(auth[0])
    return ChatHistoryResponse(messages=messages, total_saved=total)


@app.delete('/api/chat/history')
def delete_chat_history(authorization: str | None = Header(default=None)) -> dict[str, int]:
    """Let a logged-in shopper clear their own saved conversation."""
    auth = _authenticated_customer(authorization)
    if auth is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Log in to manage saved chat history.')
    return {'deleted': memory.clear_history(auth[0])}
