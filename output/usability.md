# Campus Customs Usability Improvements

This document describes four usability improvements: two on the frontend and two on the
agent/backend. Each section covers what was added, why it helps a Campus Customs shopper or the
business, and how to see or test it in the running app. Every feature listed was verified in a
real browser (headless Chromium via Playwright) against the running app, or by direct API tests.
The results are in the final section.

Run the app as described in `README.md`: the backend from `backend/` with
`uvicorn main:app --reload --port 8000`, and the frontend with `npm run dev`. Then open
http://localhost:5173.

---

## Baseline (already in the project before these changes)

These features existed before this work. The improvements extend them instead of duplicating them.

- **Products page:** category chips (Hoodies, Crewnecks, T-Shirts, Quarter-Zips, Jackets & Fleece),
  one free-text search box, sorting by name or price, and collection links from the home page.
  Filters were stored in the URL.
- **Loading and errors:** grey skeleton cards while loading. Every failure showed the same line,
  "We couldn't load products. Is the backend running?", with no way to retry. The chat showed
  typing dots and a red bubble on failure.
- **Search:** keyword search with category words ("hoodies", "tees") mapped to categories and
  simple plural handling. Misspellings such as "hoddies" or "quater zip" returned the wrong results
  or nothing.
- **Backend errors:** Pydantic validation errors were already turned into one readable message.
  Chat errors were mapped to 400, 502 and 503. Other failures, such as a missing or locked database
  or an unexpected exception, fell back to FastAPI's defaults, and the product-ID error even showed
  a raw regex.

---

## 1. Frontend: product filtering and sorting

### What was added

On the **Products page** (`frontend/src/pages/Products.tsx`, with the logic in
`frontend/src/lib/productFilters.ts`):

| Feature | Details |
|---------|---------|
| **Product type chips with live counts** | Each chip shows how many products it would display, given the other active filters (e.g. "Hoodies 27"). A chip that would show nothing is disabled, so shoppers never click into an empty page. |
| **Price filter (new)** | Under $40, $40–$70, Over $70, each with a count. The bands are based on the catalogue's actual price points ($32–$98). |
| **Color filter (new)** | The catalogue has 22 color spellings ("navy blue", "heather charcoal gray", "dusty coral"…). They are grouped into families: Navy, Blue, Gray, White, Black, Red, Green, Gold, Coral, Multicolor. Each option shows a count, and the list is built from the loaded catalogue, not hardcoded. |
| **"Size in stock" filter (new)** | XS–XXL. It shows only products that have **that size in stock right now**, using a new `in_stock_sizes` field that the backend computes from the `inventory` table. |
| **More sort options** | Name (A–Z), Price low → high, Price high → low, and **Most in stock** (new). |
| **Active filter pills** | Every active filter appears as a removable pill ("Gray ×", "Size XS in stock ×"), plus **Clear all filters**. |
| **Helpful empty state** | "No products match these filters" with a **Clear filters** button, instead of a blank grid. |
| **Result count** | "Showing 20 of 102 products", announced to screen readers (`aria-live`). |
| **Shareable filters** | All filters and the sort order live in the URL (e.g. `/products?category=hoodie&price=40-70&size=XS`). They survive a refresh, the Back button, and sharing the link with a friend. |
| **Sorting chat-search results** | The chat-search results page (`/products?view=chat`) has a sort menu (Best match, or any of the sorts above) without losing the agent's results. |

Backend support: `ProductSummary.in_stock_sizes` (`backend/models.py`, filled in by
`tools.product_summary()` from `inventory`).

### Why it helps

- **Shoppers** usually come in with constraints: "a hoodie, under $70, in my size, in gray." They
  can now apply all of these in two or three clicks instead of opening product pages one by one to
  check the size grid. The size filter is the biggest time-saver, because it uses live stock and
  hides products that are sold out in their size.
- The counts prevent dead ends: a shopper can see "Coral (1)" before choosing it.
- **The business** benefits because fewer shoppers leave frustrated when their size isn't
  available. "Most in stock" helps them find well-stocked items quickly, and shareable filtered
  links are easy to send in group chats and on social media.

*Considered and left out:* an "In stock only" toggle. Every product in the database currently has
at least one size in stock, so it would never change the results and would look broken. The
"Size in stock" filter covers the real need.

### How to test

1. Open **Products** and click **Hoodies**. The count reads 27.
2. Choose **Price: $40–$70** (25), then **Size in stock: XS** (20). Pills appear, and the URL
   updates.
