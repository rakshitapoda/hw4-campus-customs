"""Read-only catalogue tools the Campus Customs agent can call, plus run state and audit logging."""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from db import ROOT_DIR, get_connection
from models import (
    LOW_STOCK_THRESHOLD,
    CatalogueOverview,
    ChatSearchResults,
    CustomerContext,
    PageContext,
    MatchType,
    ProductCandidate,
    ProductCard,
    ProductInfo,
    ProductLookupResult,
    ProductMatch,
    ProductSummary,
    SearchResult,
    SizeAvailability,
    SizeStock,
    StockCheckResult,
    StockStatus,
)

MEDIA_URL_PREFIX = '/media/products'
SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
MAX_TOOL_CALLS_PER_MESSAGE = 6
MAX_SEARCH_RESULTS = 8  # products the model sees per search
MAX_PANEL_RESULTS = 102  # products sent to the website for one chat search (the whole catalogue at most)
MAX_QUERY_CHARS = 100
AUDIT_LOG_PATH = ROOT_DIR / 'output' / 'audit_trail.json'  # append-only: entries are never trimmed or rewritten

# garment_type has 22 inconsistent spellings, so group by keyword (same rules as the frontend).
CATEGORIES = ['hoodie', 'crewneck', 'tee', 'quarter-zip', 'outerwear']

STOPWORDS = {
    'a', 'an', 'and', 'any', 'do', 'for', 'have', 'i', 'in', 'is', 'it', 'me', 'my', 'of', 'on',
    'or', 'show', 'some', 'something', 'that', 'the', 'this', 'to', 'want', 'with', 'you', 'your',
    'yale', 'campus', 'customs', 'looking', 'find', 'need', 'got', 'what', 'which', 'good',
}
STOPWORDS |= {'products', 'product', 'items', 'stuff', 'gear', 'apparel', 'clothes', 'clothing',
              'sell', 'carry', 'options', 'available', 'all', 'there', 'are', 'can', 'see', 'get',
              'please', 'like', 'would', 'kind', 'kinds', 'type', 'types', 'shop', 'store', 'browse',
              'gift', 'gifts', 'present', 'presents', 'idea', 'ideas', 'recommend', 'recommendation',
              'recommendations', 'suggest', 'suggestions', 'buy', 'wear', 'someone', 'something'}
# Words that name a garment category become a category filter instead of a keyword
# (e.g. "Champion Full Zip Hood" has no "hoodie" in its name but is a hoodie).
CATEGORY_WORDS = {
    'hoodie': 'hoodie', 'hoodies': 'hoodie', 'hoody': 'hoodie', 'hood': 'hoodie', 'hoods': 'hoodie',
    'hooded': 'hoodie', 'crewneck': 'crewneck', 'crewnecks': 'crewneck', 'crew': 'crewneck',
    'crews': 'crewneck', 'tee': 'tee', 'tees': 'tee', 't-shirt': 'tee', 't-shirts': 'tee',
    'tshirt': 'tee', 'tshirts': 'tee', 'shirt': 'tee', 'shirts': 'tee', 'quarter-zip': 'quarter-zip',
    'quarter-zips': 'quarter-zip', 'quarter': 'quarter-zip', 'quarterzip': 'quarter-zip',
    'jacket': 'outerwear', 'jackets': 'outerwear', 'fleece': 'outerwear', 'fleeces': 'outerwear',
    'outerwear': 'outerwear', 'bomber': 'outerwear', 'coat': 'outerwear', 'coats': 'outerwear',
    'jumper': 'crewneck', 'jumpers': 'crewneck',
}
# Different wording for the same thing, mapped onto words the catalogue actually uses.
SYNONYMS = {
    'grey': 'gray', 'sweatshirts': 'sweatshirt', 'sweater': 'sweat', 'zips': 'zip', 'zipup': 'zip',
    'mum': 'mom', 'mother': 'mom', 'mothers': 'mom', 'father': 'dad', 'fathers': 'dad',
    'grandmother': 'grandma', 'nana': 'grandma', 'grandfather': 'grandpa', 'grandad': 'grandpa',
    'granddad': 'grandpa', 'sis': 'sister', 'bro': 'brother',
}
# Multi-word phrasings normalized before splitting into words ("crew neck" -> "crewneck").
PHRASES = [
    (re.compile(r'\bcrew[\s-]+necks?\b'), 'crewneck'),
    (re.compile(r'\b(?:quarter|1/4|1 4)[\s-]*zips?\b'), 'quarter-zip'),
    (re.compile(r'\b(?:t|tee)[\s-]+shirts?\b'), 't-shirt'),
    (re.compile(r'\bzip[\s-]+ups?\b'), 'zip'),
    (re.compile(r'\bhooded[\s-]+sweatshirts?\b'), 'hoodie'),
    (re.compile(r'\bsweat[\s-]+shirts?\b'), 'sweatshirt'),
]
FUZZY_CUTOFF = 0.8  # difflib similarity needed to treat a word as a typo of a catalogue word
FUZZY_MIN_LENGTH = 4  # shorter words are never "corrected" (too easy to turn one word into another)


