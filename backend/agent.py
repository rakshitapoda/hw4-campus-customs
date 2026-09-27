"""PydanticAI agent for the Campus Customs chatbot: prompt loading, model wiring, tools, and runs."""

from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

import security  # noqa: F401  (imported for its side effect: loads hw4/.env into the environment)
import tools
from models import (
    MAX_HISTORY_TURNS,
    MAX_PRODUCT_CARDS,
    AgentReply,
    ChatResponse,
    ChatTurn,
    CustomerContext,
    PageContext,
)

BACKEND_DIR = Path(__file__).resolve().parent
PROMPT_PATH = BACKEND_DIR / 'prompts' / 'prompt.md'

MODEL_NAME = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
PORTKEY_BASE_URL = os.getenv('PORTKEY_BASE_URL', 'https://api.portkey.ai/v1')
MAX_MODEL_REQUESTS_PER_MESSAGE = 8
MODEL_TIMEOUT_SECONDS = 45
# Ask Portkey for a fresh completion every time: a cached reply could repeat stale stock or an
# answer written under an older prompt. Set PORTKEY_ALLOW_CACHE=1 to let Portkey's cache apply.
PORTKEY_HEADERS = {} if os.getenv('PORTKEY_ALLOW_CACHE') == '1' else {'x-portkey-cache-force-refresh': 'true'}
# No temperature override: the Portkey route for this key only accepts the model's default temperature.
MODEL_SETTINGS = ModelSettings(max_tokens=1500, timeout=MODEL_TIMEOUT_SECONDS)


class AgentNotConfigured(RuntimeError):
    pass


class MessageBlocked(RuntimeError):
    """The model provider's content filter refused the shopper's message."""


def _is_content_filter(exc: ModelHTTPError) -> bool:
    return exc.status_code == 400 and 'content_filter' in str(exc.body)


def load_system_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding='utf-8').strip()
    if not text:
        raise AgentNotConfigured(f'System prompt file is empty: {PROMPT_PATH}')
    return text


def _build_model() -> tuple[OpenAIChatModel, str]:
    """Route through Portkey when PORTKEY_API_KEY is set; fall back to OPENAI_API_KEY directly."""
    portkey_key = os.getenv('PORTKEY_API_KEY')
    if portkey_key:
        client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=portkey_key, default_headers=PORTKEY_HEADERS)
        provider = OpenAIProvider(openai_client=client)
        return OpenAIChatModel(MODEL_NAME, provider=provider), 'portkey'
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(api_key=openai_key)), 'openai'
    raise AgentNotConfigured('No model API key found. Set PORTKEY_API_KEY (or OPENAI_API_KEY) in the environment or .env.')