3. Refresh the page. The filters stay.
4. Change **Sort by** to **Price: high to low**, then **Most in stock**.
5. Click **Clear all filters**.

---

## 2. Frontend: loading and error feedback

### What was added

| Feature | Where | Details |
|---------|-------|---------|
| **Errors sorted by kind** | `frontend/src/api/client.ts` | Every request now classifies failures: `offline`, `timeout`, `network`, `rate_limited`, `not_found`, `client` and `server`, each with a plain-language message. Examples: "You appear to be offline…", "This is taking longer than expected…", "We couldn't reach the Campus Customs server…". The backend's own `detail` message is shown when there is one. |
| **Request timeouts** | `client.ts` | 15 s for pages and 75 s for chat (the backend allows the agent 60 s). A hung request becomes a clear timeout message instead of an endless spinner. |
| **Error panel with Try again** | `components/ErrorState.tsx`; used on Home, Products and Product detail | An icon, a title ("We couldn't load products"), the message, and a **Try again** button that retries only the failed request. Server errors also show a **Reference ID** (the backend request ID) that staff can look up in the logs. |
| **Loading messages** | Products, Home, Product detail | A spinner and text ("Loading the catalogue…", "Loading product details…") alongside the skeleton cards, announced with `role="status"`. |
| **Clear "not found" page** | Product detail | An unknown or malformed product link shows "Product not found" and a **Browse all products** button. This is kept separate from temporary errors, which get **Try again**. |
| **Offline banner** | `components/NetworkStatus.tsx` | A site-wide banner ("You're offline. Products and the assistant will work again once you reconnect.") that appears and disappears automatically. |
| **Image fallback** | `components/ProductImage.tsx`; used by product cards, the detail page, the home hero and chat cards | A broken product photo is replaced by a labelled "CC · Image unavailable" tile instead of a broken-image icon. |
| **Chat status that updates while you wait** | `components/ChatWidget.tsx` | While the assistant works, a status line changes from "Thinking…" to "Checking the catalogue and stock…" (after 5 s) to "Still working on it. Thanks for your patience…" (after 15 s). |
| **Chat Try again** | `ChatWidget.tsx` | A failed message shows the reason and a **Try again** button that resends the same text (the failed exchange is removed first). It is only offered when retrying can help: offline, timeout, server or busy, not invalid input. |
| **Retry loading saved history** | `ChatWidget.tsx` | If a logged-in shopper's saved chat can't load, the panel says so and offers **Try again**. |

### Why it helps

- **Shoppers** always know what's happening: loading, offline, the server busy, or the product
  gone. They also know what to do next, with one click to retry, so they don't have to guess or
  reload the whole site.
- During a slow agent answer, the changing status shows the chat hasn't frozen, so shoppers don't
  resend the same question.
- **The business** keeps more shoppers through short outages. Broken images no longer make the
  store look broken. Reference IDs let staff find the exact failure in the server logs when a
  customer reports a problem.

### How to test

- **Error panel.** Stop the backend, or in browser dev tools block `/api/products`. Open Products
  and the error panel appears. Unblock it and click **Try again**.
- **Offline banner.** In dev tools choose Network → **Offline**. The banner appears; switch back
  and it disappears.
- **Not found.** Open `/products/not-a-real-product` to see "Product not found".
- **Chat.** Ask a question: the status line starts at "Thinking…". Block `/api/chat` and send a
  message to see the red bubble with **Try again**; unblock it and click **Try again**.

---

## 3. Agent/backend: typo-, plural-, and wording-tolerant catalogue search

### What was added

In `backend/tools.py`, used by the agent's `search_products`, `lookup_product` and `check_stock`
tools:

