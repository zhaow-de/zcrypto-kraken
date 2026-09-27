"""What a log line may say about a healthchecks.io ping that failed. The URL's path is the check's
capability -- whoever holds it can keep the dead-man fed through an outage -- and these lines ship
to a third party, so the line carries the host and the /fail flag and nothing of the path, and the
exception's text only where its class cannot quote the URL."""

from __future__ import annotations

from urllib.parse import urlsplit


def ping_failure(url: str, exc: BaseException) -> str:
    """`healthcheck ping failed target=<host>[/fail] error=<text or class name>`."""
    try:
        parts = urlsplit(url)
        target = parts.hostname or "?"
        fail = parts.path.rstrip("/").endswith("/fail")
    except ValueError:
        target, fail = "?", url.rstrip("/").endswith("/fail")
    if fail:
        target += "/fail"
    # OSError -- URLError and HTTPError, the socket and TLS errors -- formats its reason and never
    # the request; ValueError on a malformed URL and http.client's InvalidURL quote the URL whole.
    error = str(exc) if isinstance(exc, OSError) else type(exc).__name__
    return f"healthcheck ping failed target={target} error={error}"