@lru_cache(maxsize=1)
def get_agent() -> Agent[tools.ChatDeps, AgentReply]:
    """Build the agent once (on first chat request) so the rest of the API works without a key."""
    model, _ = _build_model()
    agent = Agent(
        model,
        deps_type=tools.ChatDeps,
        output_type=AgentReply,
        system_prompt=load_system_prompt(),
        model_settings=MODEL_SETTINGS,
        retries=1,
    )

    @agent.instructions
    def shopper_context(ctx: RunContext[tools.ChatDeps]) -> str:
        return customer_instructions(ctx.deps.customer)

    @agent.instructions
    def page_context(ctx: RunContext[tools.ChatDeps]) -> str:
        return page_instructions(ctx.deps.page)

    @agent.tool
    def search_products(
        ctx: RunContext[tools.ChatDeps],
        query: str = '',
        category: str | None = None,
        color: str | None = None,
        max_price: float | None = None,
        size: str | None = None,
        limit: int = tools.MAX_SEARCH_RESULTS,
    ) -> dict[str, Any]:
        """Search the Campus Customs catalogue by keywords and filters.

        Use this whenever the shopper is looking for a kind of product ("what hoodies do you have?",
        "gray crewnecks under $60", "baseball gear"). Category words in the query such as "hoodies" or
        "tees" are applied as a category filter automatically. You see up to 8 matches; all matches
        are shown on the website when you set show_search_results=true.

        Args:
            query: Keywords, e.g. "navy hoodie", "Morse college", "baseball", "vintage bulldog".
            category: Optional garment group: hoodie, crewneck, tee, quarter-zip, or outerwear.
            color: Optional color that must appear in the product's color list, e.g. "gray".
            max_price: Optional maximum price in US dollars.
            size: Optional size that must be in stock: XS, S, M, L, XL, or XXL.
            limit: Maximum number of products to return (1-8).
        """
        try:
            return tools.search_products(ctx.deps, query, category, color, max_price, size, limit).model_dump()
        except tools.ToolCallLimitReached as exc:
            return {'stopped': True, 'error': str(exc)}

    @agent.tool
    def lookup_product(ctx: RunContext[tools.ChatDeps], product: str) -> dict[str, Any]:
        """Look up one product in the database: description, exact price, colors, and stock overall and per size.

        Use this before stating any product's price, description, colors, or availability.

        Args:
            product: The product_id (e.g. "basic-hoodie-big-yale") or the product name the shopper used
                (e.g. "Basic Hoodie Big Yale" or "Morse tee").
        """
        try:
            return tools.lookup_product(ctx.deps, product).model_dump()
        except tools.ToolCallLimitReached as exc:
            return {'stopped': True, 'error': str(exc)}

    @agent.tool
    def check_stock(ctx: RunContext[tools.ChatDeps], product: str, size: str | None = None) -> dict[str, Any]:
        """Check how many units of a product are in stock right now, and for a specific size if one is given.

        Use this for every question about availability, quantities, or sizes. Reports out-of-stock sizes,
        sizes the product is not offered in, and products that are sold out.

        Args:
            product: The product_id or the product name the shopper used.
            size: Optional size the shopper asked about, e.g. "M", "medium", "XL", "2XL".
        """
        try:
            return tools.check_stock(ctx.deps, product, size).model_dump()
        except tools.ToolCallLimitReached as exc:
            return {'stopped': True, 'error': str(exc)}

    @agent.tool
    def get_catalogue_overview(ctx: RunContext[tools.ChatDeps]) -> dict[str, Any]:
        """Summarize the catalogue: product counts per category, price range, and available sizes."""
        try:
            return tools.get_catalogue_overview(ctx.deps).model_dump()
        except tools.ToolCallLimitReached as exc:
            return {'stopped': True, 'error': str(exc)}

    return agent


def customer_instructions(customer: CustomerContext | None) -> str:
    """Per-run 'who am I talking to' block. Only non-sensitive profile fields are included."""
    if customer is None:
        return ('## Current shopper\nThe shopper is a guest (not logged in). You do not know their name or email, '
                'and this conversation is not saved after they leave.')
    lines = [
        '## Current shopper (logged in)',
        f'- First name: {customer.first_name or "(not provided)"}',
        f'- Full name: {customer.name}',
        f'- Email on the account: {customer.email}',
        f'- Customer since: {customer.member_since}',
        f'- Saved chat history: {customer.saved_messages} earlier messages '
        + ('(this is a returning customer; the most recent ones are included in the conversation)'
           if customer.saved_messages else '(first conversation)'),
        'Greet them by first name once, not in every reply. Only mention their email if they ask about '
        'their account. This conversation is saved to their account.',
        'Account facts: you cannot see or change passwords (they are stored only as secure hashes), and '
        'the website has NO password-reset or "forgot password" feature. For account help, suggest '
        'visiting the shop at 57 Broadway.',
    ]
    return '\n'.join(lines)


def page_instructions(page: PageContext | None) -> str:
    """Per-run 'where is the shopper' block, so "this" / "it" can refer to the product on screen."""
    if page is None:
        return '## Current page\nUnknown.'
    lines = ['## Current page', f'- Page: {page.page_type} ({page.path})']
    if page.product_id:
        lines += [
            f'- The shopper is viewing the product page for "{page.product_name}" '
            f'(product_id: {page.product_id}, {page.garment_type}).',
            '- If they say "this", "it", "this one", or ask about colors, sizes, price, or stock without naming a '
            f'product, they mean {page.product_name}. Call lookup_product or check_stock with product_id '
            f'"{page.product_id}" before answering. Do not ask them to repeat the name.',
        ]
    elif page.page_type == 'chat_search_results':
        lines.append('- The shopper is looking at the product grid from their last chat search.')
    return '\n'.join(lines)


def served_model(result: Any) -> str | None:
    """The model name the provider reported in its response (may differ from the requested name)."""
    try:
        return result.response.model_name
    except AttributeError:
        return None