| Feature | Details |
|---------|---------|
| **Typo correction to real catalogue words only** | `search_vocabulary()` builds the set of every word used in the catalogue (names, types, tags, colors, descriptions) **from the database**. `correct_word()` uses `difflib` to find the closest word, with similarity ≥ 0.8, for words of 4 letters or more. Examples: "hoddies" → hoodies, "crewnek" → crewneck, "tshrits" → tshirts, "quater" → quarter, "jakets" → jackets, "navey" → navy, "baseboll" → baseball, "morce" → morse, "davenprot" → davenport, "bulldgo" → bulldog. A word with no close match (e.g. "pink", "purple", "teal") is **kept**, so it simply matches nothing and is never turned into some other product. |
| **Typo-tolerant product names** | `resolve_product()` corrects name words against the vocabulary of product names ("Basic Hodie Big Yale", "Tri Blend Sports Hocky T Shirt", "Champion Reverse Weave Crewnek" all resolve correctly). Price and stock questions therefore work even with a misspelled name. |
| **Plurals** | A better `_singular()` handles "hoodies", "crewnecks", "families" → "family", and so on, on both the query and the product-name side. |
| **Different wording** | Phrases are normalized before matching: "crew neck" → crewneck, "quarter zip" / "1/4 zip" → quarter-zip, "t shirt" / "tee shirt" → t-shirt, "zip up" → zip, "sweat shirt" → sweatshirt. Synonyms map onto catalogue words: mum/mother → mom, father → dad, grandmother/nana → grandma, grandfather → grandpa, grey → gray, jumper → crewneck, coat → jackets. Filler words like "gift", "ideas" and "recommend" are ignored, so "gifts for my mum" finds the Yale Mom items. |
| **Transparency** | Every correction is returned in `SearchResult.corrections`, `ProductLookupResult.corrections` and `StockCheckResult.corrections`, and recorded in the audit log. The agent is told (prompt section "Product searches update the website", rule 7) to say how it read the request, e.g. "Showing hoodies, reading 'hoddies' as hoodies". The chat-search results page shows **"Showing results for hoodies (you typed 'hoddies')"**. |

All product information, prices and stock still come **only from the database**. The vocabulary
is read from `catalogue`, results are produced by the same database queries as before, and product
cards are re-read from the database.

### Why it helps

- **Shoppers** type fast on phones and misspell things. "hoddies" or "quater zip" used to return
  nothing, and a shopper who sees "no results" often assumes the store doesn't carry the item and
  leaves. Now they see the right products, along with a note on how their words were read.
- **The business** loses fewer searches that should have led to a sale. Because corrections can
  only land on words the catalogue actually uses, the assistant can't be tricked into claiming a
  product exists ("pink hoodie" still honestly returns nothing).

### How to test

- In the chat, type **"do you have any hoddies?"**. The Products page shows 27 hoodies and the
  line "Showing results for hoodies (you typed 'hoddies')".
- Try **"show me quater zips"** (11 results).
- Try **"how much is the Basic Hodie Big Yale?"**. The agent answers $68.00.

---

## 4. Agent/backend: validation and safe error handling

### What was added

A new module, `backend/errors.py`, wired into `backend/main.py`:

| Feature | Details |
|---------|---------|
| **One safe error format** | Every error response is `{"detail": "<readable message>", "request_id": "<id>"}` with an `X-Request-ID` header. Tracebacks, SQL, file paths and provider messages are **only logged on the server**, tagged with the request ID. |
| **Catch-all for unexpected errors** | Middleware turns any unhandled exception into a 500 with "Something went wrong on our side. Please try again in a moment." and logs the details. |
| **Database problems** | Any `sqlite3.Error` (missing, locked or corrupt database) returns **503** "The Campus Customs catalogue is temporarily unavailable…". Product images are served separately and keep working. |
| **Health check that tests the database** | `GET /api/health` runs a real query and returns `database: ok` (200) or `database: unavailable` / `status: degraded` (503). |
| **Stricter validation with readable messages** | Invalid JSON → "The request body must be valid JSON." A missing body → "A request body is required." A whitespace-only chat message → "Please type a message before sending." (it is also blocked in the widget). Control characters are stripped from chat text. A product ID must be a lowercase slug (max 100 characters) → "Product id is not valid.", no longer showing the raw regex. A search longer than 100 characters, bad history roles, and off-site page paths (reset to `/`) are also handled. Unknown routes return "That page or resource was not found." and a wrong method returns "That action is not allowed here." |
| **Request size limit** | Bodies over 64 KB are rejected with **413** "That request is too large…" before any processing. |
| **Agent failures** | Timeout: the whole agent run is capped at 60 s (`CHAT_TIMEOUT_SECONDS`) and returns **504** "The assistant took too long to answer…". The run is still written to the audit log as cancelled. A missing model key returns **503** "The shopping assistant is offline right now. You can still browse all products." (it previously showed the configuration message). Crashes return **502**. Blocked messages return **400** (unchanged). |
| **Chat rate limit** | 15 messages per minute per shopper (user ID when logged in, otherwise IP) → **429** "You're sending messages very quickly. Please wait about N seconds…" with a `Retry-After` header. |
| **Configurable database path** | `CAMPUS_CUSTOMS_DB` in the environment can point the backend at another database file. It is used to test the database-down behavior without touching the real database. |

The frontend (improvement 2) shows these messages directly and offers **Try again** for the
temporary ones.

### Why it helps