# ---------- Run state ----------

class ToolCallLimitReached(RuntimeError):
    pass


@dataclass
class ChatDeps:
    """Per-message state passed to every tool via RunContext.deps."""

    # Who the agent is talking to (None for guests) and where they are on the site.
    customer: CustomerContext | None = None
    page: PageContext | None = None
    tool_calls: int = 0
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    tool_limit_hit: bool = False
    # Full, ordered results of the most recent search_products call, for the website's product grid.
    last_search: dict[str, Any] | None = None
    # Products resolved by lookup_product / check_stock this turn (used as cards if the agent lists none).
    looked_up_ids: list[str] = field(default_factory=list)

    def note_product(self, product_id: str) -> None:
        if product_id not in self.looked_up_ids:
            self.looked_up_ids.append(product_id)

    def reserve_tool_call(self) -> None:
        if self.tool_calls >= MAX_TOOL_CALLS_PER_MESSAGE:
            self.tool_limit_hit = True
            self.record('tool_call_refused', {}, f'tool-call limit of {MAX_TOOL_CALLS_PER_MESSAGE} reached')
            raise ToolCallLimitReached(
                f'Tool-call limit of {MAX_TOOL_CALLS_PER_MESSAGE} reached for this message. '
                'Answer with the information already gathered.'
            )
        self.tool_calls += 1

    def record(self, tool: str, args: dict[str, Any], summary: str) -> None:
        self.tool_log.append({'tool': tool, 'args': args, 'result_summary': summary})


# ---------- Helpers ----------

def category_of(garment_type: str) -> str:
    g = garment_type.lower()
    if 'quarter-zip' in g:
        return 'quarter-zip'
    if 'jacket' in g or 'fleece' in g:
        return 'outerwear'
    if 'hood' in g:
        return 'hoodie'
    # Check sweatshirts before tees: "sweatshirt" contains "shirt".
    if 'crewneck' in g or 'sweatshirt' in g or 'mockneck' in g:
        return 'crewneck'
    if 'shirt' in g:
        return 'tee'
    return 'other'


def image_url_for(image_file_path: str) -> str:
    # image_file_path is stored relative to data/, e.g. "products/foo.jpg"
    return f'{MEDIA_URL_PREFIX}/{Path(image_file_path).name}'


def _size_rank(size: str) -> int:
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else len(SIZE_ORDER)


def load_inventory(conn: sqlite3.Connection, product_ids: list[str] | None = None) -> dict[str, list[SizeStock]]:
    sql = 'SELECT product_id, size, quantity FROM inventory'
    params: list[str] = []
    if product_ids is not None:
        if not product_ids:
            return {}
        sql += f' WHERE product_id IN ({",".join("?" * len(product_ids))})'
        params = product_ids
    stock: dict[str, list[SizeStock]] = {}
    for r in conn.execute(sql, params):
        stock.setdefault(r['product_id'], []).append(SizeStock(size=r['size'], quantity=r['quantity']))
    for sizes in stock.values():
        sizes.sort(key=lambda s: _size_rank(s.size))
    return stock


def product_summary(row: sqlite3.Row, sizes: list[SizeStock]) -> ProductSummary:
    return ProductSummary(
        product_id=row['product_id'],
        name=row['name'],
        garment_type=row['garment_type'],
        description=row['description'],
        colors=json.loads(row['colors']),
        search_tags=json.loads(row['search_tags']),
        image_file_path=row['image_file_path'],
        image_url=image_url_for(row['image_file_path']),
        price=row['price'],
        total_stock=sum(s.quantity for s in sizes),
        in_stock_sizes=[s.size for s in sizes if s.quantity > 0],
    )


