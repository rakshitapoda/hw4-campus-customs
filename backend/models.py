"""Pydantic / PydanticAI structured types shared by the API, the tools, and the agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_CHAT_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 12  # earlier turns replayed to the agent as short-term memory
MAX_HISTORY_RELOAD = 50  # saved messages returned to the widget when a logged-in shopper comes back
MAX_PRODUCT_CARDS = 6
LOW_STOCK_THRESHOLD = 5  # a size with 1-5 units is "low stock" (same rule as the product page)

StockStatus = Literal['in_stock', 'low_stock', 'out_of_stock']
MatchType = Literal['product_id', 'exact_name', 'best_match', 'ambiguous', 'not_found']


# ---------- Catalogue API ----------

class SizeStock(BaseModel):
    size: str
    quantity: int


class ProductSummary(BaseModel):
    product_id: str
    name: str
    garment_type: str
    description: str
    colors: list[str]
    search_tags: list[str]
    image_file_path: str
    image_url: str
    price: float
    total_stock: int
    in_stock_sizes: list[str] = Field(default_factory=list, description='Sizes with quantity > 0 (for size filters).')


class ProductDetail(ProductSummary):
    inventory: list[SizeStock]


# ---------- Tool results (what the agent sees) ----------

class ProductMatch(BaseModel):
    """Compact product record returned by the search tool."""

    product_id: str
    name: str
    garment_type: str
    price: float
    colors: list[str]
    description: str
    total_stock: int
    in_stock_sizes: list[str]


class SearchResult(BaseModel):
    query: str
    filters: dict[str, str | float]
    total_matches: int
    products: list[ProductMatch]
    corrections: dict[str, str] = Field(default_factory=dict, description='Typo fixes applied, e.g. {"hoddie": "hoodie"}.')
    note: str | None = None


class SizeAvailability(BaseModel):
    """Stock for one size, straight from the inventory table."""

    size: str
    quantity: int = Field(description='Units in stock right now (inventory.quantity).')
    status: StockStatus


class ProductCandidate(BaseModel):
    """A possible match when the shopper's product name was ambiguous or not found."""

    product_id: str
    name: str
    price: float


class ProductInfo(BaseModel):
    """Everything the agent may say about one product, from catalogue + inventory."""

    product_id: str
    name: str
    garment_type: str
    description: str
    price: float = Field(description='catalogue.price in US dollars; quote exactly.')
    colors: list[str]
    colors_listed: bool = Field(description='False when the catalogue has no colors for this product.')
    total_stock: int = Field(description='Sum of inventory.quantity across all sizes.')
    stock_status: StockStatus
    sizes: list[SizeAvailability]
    in_stock_sizes: list[str]
    out_of_stock_sizes: list[str]


class ProductLookupResult(BaseModel):
    """Result of lookup_product: the product's description, price, and stock, or why it wasn't found."""

    found: bool
    match_type: MatchType
    query: str
    product: ProductInfo | None = None
    candidates: list[ProductCandidate] = Field(default_factory=list)
    corrections: dict[str, str] = Field(default_factory=dict)
    note: str


class StockCheckResult(BaseModel):
    """Result of check_stock: availability for a product overall and, if asked, for one size."""

    found: bool
    match_type: MatchType
    query: str
    product_id: str | None = None
    name: str | None = None
    price: float | None = None
    requested_size: str | None = Field(default=None, description='Normalized size code, e.g. "M".')
    size_offered: bool | None = Field(default=None, description='False if the product has no inventory row for that size.')
    size_quantity: int | None = None
    size_status: StockStatus | None = None
    total_stock: int | None = None
    product_status: StockStatus | None = None
    sizes: list[SizeAvailability] = Field(default_factory=list)
    in_stock_sizes: list[str] = Field(default_factory=list)
    out_of_stock_sizes: list[str] = Field(default_factory=list)
    candidates: list[ProductCandidate] = Field(default_factory=list)
    corrections: dict[str, str] = Field(default_factory=dict)
    answer: str = Field(description='Plain-language summary of the facts above, for the agent to rely on.')


class CatalogueOverview(BaseModel):
    total_products: int
    categories: dict[str, int]
    price_min: float
    price_max: float
    sizes: list[str]
    collections_hint: list[str]