- **Shoppers** get a clear message and a next step instead of a crash, a blank screen or a
  technical dump. For example, during a database outage they're told the catalogue is temporarily
  unavailable, and product photos still load.
- **The business:**
  - Internal details, such as file paths, SQL or model-provider errors, are never exposed to
    attackers.
  - Request IDs make support reports traceable.
  - The size limit and rate limit protect the server and cap model-API spending from runaway or
    abusive clients.
  - The health check lets whoever runs the site see immediately when the database is down.

### How to test

- `curl http://localhost:8000/api/health`
- `curl http://localhost:8000/api/products/NOT_VALID`
- `curl -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message":"   "}'`
- To simulate a database outage, start a second backend with
  `CAMPUS_CUSTOMS_DB=/tmp/missing.db uvicorn main:app --port 8001` and request
  `/api/products` on port 8001.

---

## Verification (2026-09-26)

**Browser tests: 42/42 passed.** These ran in headless Chromium (Playwright) against the running
app: Vite on :5173, then FastAPI on :8000, then the real agent. Failures were simulated with
Playwright's network routing and offline mode.

- **Filters and sorting (15):**
  - The catalogue loads (102).
  - Hoodies chip = 27, matching an independent count from the API data. The chip shows its count.
  - $40–$70 hoodies = 25, all priced within the band.
  - Size XS in stock = 20, the exact expected set.
  - Filters are kept in the URL and survive a refresh. Three pills appear, and Clear all restores
    102.
  - Sorts: price high → low ($98 → $32), low → high, most in stock (the top item has 116 units,
    the catalogue maximum).
  - Gray = 51 products, all with gray-family colors.
  - The empty state and Clear filters work.
- **Loading and errors (9):**
  - The loading message appears on a slow API.
  - A products failure shows the error panel, and Try again recovers it.
  - A detail-page server error shows "Reference: test123abc", and Try again recovers it.
  - An unknown product shows "Product not found".
  - A broken image shows "Image unavailable".
  - The offline banner appears and disappears.
- **Chat and search (10):**
  - A chat failure shows a bubble with Try again.
  - The status reads "Thinking…", then "Checking the catalogue…" after 5 s.
  - Try again resends the message and removes the error.
  - "hoddies" shows "Showing results for hoodies (you typed 'hoddies')" with all 27 hoodies, and a
    card opens the correct detail page.
  - "quater zips" returns all 11 quarter-zips.
  - A whitespace-only message can't be sent.
- **Existing features (8):**
  - Demo login works, and saved history reloads (7 earlier user messages).
  - The "Viewing" chip names the product. "Is this available in a medium?" on the Tri Blend page
    gets "…medium is currently out of stock… (0 units). It's available in sizes S and XL."
  - Logging out switches to an empty guest chat.
  - Create Account shows its validation error.
  - Home, About and a collection page render.

**Backend error handling:**

- **Live API:** 14 checks, all passing:
  - health;
  - an invalid product ID ("Product id is not valid.") and an unknown product (404);
  - a search that is too long, an unknown route and a wrong method;
  - malformed JSON, a missing body, a whitespace-only message, a message of the wrong type and a
    bad history role;
  - a 100 KB body (413);
  - a login missing a field and a signup with mismatched passwords.

  Each returned a readable message with a `request_id`.
- **Database missing:** a second server with `CAMPUS_CUSTOMS_DB` pointed at a missing file
  returned health 503 `degraded`, and 503 with the safe message for products, product detail and
  login. Images still returned 200. The only traceback was in the server log.
- **In-process (FastAPI TestClient with a stubbed agent):**
  - agent crash → 502;
  - no model key → 503 "offline right now";
  - slow agent → 504;
  - 16th message within a minute → 429 with `Retry-After: 60`;
  - unhandled route exception → 500 generic.

  None of the planted secrets (a fake password, a file path, exception names) appeared in any
  response.

**Search tolerance:** 30+ offline queries were checked. Correct results for typos, plurals and
wordings are listed in section 3. Colors that don't exist (pink, purple, teal, orange) returned 0
with no false correction.

**Regression suites from earlier problems:** all pass.

- Problem 6 inventory lookups: 10/10.
- Problem 7 chat search: 6/6.
- Problem 8 customer memory, guest chat, history and security: 20/20.
- Chat-search card rendering: 27/27 cards linking to the correct `/products/:id`.
- Frontend `npm run build` and `npm run lint` are clean.

Running the suites back to back from one machine triggered the new 15-per-minute chat limit once
(a 429), which confirmed the limiter works on the live server. The suites were then re-run with a
one-minute gap.