def _in_stock(sizes: list[SizeStock]) -> list[str]:
    return [s.size for s in sizes if s.quantity > 0]


def _singular(word: str) -> str:
    """Rough English singular: "hoodies" -> "hoodie", "jerseys" -> "jersey", "families" -> "family"."""
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)?', text.lower())


@lru_cache(maxsize=1)
def search_vocabulary() -> frozenset[str]:
    """Every word used in the catalogue (names, types, tags, colors, descriptions), read from the database.

    Typos are only ever corrected to one of these words, so a correction can never invent a product.
    Cached for the life of the process (the catalogue is read-only here).
    """
    words: set[str] = set()
    with get_connection() as conn:
        for r in conn.execute('SELECT name, garment_type, description, search_tags, colors FROM catalogue'):
            text = ' '.join([r['name'], r['garment_type'], r['description'],
                             ' '.join(json.loads(r['search_tags'])), ' '.join(json.loads(r['colors']))])
            for w in _words(text):
                words.add(w)
                words.add(_singular(w))
    return frozenset(words)


def correct_word(word: str, vocabulary: frozenset[str] | set[str]) -> str | None:
    """Closest catalogue word for a probable typo ("hoddie" -> "hoodie"), or None if nothing is close."""
    if len(word) < FUZZY_MIN_LENGTH:
        return None
    match = difflib.get_close_matches(word, vocabulary, n=1, cutoff=FUZZY_CUTOFF)
    return match[0] if match else None


def _parse_query(query: str) -> tuple[list[str], set[str], dict[str, str]]:
    """Split a search into keyword terms, garment categories, and any typo corrections applied."""
    text = query.lower()
    for pattern, replacement in PHRASES:
        text = pattern.sub(replacement, text)
    vocab = search_vocabulary()
    targets = vocab | set(CATEGORY_WORDS) | set(SYNONYMS)
    terms: list[str] = []
    categories: set[str] = set()
    corrections: dict[str, str] = {}
    for word in _words(text):
        if word in STOPWORDS or len(word) < 2:
            continue
        w = SYNONYMS.get(word, word)
        singular = _singular(w)
        if w in CATEGORY_WORDS or singular in CATEGORY_WORDS:
            categories.add(CATEGORY_WORDS.get(w) or CATEGORY_WORDS[singular])
            continue
        if w in vocab or singular in vocab:
            terms.append(w)
            continue
        fix = correct_word(w, targets)
        if fix:
            corrections[word] = fix
            fix = SYNONYMS.get(fix, fix)
            if fix in CATEGORY_WORDS:
                categories.add(CATEGORY_WORDS[fix])
            else:
                terms.append(fix)
        else:
            terms.append(w)  # unknown word kept as-is: it simply won't match anything
    return terms, categories, corrections


def _score(p: ProductSummary, terms: list[str]) -> tuple[int, int]:
    """Return (number of terms matched, weighted relevance score)."""
    name, gtype = p.name.lower(), p.garment_type.lower()
    tags, colors = ' '.join(p.search_tags).lower(), ' '.join(p.colors).lower()
    desc = p.description.lower()
    matched = score = 0
    for t in terms:
        variants = {t, t.rstrip('s')} if len(t) > 3 else {t}
        best = 0
        for v in variants:
            best = max(
                best,
                (3 if v in name else 0) + (2 if v in gtype else 0) + (2 if v in tags else 0)
                + (2 if v in colors else 0) + (1 if v in desc else 0),
            )
        if best:
            matched += 1
            score += best
    return matched, score


# ---------- Tools ----------

