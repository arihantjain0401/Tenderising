# Live revalidation & probing — GeM BidPlus (2026-09-19)

Method: read-only, polite (~1.5 s between requests), stdlib `urllib`, no login, no captcha
solving, no rate-limit evasion. Findings recorded against the live site on 2026-09-19.

## 1. searchBid listing — REVALIDATED (works)

- `GET https://bidplus.gem.gov.in/all-bids` → 200 HTML; CSRF token `csrf_bd_gem_nk` extracted via
  `csrf_bd_gem_nk['"]?\s*[:=]\s*['"]?([0-9a-f]{16,})`.
- `POST https://bidplus.gem.gov.in/all-bids-data` with form `payload=<json>&csrf_bd_gem_nk=<token>`
  and nested JSON `{page, param:{searchBid, searchType:"fullText"}, filter:{bidStatusType, byType,
  highBidValue, byEndDate:{from,to}, sort}}` → HTTP 200 JSON `{code:200, response:{response:
  {numFound, docs}}}`.
- **Transient 403 observed** on the first POST after a fresh handshake; clears on retry. The
  retry-with-refresh loop is load-bearing (port gem-scraper `post_page_with_retry`).
- Empty keyword (`searchBid:""`) works; page size 10 docs/page; `numFoundExact:true`.
- `numFound` (ongoing) = **46,181** (was ~42k in the Aug probe — board is growing).
- Doc shape: scalars arrive as **single-element lists** (`b_id:[…]`, `b_bid_number:[…]`); `id` is a
  string; use `unwrap()`.

## 2. Status facets (award / technical / financial) — REVALIDATED (captcha-free)

The "By Bid/RA Status" tab sets `filter.bidStatusType = "bidrastatus"` and a separate
`filter.byStatus` key (`window.filter['byStatus']`). Values and live counts:

| Facet | `bidStatusType` | `byStatus` | `numFound` |
|---|---|---|---|
| Ongoing | `ongoing_bids` | (absent) | 46,181 |
| Technical Evaluated | `bidrastatus` | `tech_evaluated` | 179,478 |
| Financial Evaluated | `bidrastatus` | `fin_evaluated` | 804,312 |
| Bid /RA Awarded | `bidrastatus` | `bid_awarded` | 3,344,865 |

Awarded docs carry `b_buyer_status = 3`, `b_status = 2`. **Awards are a captcha-free, separately
discoverable fact** (§4.2) — the "Bid /RA Awarded" facet is the discovery path, not a per-bid-only
source.

## 3. Status / type code mapping (observed)

- `b_status`: `1` = active, `2` = closed.
- `b_buyer_status`: `0` Not Evaluated, `1` Technical Evaluation, `2` Financial Evaluation,
  `3` Bid Award (matches gem-scraper `STATUS_LABELS`).
- `b_bid_type`: numeric; `1` normal, `2` (observed with `GEM/…/R/…` and bunch bids), `5` = RA
  (JS: `b_bid_type==5` → "RA", doc label `showdirectradocumentPdf`). RA bid numbers appear as
  `GEM/YYYY/RA/NNNN` (and some older `GEM/YYYY/R/NNN`). Full `b_bid_type` label map still to verify.

## 4. Detail / result endpoints — PARTIALLY UNLOCKED (corrects gem-scraper note)

`GET /bidding/bid/getBidResultView/<b_id>` → 200 **server-rendered HTML** (~130–190 KB), NOT an
empty JS shell. It contains three tables:

- **Technical evaluation** — `S.No., Seller Name, Offered Item, Participated On, MSE/MII Status,
  Status` (Qualified / Disqualified).
- **Financial evaluation** — `S.No., Seller Name, Offered Item, Total Price, Rank` with real prices
  and `L1/L2/L3…` ranks. **L1 = lowest evaluated bidder** is directly identifiable here (§4.2).
- Specifications — client-rendered JS template (not server-rendered; would need JS).

`GET /bidding/bid/getSinglePacketResultView/<b_id>` → same shape (single-packet variant).
`GET /bidding/bid/getBidResultViewSchedule/<b_id>` → 200 empty body (no static content).

These feed `participation` (technical + financial stages) and L1/award facts. The gem-scraper's
"getBidResultView is a JS shell" note was incorrect for the tech/financial tables — only the specs
table is client-rendered.

## 5. Bid documents — UNLOCKED

