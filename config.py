"""Configuration for the Seek Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT        port the API listens on (default 8000)
    SEEK_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                (default: none — direct). Seek's job-search and GraphQL APIs
                answer plain HTTP with no cookies, so you very likely don't
                need this. Set it only if you start seeing failures at high
                volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

SEEK_PROXY = os.environ.get("SEEK_PROXY") or None

# Names the seek package reads.
SEEK_PROXY_COUNTRY = None              # unused here: SEEK_PROXY above is the whole proxy policy
SEEK_MAX_ATTEMPTS = MAX_RETRIES        # attempts per upstream call
SEEK_BATCH_WORKERS = 4                 # parallel job fetches in /jobs/batch


def seek_proxy(fallback=False):
    """The proxy for one Seek request: SEEK_PROXY, or None for direct."""
    return SEEK_PROXY