def search_products(
    deps: ChatDeps,
    query: str = '',
    category: str | None = None,
    color: str | None = None,
    max_price: float | None = None,
    size: str | None = None,
    limit: int = MAX_SEARCH_RESULTS,
) -> SearchResult:
    deps.reserve_tool_call()
    query = query[:MAX_QUERY_CHARS]
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    size = normalize_size(size) if size and size.strip() else None

    terms, categories, corrections = _parse_query(query)
    note = None
    if category:
        cat = CATEGORY_WORDS.get(category.lower().strip(), category.lower().strip())
        if cat in CATEGORIES:
            categories.add(cat)
        else:
            note = f'Unknown category "{category}" was ignored. Valid categories: {", ".join(CATEGORIES)}.'

    filters: dict[str, str | float] = {}
    if categories:
        filters['category'] = ', '.join(sorted(categories))
    if color:
        filters['color'] = color
    if max_price is not None:
        filters['max_price'] = max_price
    if size:
        filters['size_in_stock'] = size

    with get_connection() as conn:
        rows = conn.execute('SELECT * FROM catalogue').fetchall()
        stock = load_inventory(conn)

    candidates: list[tuple[int, int, ProductSummary, list[SizeStock]]] = []
    for row in rows:
        sizes = stock.get(row['product_id'], [])
        p = product_summary(row, sizes)
        if categories and category_of(p.garment_type) not in categories:
            continue
        if color and not any(color.lower() in c.lower() for c in p.colors):
            continue
        if max_price is not None and p.price > max_price:
            continue
        if size and size not in _in_stock(sizes):
            continue
        matched, score = _score(p, terms) if terms else (0, 1)
        candidates.append((matched, score, p, sizes))

    # Prefer products that match every keyword; fall back to partial matches only if none do.
    if terms:
        strict = [c for c in candidates if c[0] == len(terms)]
        partial = [c for c in candidates if 0 < c[0] < len(terms)]
        scored, match_mode = (strict, 'all_terms') if strict else (partial, 'partial')
        if match_mode == 'partial' and partial:
            note = (f'No product matched every keyword in "{query}"; these match some of them. '
                    'Say so honestly.')
    else:
        scored, match_mode = candidates, 'filters_only'

    scored.sort(key=lambda t: (-t[1], -t[2].total_stock, t[2].name))
    matches = [
        ProductMatch(
            product_id=p.product_id,
            name=p.name,
            garment_type=p.garment_type,
            price=p.price,
            colors=p.colors,
            description=p.description,
            total_stock=p.total_stock,
            in_stock_sizes=_in_stock(sizes),
        )
        for _, _, p, sizes in scored[:limit]
    ]
    if corrections:
        fixed = ', '.join(f'"{a}" as "{b}"' for a, b in corrections.items())
        note = ((note + ' ') if note else '') + f'Probable typos were corrected: read {fixed}. Mention this briefly.'
    if not scored:
        note = ((note + ' ') if note else '') + (
            'No products in the catalogue match. Tell the shopper honestly and suggest a broader search.')
    elif len(scored) > len(matches):
        note = ((note + ' ') if note else '') + (
            f'Showing {len(matches)} of {len(scored)} matches here. If this is a product search, set '
            'show_search_results=true and all matches will be displayed on the website.')

    deps.last_search = {
        'query': query,
        'filters': filters,
        'match_mode': match_mode,
        'total_matches': len(scored),
        'corrections': corrections,
        'product_ids': [p.product_id for _, _, p, _ in scored[:MAX_PANEL_RESULTS]],
    }
    result = SearchResult(query=query, filters=filters, total_matches=len(scored), products=matches,
                          corrections=corrections, note=note)
    deps.record(
        'search_products',
        {'query': query, **filters, 'limit': limit},
        f'{len(scored)} matches ({match_mode}), corrections={corrections}, returned {len(matches)}: '
        f'{[m.product_id for m in matches]}',
    )
    return result


# ---------- Product resolution (shopper wording -> one catalogue row) ----------

NAME_STOPWORDS = {'the', 'a', 'an', 'your', 'that', 'this', 'one', 'please'}
SIZE_ALIASES = {
    'XS': 'XS', 'XSMALL': 'XS', 'EXTRASMALL': 'XS',
    'S': 'S', 'SM': 'S', 'SMALL': 'S',
    'M': 'M', 'MD': 'M', 'MED': 'M', 'MEDIUM': 'M',
    'L': 'L', 'LG': 'L', 'LARGE': 'L',
    'XL': 'XL', 'XLARGE': 'XL', 'EXTRALARGE': 'XL',
    'XXL': 'XXL', '2XL': 'XXL', '2X': 'XXL', 'XXLARGE': 'XXL', 'EXTRAEXTRALARGE': 'XXL', '2XLARGE': 'XXL',
}


