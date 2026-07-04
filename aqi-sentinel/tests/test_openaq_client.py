import pytest

from pipeline.openaq_client import OpenAQClient, OpenAQConfig, OpenAQConfigurationError


class DummyResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


def test_missing_openaq_api_key_produces_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
    with pytest.raises(OpenAQConfigurationError, match="OPENAQ_API_KEY is missing"):
        OpenAQConfig.from_env(load_dotenv_file=False)


def test_pagination_combines_multiple_mocked_pages(tmp_path):
    session = DummySession(
        [
            DummyResponse(200, {"meta": {"page": 1, "limit": 2, "found": 3}, "results": [{"id": 1}, {"id": 2}]}),
            DummyResponse(200, {"meta": {"page": 2, "limit": 2, "found": 3}, "results": [{"id": 3}]}),
        ]
    )
    client = OpenAQClient(OpenAQConfig(api_key="test"), raw_dir=tmp_path, session=session, sleep_func=lambda _: None)
    records = client.paginate("/locations", {"limit": 2}, "locations", "20260704T120000Z", refresh=True)
    assert records == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert [call["params"]["page"] for call in session.calls] == [1, 2]


def test_http_429_retry_eventually_succeeds(tmp_path):
    sleeps = []
    session = DummySession(
        [
            DummyResponse(429, {"detail": "rate limited"}, headers={"Retry-After": "0"}),
            DummyResponse(200, {"meta": {"page": 1, "limit": 1000, "found": 1}, "results": [{"id": 1}]}),
        ]
    )
    client = OpenAQClient(OpenAQConfig(api_key="test", max_retries=1), raw_dir=tmp_path, session=session, sleep_func=sleeps.append)
    records = client.paginate("/locations", {}, "locations", "20260704T120000Z", refresh=True)
    assert records == [{"id": 1}]
    assert len(session.calls) == 2
    assert sleeps == [0.0]
