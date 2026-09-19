from app.http_client import session


def test_session_retries_transient_status_codes():
    adapter = session.get_adapter("https://example.com")
    retry = adapter.max_retries

    assert retry.total == 3
    assert 429 in retry.status_forcelist
    assert 503 in retry.status_forcelist
    assert retry.respect_retry_after_header is True


def test_session_mounted_for_both_schemes():
    assert session.get_adapter("http://example.com").max_retries.total == 3
    assert session.get_adapter("https://example.com").max_retries.total == 3