def normalize_size(size: str) -> str:
    """Map shopper wording ("medium", "x-large", "2XL") to the inventory size codes; else upper-case it."""
    key = re.sub(r'[^A-Z0-9]', '', size.upper())
    return SIZE_ALIASES.get(key, key)


def _name_tokens(text: str) -> list[str]:
    text = text.lower().replace('1/4', '1 4').replace('quarter-zip', '1 4 zip').replace('quarter zip', '1 4 zip')
    text = re.sub(r'\bt-?shirts?\b|\btees?\b', 't shirt', text)
    # Singularize both sides so "Crewnecks" matches "Crewneck" (and "Sports" matches "Sport").
    return [_singular(t) for t in re.findall(r'[a-z0-9]+', text) if t not in NAME_STOPWORDS]


def _candidate(row: sqlite3.Row) -> ProductCandidate:
    return ProductCandidate(product_id=row['product_id'], name=row['name'], price=row['price'])


@lru_cache(maxsize=1)
def name_vocabulary() -> frozenset[str]:
    """Every (normalized) word used in product names, from the database."""
    with get_connection() as conn:
        return frozenset(t for (n,) in conn.execute('SELECT name FROM catalogue') for t in _name_tokens(n))


def resolve_product(
    conn: sqlite3.Connection, query: str
) -> tuple[sqlite3.Row | None, MatchType, list[ProductCandidate], dict[str, str]]:
    """Find the single catalogue row the shopper means, by product_id, exact name, or unambiguous best match.

    Name words that aren't in any product name are corrected to the closest real name word when one is
    close enough ("Basic Hodie Big Yale" -> "hoodie"); the corrections are returned so the agent can say so.
    """
    q = query.strip()[:MAX_QUERY_CHARS]
    row = conn.execute('SELECT * FROM catalogue WHERE product_id = ?', (q.lower(),)).fetchone()
    if row:
        return row, 'product_id', [], {}
    row = conn.execute('SELECT * FROM catalogue WHERE lower(name) = ?', (q.lower(),)).fetchone()
    if row:
        return row, 'exact_name', [], {}

    vocab = name_vocabulary()
    corrections: dict[str, str] = {}
    wanted: set[str] = set()
    for token in _name_tokens(q):
        if token not in vocab and (fix := correct_word(token, vocab)):
            corrections[token] = fix
            token = fix
        wanted.add(token)
    if not wanted:
        return None, 'not_found', [], corrections
    full, partial = [], []
    for r in conn.execute('SELECT * FROM catalogue'):
        have = set(_name_tokens(r['name']))
        overlap = len(wanted & have)
        if overlap == len(wanted):
            full.append((len(have - wanted), r))  # fewer extra words = tighter match
        elif overlap:
            partial.append((overlap, -len(have - wanted), r))
    if not full:
        # Some words matched nothing (e.g. "Stanford hoodie"): the product isn't carried.
        partial.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return None, 'not_found', [_candidate(t[2]) for t in partial[:3]], corrections
    full.sort(key=lambda t: t[0])
    if len(full) == 1 or full[0][0] < full[1][0]:
        return full[0][1], 'best_match', [], corrections
    return None, 'ambiguous', [_candidate(r) for _, r in full[:5]], corrections


def _availability(sizes: list[SizeStock]) -> list[SizeAvailability]:
    return [SizeAvailability(size=s.size, quantity=s.quantity, status=stock_status(s.quantity)) for s in sizes]


def stock_status(quantity: int) -> StockStatus:
    if quantity <= 0:
        return 'out_of_stock'
    if quantity <= LOW_STOCK_THRESHOLD:
        return 'low_stock'
    return 'in_stock'


def _product_info(row: sqlite3.Row, sizes: list[SizeStock]) -> ProductInfo:
    colors = json.loads(row['colors'])
    total = sum(s.quantity for s in sizes)
    return ProductInfo(
        product_id=row['product_id'],
        name=row['name'],
        garment_type=row['garment_type'],
        description=row['description'],
        price=row['price'],
        colors=colors,
        colors_listed=bool(colors),
        total_stock=total,
        stock_status=stock_status(total),
        sizes=_availability(sizes),
        in_stock_sizes=[s.size for s in sizes if s.quantity > 0],
        out_of_stock_sizes=[s.size for s in sizes if s.quantity <= 0],
    )


