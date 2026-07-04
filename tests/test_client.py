from __future__ import annotations

import json
from unittest.mock import ANY, MagicMock

import httpx
import pytest
from client import HOOK_TIMEOUT, SEARCH_TIMEOUT, AiMemoryClient
from config import AiMemoryConfig


@pytest.fixture
def client() -> AiMemoryClient:
    return AiMemoryClient(AiMemoryConfig(
        server_url="http://localhost:49374",
        auth_token="test-token",
    ))


def test_client_search_success(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "test+query" in str(request.url) or "test%20query" in str(request.url)
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"results": [{"path": "test.md"}]})

    client._transport = httpx.MockTransport(handler)
    results = client.search("test query", workspace="hermes", project="hermes-test", limit=3)
    assert len(results) == 1
    assert results[0]["path"] == "test.md"


def test_client_search_raises_on_http_error(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client._transport = httpx.MockTransport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.search("test query")


def test_client_write_page_success(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["path"] == "notes/test.md"
        assert body["body"] == "# Hello"
        return httpx.Response(200, json={"ok": True, "path": "notes/test.md"})

    client._transport = httpx.MockTransport(handler)
    result = client.write_page("notes/test.md", "# Hello")
    assert result["ok"] is True


def test_client_write_page_with_tags(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tags"] == ["test", "docs"]
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    result = client.write_page("notes/test.md", "# Hello", tags=["test", "docs"])
    assert result["ok"] is True


def test_client_status_success(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "pages": 10})

    client._transport = httpx.MockTransport(handler)
    result = client.status()
    assert result["ok"] is True
    assert result["pages"] == 10


def test_client_status_raises_on_connection_error(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client._transport = httpx.MockTransport(handler)
    with pytest.raises(httpx.ConnectError):
        client.status()


def test_client_send_hook(client: AiMemoryClient) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    client.send_hook(
        event="user-prompt",
        session_id="test-session",
        payload={"user": "hello", "assistant": "hi"},
        workspace="hermes",
        project="hermes-test",
    )
    assert len(sent) == 1
    assert "event=user-prompt" in str(sent[0].url)


def test_client_send_hook_does_not_raise(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client._transport = httpx.MockTransport(handler)
    client.send_hook("user-prompt", "test-session")
    assert True


def test_client_fetch_handoff_returns_summary(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "handoff": {"summary": "Continue working on X"},
        })

    client._transport = httpx.MockTransport(handler)
    result = client.fetch_handoff()
    assert result == "Continue working on X"


def test_client_fetch_handoff_returns_none_on_404(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client._transport = httpx.MockTransport(handler)
    result = client.fetch_handoff()
    assert result is None


def test_client_fetch_handoff_raises_on_500(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client._transport = httpx.MockTransport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_handoff()


def test_client_no_auth_header_when_no_token() -> None:
    client = AiMemoryClient(AiMemoryConfig(server_url="http://localhost:49374"))
    assert "authorization" not in client._client.headers


def test_client_search_passes_workspace_project(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "workspace=custom-ws" in str(request.url)
        assert "project=custom-proj" in str(request.url)
        return httpx.Response(200, json={"results": []})

    client._transport = httpx.MockTransport(handler)
    client.search("q", workspace="custom-ws", project="custom-proj")


def _ok_response(json_data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json=json_data,
        request=httpx.Request("GET", "http://test"),
    )


def test_client_search_uses_search_timeout(client: AiMemoryClient) -> None:
    client._request = MagicMock()
    client._request.return_value = _ok_response({"results": []})
    client.search("test query")
    client._request.assert_called_once_with(
        "GET", "/admin/search", params=ANY, timeout=SEARCH_TIMEOUT
    )


def test_client_send_hook_uses_hook_timeout(client: AiMemoryClient) -> None:
    client._request = MagicMock()
    client._request.return_value = _ok_response({"ok": True})
    client.send_hook("user-prompt", "test-session")
    client._request.assert_called_once_with(
        "POST", "/hook", params=ANY, json=ANY, timeout=HOOK_TIMEOUT
    )


def test_client_write_page_with_tier_and_pinned(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tier"] == "semantic"
        assert body["pinned"] is True
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    result = client.write_page(
        "notes/test.md", "# Hello", tier="semantic", pinned=True
    )
    assert result["ok"] is True