def model_description(served: str | None = None) -> str:
    """Human-readable model/provider label, without any key material.

    Portkey routes the requested OPENAI_MODEL to a deployment of its choosing; in testing, requests for
    gpt-4o-mini were answered by "gpt-5.6-luna-2026-07-09", so the served name is reported when known.
    """
    provider = 'Portkey' if os.getenv('PORTKEY_API_KEY') else 'OpenAI' if os.getenv('OPENAI_API_KEY') else None
    if provider is None:
        return f'{MODEL_NAME} (no API key configured)'
    if served and served != MODEL_NAME:
        return f'{served} via {provider} (requested {MODEL_NAME})'
    return f'{MODEL_NAME} via {provider}'


def to_message_history(turns: list[ChatTurn]) -> list[ModelMessage]:
    """Convert the widget's recent turns into PydanticAI message history (text only)."""
    history: list[ModelMessage] = []
    for turn in turns[-MAX_HISTORY_TURNS:]:
        if turn.role == 'user':
            history.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return history


async def run_chat(
    message: str,
    history: list[ChatTurn],
    customer: CustomerContext | None = None,
    page: PageContext | None = None,
) -> ChatResponse:
    """Send one shopper message to the agent and return its reply with DB-verified product cards."""
    deps = tools.ChatDeps(customer=customer, page=page)
    started = time.perf_counter()
    audit: dict[str, Any] = {
        'event': 'chat_run',
        'model': model_description(),
        'logged_in': customer is not None,  # never the name or email
        'page': {'type': page.page_type, 'product_id': page.product_id} if page else None,
        'message_preview': message[:200],
        'history_turns': min(len(history), MAX_HISTORY_TURNS),
        'stop_reason': 'cancelled (request timed out or client disconnected)',  # overwritten below
    }
    try:
        agent = get_agent()
        result = await agent.run(
            message,
            deps=deps,
            message_history=to_message_history(history),
            usage_limits=UsageLimits(
                request_limit=MAX_MODEL_REQUESTS_PER_MESSAGE,
                tool_calls_limit=tools.MAX_TOOL_CALLS_PER_MESSAGE + 2,  # hard backstop
            ),
        )
    except AgentNotConfigured:
        audit['stop_reason'] = 'not_configured'
        raise
    except UsageLimitExceeded as exc:
        audit['stop_reason'] = f'usage_limit: {exc}'
        raise
    except ModelHTTPError as exc:
        if _is_content_filter(exc):
            audit['stop_reason'] = 'blocked_by_provider_content_filter'
            raise MessageBlocked() from exc
        audit['stop_reason'] = f'error: ModelHTTPError {exc.status_code}'
        raise
    except Exception as exc:
        audit['stop_reason'] = f'error: {type(exc).__name__}'
        raise
    else:
        audit['stop_reason'] = 'completed_after_tool_call_limit' if deps.tool_limit_hit else 'completed'
        audit['served_model'] = served_model(result)
        audit['show_search_results'] = result.output.show_search_results
        if result.output.show_search_results and deps.last_search:
            audit['search_panel'] = {k: deps.last_search[k] for k in ('query', 'filters', 'total_matches')}
    finally:
        audit['tool_calls'] = deps.tool_log
        audit['duration_seconds'] = round(time.perf_counter() - started, 2)
        tools.append_audit_log(audit)

    output = result.output
    # If the agent answered about specific products (lookup_product / check_stock) but listed none,
    # show those products: they are real catalogue ids returned by the tools.
    card_ids = output.product_ids or deps.looked_up_ids
    cards, rejected = tools.build_product_cards(card_ids, MAX_PRODUCT_CARDS)
    if rejected:
        # Any id the model invented is dropped; only real catalogue products become cards.
        tools.append_audit_log({'event': 'rejected_product_ids', 'product_ids': rejected})

    # Product search: the website grid shows the agent's most recent search_products results, re-read
    # from the database. The ids come from the tool call itself, never from model-written text.
    search_results = None
    if output.show_search_results and deps.last_search is not None:
        search_results = tools.build_search_results(deps.last_search, message)
    elif output.show_search_results:
        tools.append_audit_log({'event': 'search_flag_without_search', 'message_preview': message[:200]})

    return ChatResponse(
        reply=output.reply.strip(),
        products=cards,
        search_results=search_results,
        model=model_description(served_model(result)),
        tool_calls=deps.tool_calls,
    )
