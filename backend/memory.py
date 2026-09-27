"""Customer memory: saved chat history for logged-in shoppers, customer context, and page context.

Chat history lives in the existing chat_messages table (one row per message). Guests are never
written to the database.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from db import get_connection
from models import (
    MAX_HISTORY_RELOAD,
    ChatHistoryMessage,
    ChatTurn,
    CustomerContext,
    PageContext,
    PageContextIn,
    PageType,
    ProductCard,
)
from tools import build_product_cards

MAX_CARDS_PER_SAVED_MESSAGE = 6


# ---------- Customer context ----------

def get_customer(user_id: int) -> CustomerContext | None:
    """Load the fields the agent may use about a logged-in shopper (no password hash, no user id)."""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT name, email, first_name, last_name, created_at FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        if row is None:
            return None
        saved = conn.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id = ?', (user_id,)).fetchone()[0]
    return CustomerContext(
        first_name=row['first_name'],
        last_name=row['last_name'],
        name=row['name'],
        email=row['email'],
        member_since=str(row['created_at'])[:10],
        saved_messages=saved,
    )


# ---------- Chat history ----------

def _card_ids(products_json: str | None) -> list[str]:
    """product_ids from a stored products_json array (works for old full snapshots and new cards)."""
    if not products_json:
        return []
    try:
        items = json.loads(products_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [str(i['product_id']) for i in items if isinstance(i, dict) and i.get('product_id')]


def load_history(user_id: int, limit: int = MAX_HISTORY_RELOAD) -> tuple[list[ChatHistoryMessage], int]:
    """Most recent saved messages, oldest first. Product cards are rebuilt from the current catalogue."""
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT id, role, content, products_json, created_at FROM chat_messages '
            'WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (user_id, limit),
        ).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id = ?', (user_id,)).fetchone()[0]
    messages = []
    for r in reversed(rows):
        if r['role'] not in ('user', 'assistant'):
            continue
        # Current price/stock are shown, and products no longer in the catalogue drop out.
        cards, _ = build_product_cards(_card_ids(r['products_json']), MAX_CARDS_PER_SAVED_MESSAGE)
        messages.append(ChatHistoryMessage(
            id=r['id'], role=r['role'], content=r['content'], products=cards, created_at=str(r['created_at']),
        ))
    return messages, total


def _products_note(products_json: str | None) -> str:
    """'[Products shown with this reply: …]' so a reloaded reply like "this hoodie…" stays unambiguous."""
    try:
        items = json.loads(products_json) if products_json else []
    except json.JSONDecodeError:
        return ''
    named = [f"{i.get('name', i['product_id'])} ({i['product_id']})"
             for i in items if isinstance(i, dict) and i.get('product_id')][:MAX_CARDS_PER_SAVED_MESSAGE]
    return f"\n[Products shown with this reply: {', '.join(named)}]" if named else ''


def recent_turns(user_id: int, limit: int) -> list[ChatTurn]:
    """The last `limit` saved messages as agent history, with the products each reply showed."""
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT role, content, products_json FROM chat_messages '
            'WHERE user_id = ? AND role IN (\'user\', \'assistant\') ORDER BY id DESC LIMIT ?',
            (user_id, limit),
        ).fetchall()
    turns = []
    for r in reversed(rows):
        note = _products_note(r['products_json']) if r['role'] == 'assistant' else ''
        turns.append(ChatTurn(role=r['role'], content=(r['content'][:3800] + note)[:4000]))
    return turns


def save_exchange(user_id: int, user_message: str, reply: str, cards: list[ProductCard]) -> None:
    """Store the shopper's message and the assistant's reply together, in one transaction."""
    products_json = json.dumps([c.model_dump() for c in cards[:MAX_CARDS_PER_SAVED_MESSAGE]])
    with get_connection(write=True) as conn:
        conn.execute(
            'INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, NULL)',
            (user_id, 'user', user_message),
        )
        conn.execute(
            'INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, ?)',
            (user_id, 'assistant', reply, products_json),
        )


def clear_history(user_id: int) -> int:
    with get_connection(write=True) as conn:
        return conn.execute('DELETE FROM chat_messages WHERE user_id = ?', (user_id,)).rowcount


# ---------- Page context ----------

def _page_type(path: str, query: dict[str, list[str]]) -> PageType:
    if path in ('', '/'):
        return 'home'
    if path == '/products':
        return 'chat_search_results' if query.get('view') == ['chat'] else 'products'
    if path.startswith('/products/'):
        return 'product_detail'
    return {'/about': 'about', '/login': 'login', '/create-account': 'create_account'}.get(path, 'other')


def resolve_page_context(page: PageContextIn | None) -> PageContext | None:
    """Validate the widget's page context; the product is confirmed against the catalogue."""
    if page is None:
        return None
    parts = urlsplit(page.path)
    path = parts.path.rstrip('/') or '/'
    ctx = PageContext(path=page.path, page_type=_page_type(path, parse_qs(parts.query)))
    product_id = page.product_id or (path.removeprefix('/products/') if ctx.page_type == 'product_detail' else None)
    if product_id:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT product_id, name, garment_type FROM catalogue WHERE product_id = ?', (product_id,)
            ).fetchone()
        if row:
            ctx.product_id, ctx.product_name, ctx.garment_type = row['product_id'], row['name'], row['garment_type']
    return ctx
