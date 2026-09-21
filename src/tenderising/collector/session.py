"""GeM BidPlus anonymous HTTP session (CSRF handshake + paged search + GETs).

Ported from gem-scraper app/scraper/session.py (stdlib urllib). The handshake and
POST payload shape are the live contract — re-verified 2026-09-19 — and must not
change without re-verifying (CLAUDE.md §3).
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from tenderising.config import DATA_URL, LIST_URL, POLITENESS


class EmptySearch(Exception):
    """GeM returns HTTP 404 for zero-match keywords — a deterministic "no results"
    signal, not a transient failure; callers must not retry it."""


class GemSession:
    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or POLITENESS.user_agent
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [
            ("User-Agent", self.user_agent),
            ("Accept", "application/json, text/javascript, */*; q=0.01"),
        ]
        self.token: str | None = None

    def refresh(self) -> None:
        """GET the listing page to obtain the CSRF token and session cookie."""
        req = urllib.request.Request(LIST_URL, headers={"User-Agent": self.user_agent})
        with self.opener.open(req, timeout=POLITENESS.timeout_seconds) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        match = re.search(r"csrf_bd_gem_nk['\"]?\s*[:=]\s*['\"]?([0-9a-f]{16,})", html)
        if match:
            self.token = match.group(1)
            return
        for cookie in self.cj:
            if cookie.name == "csrf_gem_cookie":
                self.token = cookie.value
                return
        raise RuntimeError("Could not locate CSRF token on the listing page.")

    def post_page(
        self,
        keyword: str,
        page: int,
        *,
        sort: str = "Bid-End-Date-Oldest",
        status: str = "ongoing_bids",
        by_status: str | None = None,
        search_type: str = "fullText",
    ) -> tuple[int, list]:
        """POST one page; returns (num_found, docs)."""
        param = {"searchBid": keyword, "searchType": search_type}
        filt = {
            "bidStatusType": status,
            "byType": "all",
            "highBidValue": "",
            "byEndDate": {"from": "", "to": ""},
            "sort": sort,
        }
        if by_status:
            filt["byStatus"] = by_status
        payload = json.dumps({"page": page, "param": param, "filter": filt}, separators=(",", ":"))
        body = urllib.parse.urlencode({"payload": payload, "csrf_bd_gem_nk": self.token})
        req = urllib.request.Request(
            DATA_URL,
            data=body.encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": LIST_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        try:
            with self.opener.open(req, timeout=POLITENESS.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise EmptySearch() from err
            raise
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("non-JSON response (likely expired session/CSRF)") from None
        if data.get("code") != 200:
            raise RuntimeError(f"API returned code={data.get('code')}")
        response = data["response"]["response"]
        return response.get("numFound", 0), response.get("docs", [])

    def post_page_with_retry(self, keyword: str, page: int, **kwargs) -> tuple[bool, int, list]:
        """POST a page, retrying with a session refresh on transient failure.

        Returns (ok, num_found, docs); (False, 0, []) on persistent failure.
        """
        for attempt in range(POLITENESS.max_retries):
            try:
                num_found, docs = self.post_page(keyword, page, **kwargs)
                return True, num_found, docs
            except EmptySearch:
                return True, 0, []
            except (RuntimeError, OSError):
                if attempt < POLITENESS.max_retries - 1:
                    time.sleep(POLITENESS.request_delay_seconds * (attempt + 1))
                    try:
                        self.refresh()
                    except (RuntimeError, OSError):
                        pass
        return False, 0, []

    def get(self, url: str) -> tuple[int, str, bytes]:
        """Polite GET returning (status, content_type, body)."""
        time.sleep(POLITENESS.request_delay_seconds)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with self.opener.open(req, timeout=POLITENESS.timeout_seconds) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get("Content-Type", ""), err.read()
        except OSError as err:
            return 0, "", f"EXC {err!r}".encode()

    def post_form(self, url: str, data: dict | None = None) -> tuple[int, str, bytes]:
        """Polite form-encoded POST (auto-adds the CSRF token). Returns (status, ct, body)."""
        time.sleep(POLITENESS.request_delay_seconds)
        form = dict(data or {})
        form.setdefault("csrf_bd_gem_nk", self.token)
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(form).encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": LIST_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        try:
            with self.opener.open(req, timeout=POLITENESS.timeout_seconds) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get("Content-Type", ""), err.read()
        except OSError as err:
            return 0, "", f"EXC {err!r}".encode()