`GET /showbidDocument/<numeric_b_id>` → **valid `application/pdf`** (verified with PyMuPDF):
- ongoing bid `9801618` → 12-page PDF (Bid Document: Bid Details, End/Opening Date-Time, Validity,
  Ministry/State Name, Total Quantity, Item Category).
- awarded bid `300815` → 3-page PDF (Bid Number, Dated, Bid End Date, Ministry, Total Quantity,
  Item Category).

Content type is `application/pdf` with a real `%PDF-` signature — **BOQ/bid-document PDFs are
reachable headlessly**. Some older/RA bids return an empty body (len 0) via this path;
`/showdirectradocumentPdf/<b_id>` returned empty for all probed bids (RA-document path unverified).

The bid-document PDF embeds **link annotations** to the bid's other first-class documents — spec
(`…/SpecificationDocument/….pdf`), GTC (`admin.gem.gov.in/apis/v1/gtc/pdfByDate/?date=…`), OMP
(`/bidding/downloadOmppdfile/`), and shared docs — all reachable headlessly. Each is fetched,
classified by `doc_type`, and indexed as a `bid_document` (verified: a spec bid indexed
`bid_document` + `spec` + `GTC`).

## 5a. Corrigenda — UNLOCKED

Corrigendum endpoints are **anonymous (CSRF-only)**, same as `searchBid` — no buyer session needed
(this corrects the earlier gem-scraper note). Verified 2026-09-19:

| Endpoint | Method | Returns |
|---|---|---|
| `/public-bid-other-details/<b_id>` | POST (CSRF) | JSON `{"corrigendum": bool, "representation": bool}` — cheap gate |
| `/bidding/bid/viewCorrigendum/<b_id>` | POST (CSRF) | HTML list: per-corrigendum `span_<iid>` with "Modified On" date |
| `/bidding/bid/getPublicTchtml/<iid>` | POST (CSRF) | JSON `{"bcm_txt": …}` — the corrigendum body text (amended terms/specs) |

Each corrigendum's stable key is the `iid`; the body text is first-class content (§4.11).

## 5b. BOQ / specifications — UNLOCKED (via embedded links, not showSpecs)

The dedicated `showSpecs` endpoint needs item-level IDs (`variantID`, `itemID`, `btype`, `bdid`)
that are **not present** in the `searchBid` listing, and are also absent from the bid-document PDF
and corrigendum body. But the bid-document PDF embeds **link annotations** pointing directly at the
BOQ files on `mkp.gem.gov.in` (verified 2026-09-19):

- `.../OrderItem/BoqLineItemsDocument/….csv` → machine-readable BOQ line items (HTTP 200, no
  login): columns `Item Number, Item Title, Item Description, Item Quantity, Unit of Measure,
  Consignee ID, Delivery Period` — parsed into `bid_line_items`.
- `.../OrderItem/BoqDocument/….pdf` → the BOQ document.

So BOQ line items are collected by following the CSV link embedded in the bid document, not via
`showSpecs`.

## 6. Contracts / direct orders — STILL BLOCKED (captcha)

`GET https://gem.gov.in/view_contracts` → 200 HTML, 3.17 MB, mentions "captcha". Results are
captcha-gated per §3 — **no bypass**. `contracts` and `direct_orders` collectors remain gated
stubs until an alternative (official API / assisted capture) is chosen (§11).

## 7. Conclusions

Unblocked (implementable headlessly, no login, no captcha bypass):
1. **Bids** — `searchBid` listing (ongoing + facets), 28 raw fields.
2. **Awards + participation** — `bid_awarded` facet for discovery + `getBidResultView/<b_id>` for
   technical/financial results, L1 rank, prices, seller names.
3. **Documents/PDFs** — `showbidDocument/<b_id>` → valid bid-document PDF.
4. **Corrigenda** — `viewCorrigendum/<b_id>` + `getPublicTchtml/<iid>` → corrigendum list + body text.
5. **BOQ line items** — `BoqLineItemsDocument` CSV linked from the bid-document PDF → `bid_line_items`.

Still blocked / unverified:
- `contracts`, `direct_orders` — captcha-gated (`view_contracts`).
- `showSpecs` (structured specs by item) — needs item-level IDs not in the listing/PDF; superseded
  by the BOQ CSV link above.
- Specifications table in `getBidResultView` — client-rendered (needs JS).
- RA result pages — `showdirectradocumentPdf` empty; RA award appears in the `bid_awarded` facet
  (`b_bid_type==5`) but a dedicated RA-result page is unverified.

