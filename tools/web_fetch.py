#!/usr/bin/env python3
"""Portable sanitized URL fetch wrapper."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from tools.web_search import utc_now, with_sanitization


class UnsupportedSchemeError(ValueError):
    pass


class InvalidUrlError(ValueError):
    pass


class CrossHostRedirect(RuntimeError):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


class NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        old_host = urllib.parse.urlparse(req.full_url).netloc.lower()
        new_host = urllib.parse.urlparse(newurl).netloc.lower()
        if old_host and new_host and old_host != new_host:
            raise CrossHostRedirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if data:
            self.parts.append(data)


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    parser.close()
    text = " ".join(parser.parts).replace("\xa0", " ")
    return " ".join(text.split())


def build_fetch_artifact(
    *,
    url: str,
    text: str,
    status: str,
    now: str,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "url": url,
        "retrieved_at": now,
        "text": text,
    }
    if reason:
        payload["reason"] = reason
    return with_sanitization(payload, now=now)


def fetch(
    url: str,
    *,
    max_chars: int = 20_000,
    now: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    try:
        normalized_url = normalize_url(url)
    except UnsupportedSchemeError:
        return build_fetch_artifact(
            url=url,
            text="",
            status="error",
            now=timestamp,
            reason="unsupported_scheme",
        )
    except InvalidUrlError:
        return build_fetch_artifact(
            url=url,
            text="",
            status="error",
            now=timestamp,
            reason="invalid_url",
        )

    request = urllib.request.Request(
        normalized_url,
        headers={
            "User-Agent": "stock-analysis-agent-web-fetch/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(NoCrossHostRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            final_url = response.geturl()
    except CrossHostRedirect as exc:
        return build_fetch_artifact(
            url=exc.url,
            text="",
            status="redirect",
            now=timestamp,
            reason="cross_host_redirect",
        )
    except urllib.error.HTTPError as exc:
        return build_fetch_artifact(
            url=normalized_url,
            text="",
            status="error",
            now=timestamp,
            reason=f"http_{exc.code}",
        )
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return build_fetch_artifact(
            url=normalized_url,
            text="",
            status="error",
            now=timestamp,
            reason=str(getattr(exc, "reason", exc))[:200] or "request_failed",
        )

    html = body.decode("utf-8", errors="replace")
    text = extract_text(html)[:max_chars]
    return build_fetch_artifact(
        url=final_url,
        text=text,
        status="ok",
        now=timestamp,
    )


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsupportedSchemeError(url)
    if not parsed.netloc:
        raise InvalidUrlError(url)
    if parsed.scheme == "http":
        parsed = parsed._replace(scheme="https")
    return urllib.parse.urlunparse(parsed)


def write_output(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        return
    print(text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch a URL as sanitized readable text.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--max-chars", type=int, default=20_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--now", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = fetch(
        args.url,
        max_chars=args.max_chars,
        now=args.now,
        timeout=args.timeout,
    )
    write_output(payload, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