def _not_found_note(match_type: MatchType, query: str) -> str:
    if match_type == 'ambiguous':
        return f'"{query}" matches several products. Ask the shopper which one they mean (see candidates).'
    return (f'No product matching "{query}" is in the Campus Customs catalogue. Tell the shopper we do not '
            'carry it; do not guess. Candidates (if any) are only loosely related real products you may suggest.')


def lookup_product(deps: ChatDeps, product: str) -> ProductLookupResult:
    """Description, price, colors, and stock (overall and per size) for one product."""
    deps.reserve_tool_call()
    with get_connection() as conn:
        row, match_type, candidates, corrections = resolve_product(conn, product)
        sizes = load_inventory(conn, [row['product_id']]).get(row['product_id'], []) if row else []
    if row is None:
        deps.record('lookup_product', {'product': product}, f'{match_type}; candidates={[c.product_id for c in candidates]}')
        return ProductLookupResult(found=False, match_type=match_type, query=product, candidates=candidates,
                                   corrections=corrections, note=_not_found_note(match_type, product))
    info = _product_info(row, sizes)
    deps.note_product(info.product_id)
    note = f'Facts from the database for {info.name}.'
    if corrections:
        note += f' (Typos corrected in the product name: {corrections}.)'
    if info.stock_status == 'out_of_stock':
        note += ' This product is OUT OF STOCK in every size.'
    if not info.colors_listed:
        note += ' No colors are listed for this product; say the color is not listed.'
    deps.record('lookup_product', {'product': product},
                f'{match_type} -> {info.product_id}, ${info.price:.2f}, total {info.total_stock}, '
                f'out of stock sizes {info.out_of_stock_sizes}')
    return ProductLookupResult(found=True, match_type=match_type, query=product, product=info,
                               corrections=corrections, note=note)


def check_stock(deps: ChatDeps, product: str, size: str | None = None) -> StockCheckResult:
    """How many units are in stock for a product, and for one size when the shopper names a size."""
    deps.reserve_tool_call()
    requested = normalize_size(size) if size and size.strip() else None
    with get_connection() as conn:
        row, match_type, candidates, corrections = resolve_product(conn, product)
        sizes = load_inventory(conn, [row['product_id']]).get(row['product_id'], []) if row else []
    args = {'product': product, 'size': size}

    if row is None:
        deps.record('check_stock', args, f'{match_type}; candidates={[c.product_id for c in candidates]}')
        return StockCheckResult(found=False, match_type=match_type, query=product, requested_size=requested,
                                candidates=candidates, corrections=corrections,
                                answer=_not_found_note(match_type, product))

    info = _product_info(row, sizes)
    deps.note_product(info.product_id)
    result = StockCheckResult(
        found=True, match_type=match_type, query=product, product_id=info.product_id, name=info.name,
        price=info.price, requested_size=requested, total_stock=info.total_stock,
        product_status=info.stock_status, sizes=info.sizes, in_stock_sizes=info.in_stock_sizes,
        out_of_stock_sizes=info.out_of_stock_sizes, corrections=corrections, answer='',
    )
    in_stock_text = ', '.join(info.in_stock_sizes) or 'none'
    if info.stock_status == 'out_of_stock':
        answer = f'{info.name} is OUT OF STOCK in every size (0 units).'
    else:
        answer = f'{info.name} has {info.total_stock} units in stock in total. In-stock sizes: {in_stock_text}.'

    if requested:
        match = next((s for s in info.sizes if s.size == requested), None)
        if match is None:
            result.size_offered = False
            offered = ', '.join(s.size for s in info.sizes) or 'none'
            answer += f' Size {requested} is NOT OFFERED for this product (offered sizes: {offered}).'
        else:
            result.size_offered = True
            result.size_quantity = match.quantity
            result.size_status = match.status
            if match.status == 'out_of_stock':
                answer += f' Size {requested} is OUT OF STOCK (0 units).'
            else:
                answer += f' Size {requested}: {match.quantity} in stock' + (' (low stock).' if match.status == 'low_stock' else '.')
    result.answer = answer
    deps.record('check_stock', args, f'{match_type} -> {info.product_id}; {answer}')
    return result