# ---------- Agent output (PydanticAI output_type) ----------

class AgentReply(BaseModel):
    """The structured answer the agent must return for every chat turn."""

    reply: str = Field(
        description='The message shown to the shopper. Plain text, friendly, concise. '
        'Only state product facts (price, colors, sizes, stock) that came from tool results.',
    )
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_PRODUCT_CARDS,
        description='product_id values (copied exactly from tool results) to show as product cards, '
        'most relevant first. Empty when no specific products are being recommended.',
    )
    show_search_results: bool = Field(
        default=False,
        description='True when the shopper is browsing or searching for a kind of product (e.g. "what '
        'hoodies do you have?") and you called search_products for it. The full results of your most '
        'recent search_products call are then shown as product cards on the website. False for '
        'questions about one specific product, stock checks, and general chat.',
    )


# ---------- Chat API ----------

def _clean_text(value: str) -> str:
    """Trim whitespace and drop control characters (keeps newlines and tabs)."""
    return ''.join(ch for ch in value if ch in '\n\t' or ord(ch) >= 32).strip()


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=4000)

    @field_validator('content')
    @classmethod
    def clean(cls, v: str) -> str:
        return _clean_text(v)


class PageContextIn(BaseModel):
    """Where the shopper is on the website when they send a message (sent by the chat widget)."""

    path: str = Field(default='/', max_length=300, description='location.pathname + location.search')
    product_id: str | None = Field(default=None, max_length=100, description='Set on /products/:productId pages.')

    @field_validator('path')
    @classmethod
    def site_path(cls, v: str) -> str:
        # Only same-site paths are meaningful; anything else is treated as "unknown page".
        v = v.strip()
        return v if v.startswith('/') and not v.startswith('//') else '/'


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)

    @field_validator('message')
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = _clean_text(v)
        if not v:
            raise ValueError('Please type a message before sending.')
        return v

    # Guests send their in-tab history; for logged-in shoppers the server loads it from the database.
    history: list[ChatTurn] = Field(default_factory=list, max_length=50)
    page_context: PageContextIn | None = None


# ---------- Agent context (dependencies) ----------

class CustomerContext(BaseModel):
    """The logged-in shopper, as given to the agent. Never includes the password hash."""

    first_name: str | None
    last_name: str | None
    name: str
    email: str
    member_since: str = Field(description='Account creation date (YYYY-MM-DD).')
    saved_messages: int = Field(description='Messages already stored in this shopper\'s chat history.')


PageType = Literal['home', 'products', 'chat_search_results', 'product_detail', 'about', 'login',
                   'create_account', 'other']


class PageContext(BaseModel):
    """Server-validated page context. Product details are looked up in the database, not trusted from the client."""

    path: str
    page_type: PageType
    product_id: str | None = None
    product_name: str | None = None
    garment_type: str | None = None


class ProductCard(BaseModel):
    """A product the assistant recommended, built from the database (never from model text)."""

    product_id: str
    name: str
    garment_type: str
    price: float
    image_url: str
    colors: list[str]
    total_stock: int
    in_stock_sizes: list[str]


class ChatSearchResults(BaseModel):
    """A catalogue search from chat, rendered by the website as a full product grid.

    Products use the same ProductSummary shape as GET /api/products, so the website's existing
    ProductCard component and /products/:id detail route work unchanged.
    """

    query: str = Field(description='The search_products query the agent used.')
    shopper_message: str = Field(description='What the shopper typed, for the results banner.')
    filters: dict[str, str | float]
    match_mode: Literal['all_terms', 'partial', 'filters_only']
    total_matches: int
    corrections: dict[str, str] = Field(default_factory=dict, description='Typo fixes, shown as "Showing results for…".')
    products: list[ProductSummary]


class ChatResponse(BaseModel):
    reply: str
    products: list[ProductCard] = Field(default_factory=list)
    search_results: ChatSearchResults | None = None
    model: str
    tool_calls: int
    saved: bool = Field(default=False, description='True when this exchange was stored in chat_messages.')


class ChatHistoryMessage(BaseModel):
    id: int
    role: Literal['user', 'assistant']
    content: str
    products: list[ProductCard] = Field(default_factory=list)
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage]
    total_saved: int
