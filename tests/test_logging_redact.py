"""`ping_failure`: the host and the /fail flag, never the path, and an exception's text only where
its class cannot quote the URL."""

import http.client
import urllib.error

import pytest

from cli.logging.redact import ping_failure

UUID = "1c1ab0a3-0d68-4c47-9a67-3b8c0f0e7c9d"
URL = f"https://hc-ping.com/{UUID}"


def test_a_transport_error_keeps_its_text_and_the_host_and_loses_the_path():
    line = ping_failure(URL, urllib.error.URLError("[Errno -3] Temporary failure in name resolution"))
    assert (
        line == "healthcheck ping failed target=hc-ping.com error=<urlopen error [Errno -3] Temporary failure in name resolution>"
    )


def test_the_fail_ping_is_named_as_such_without_its_path():
    assert ping_failure(URL + "/fail", OSError("timed out")) == "healthcheck ping failed target=hc-ping.com/fail error=timed out"


@pytest.mark.parametrize(
    "exc",
    [ValueError(f"unknown url type: {URL!r}"), http.client.InvalidURL(f"nonnumeric port: {URL}")],
    ids=["ValueError", "InvalidURL"],
)
def test_a_class_that_quotes_the_url_gives_its_name_alone(exc):
    line = ping_failure(URL, exc)
    assert UUID not in line
    assert line == f"healthcheck ping failed target=hc-ping.com error={type(exc).__name__}"


def test_an_unparseable_url_still_yields_a_line_without_it():
    line = ping_failure(f"https://[bad/{UUID}/fail", OSError("x"))
    assert UUID not in line
    assert line == "healthcheck ping failed target=?/fail error=x"