def get_catalogue_overview(deps: ChatDeps) -> CatalogueOverview:
    deps.reserve_tool_call()
    with get_connection() as conn:
        rows = conn.execute('SELECT garment_type, price FROM catalogue').fetchall()
        sizes = [r['size'] for r in conn.execute('SELECT DISTINCT size FROM inventory')]
    categories: dict[str, int] = {}
    for r in rows:
        cat = category_of(r['garment_type'])
        categories[cat] = categories.get(cat, 0) + 1
    overview = CatalogueOverview(
        total_products=len(rows),
        categories=categories,
        price_min=min(r['price'] for r in rows),
        price_max=max(r['price'] for r in rows),
        sizes=sorted(sizes, key=_size_rank),
        collections_hint=['residential colleges', 'graduate & professional schools', 'sports teams',
                          'family (mom, dad, grandparents...)', 'vintage bulldog'],
    )
    deps.record('get_catalogue_overview', {}, f'{overview.total_products} products, {categories}')
    return overview


# ---------- Product cards (built from the DB, never from model text) ----------

def build_product_cards(product_ids: list[str], limit: int) -> tuple[list[ProductCard], list[str]]:
    """Return cards for ids that exist in the catalogue, plus any ids that were rejected."""
    unique_ids = list(dict.fromkeys(pid.strip() for pid in product_ids))[:limit]
    with get_connection() as conn:
        rows = {
            r['product_id']: r
            for r in conn.execute(
                f'SELECT * FROM catalogue WHERE product_id IN ({",".join("?" * len(unique_ids))})', unique_ids
            )
        } if unique_ids else {}
        stock = load_inventory(conn, list(rows))
    cards, rejected = [], []
    for pid in unique_ids:
        row = rows.get(pid)
        if row is None:
            rejected.append(pid)
            continue
        sizes = stock.get(pid, [])
        p = product_summary(row, sizes)
        cards.append(ProductCard(
            product_id=p.product_id, name=p.name, garment_type=p.garment_type, price=p.price,
            image_url=p.image_url, colors=p.colors, total_stock=p.total_stock, in_stock_sizes=_in_stock(sizes),
        ))
    return cards, rejected


def build_search_results(last_search: dict[str, Any], shopper_message: str) -> ChatSearchResults:
    """Turn the recorded search into full ProductSummary records, re-read from the database."""
    ids = last_search['product_ids']
    with get_connection() as conn:
        rows = {
            r['product_id']: r
            for r in conn.execute(f'SELECT * FROM catalogue WHERE product_id IN ({",".join("?" * len(ids))})', ids)
        } if ids else {}
        stock = load_inventory(conn, list(rows))
    products = [product_summary(rows[pid], stock.get(pid, [])) for pid in ids if pid in rows]
    return ChatSearchResults(
        query=last_search['query'],
        shopper_message=shopper_message,
        filters=last_search['filters'],
        match_mode=last_search['match_mode'],
        total_matches=last_search['total_matches'],
        corrections=last_search.get('corrections', {}),
        products=products,
    )


# ---------- Audit log ----------

_audit_lock = threading.Lock()


def append_audit_log(entry: dict[str, Any]) -> None:
    """Append one entry to output/audit_trail.json. Earlier entries are always kept.

    The file is rewritten through a temp file + rename, so a crash mid-write can't truncate it.
    If the existing file isn't a valid JSON list, it is moved aside (never discarded) and a new
    trail is started.
    """
    entry = {'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'), **entry}
    with _audit_lock:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log: list[Any] = []
        if AUDIT_LOG_PATH.exists():
            try:
                log = json.loads(AUDIT_LOG_PATH.read_text())
                if not isinstance(log, list):
                    raise ValueError('audit trail is not a JSON list')
            except ValueError:  # includes json.JSONDecodeError
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                AUDIT_LOG_PATH.rename(AUDIT_LOG_PATH.with_name(f'audit_trail.unreadable-{stamp}.json'))
                log = []
        log.append(entry)
        tmp = AUDIT_LOG_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(log, indent=2))
        tmp.replace(AUDIT_LOG_PATH)
