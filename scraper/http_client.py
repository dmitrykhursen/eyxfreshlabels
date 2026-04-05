import random
import time
import logging

import requests

from scraper import config

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    pass


class HttpClient:
    """Requests session with rate limiting and retry logic."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._last_request_time: float = 0.0

    def get(self, url: str) -> str:
        """Fetch URL with rate limiting and retries. Returns response text."""
        self._wait()
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                logger.debug("GET %s", url)
                resp = self._session.get(url, timeout=config.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in (429, 503):
                    wait = config.RETRY_BACKOFF * attempt
                    logger.warning("HTTP %s on %s — waiting %ss before retry %s/%s",
                                   resp.status_code, url, wait, attempt, config.MAX_RETRIES)
                    time.sleep(wait)
                    continue
                raise ScraperError(f"HTTP {resp.status_code} for {url}")
            except requests.ConnectionError as exc:
                wait = config.RETRY_BACKOFF * attempt
                logger.warning("Connection error on %s: %s — retry %s/%s in %ss",
                               url, exc, attempt, config.MAX_RETRIES, wait)
                time.sleep(wait)
        raise ScraperError(f"Failed to fetch {url} after {config.MAX_RETRIES} retries")

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        delay = config.DELAY_BETWEEN_REQUESTS + random.uniform(
            -config.DELAY_JITTER, config.DELAY_JITTER
        )
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_time = time.monotonic()
