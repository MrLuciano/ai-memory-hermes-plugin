from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import ANY, MagicMock

import httpx
import pytest
from client import (
    FAILURE_THRESHOLD,
    HOOK_TIMEOUT,
    SEARCH_TIMEOUT,
    SESSION_END_TIMEOUT,
    AiMemoryClient,
)
from config import AiMemoryConfig


@pytest.fixture
def client() -> AiMemoryClient:
    return AiMemoryClient(
        AiMemoryConfig(
            server_url="http://localhost:49374",
            auth_token="test-token",
        )
    )


def test_client_search_success(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/admin/search"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert dict(request.url.params) == {
            "q": "test query",
            "limit": "3",
            "workspace": "hermes",
            "project": "hermes-test",
        }
        return httpx.Response(200, json=[{"path": "test.md"}])

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
    result = client.write_page(
        "notes/test.md", "# Hello", workspace="hermes", project="hermes-test"
    )
    assert result["ok"] is True


def test_client_write_page_with_tags(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tags"] == ["test", "docs"]
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    result = client.write_page(
        "notes/test.md",
        "# Hello",
        tags=["test", "docs"],
        workspace="hermes",
        project="hermes-test",
    )
    assert result["ok"] is True


def test_client_write_page_always_sends_required_scope(client: AiMemoryClient) -> None:
    # Upstream declares workspace/project as required strings, so both must
    # be present even when the caller passes them positionally-empty.
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["workspace"] == "hermes"
        assert body["project"] == "hermes-test"
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    client.write_page("notes/test.md", "# Hello", workspace="hermes", project="hermes-test")


@pytest.mark.parametrize(
    ("workspace", "project"),
    [("", "hermes-test"), ("hermes", ""), ("", ""), ("   ", "hermes-test")],
)
def test_client_write_page_rejects_missing_scope(
    client: AiMemoryClient, workspace: str, project: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("write_page must not hit the wire without a scope")

    client._transport = httpx.MockTransport(handler)
    with pytest.raises(ValueError, match="workspace and project"):
        client.write_page("notes/test.md", "# Hello", workspace=workspace, project=project)


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


def test_client_fetch_handoff_returns_summary(client: AiMemoryClient) -> None:
    # ai-memory 3.x (verified against 3.2.0) serves the handoff as markdown.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="  Continue working on X  ")

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


def _briefing_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> Path:
    home = tmp_path / "home"
    repo = home / "repo"
    repo.mkdir(parents=True)
    (repo / ".ai-memory.toml").write_text(marker, encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return repo


def test_client_fetch_handoff_forwards_briefing_opt_in(
    client: AiMemoryClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _briefing_repo(
        tmp_path,
        monkeypatch,
        "[briefing]\ninject_on_session_start = true\nmax_chars = 6000\n",
    )
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text="brief")

    client._transport = httpx.MockTransport(handler)
    result = client.fetch_handoff(
        cwd=str(repo), workspace="custom-ws", project="custom-proj"
    )
    assert result == "brief"
    assert seen == {
        "agent": "hermes",
        "cwd": str(repo),
        "briefing": "true",
        "briefing_budget": "6000",
        "workspace": "custom-ws",
        "project": "custom-proj",
    }


def test_client_fetch_handoff_omits_briefing_without_opt_in(
    client: AiMemoryClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _briefing_repo(tmp_path, monkeypatch, 'workspace = "acme"\n')
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text="handoff")

    client._transport = httpx.MockTransport(handler)
    client.fetch_handoff(cwd=str(repo))
    assert seen["cwd"] == str(repo)
    assert "briefing" not in seen
    assert "briefing_budget" not in seen


def test_client_fetch_handoff_treats_falsy_opt_in_as_absent(
    client: AiMemoryClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _briefing_repo(
        tmp_path, monkeypatch, '[briefing]\ninject_on_session_start = "off"\n'
    )
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text="handoff")

    client._transport = httpx.MockTransport(handler)
    client.fetch_handoff(cwd=str(repo))
    assert "briefing" not in seen


def test_client_no_auth_header_when_no_token() -> None:
    client = AiMemoryClient(AiMemoryConfig(server_url="http://localhost:49374"))
    assert "authorization" not in client._client.headers


def test_client_search_passes_workspace_project(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["workspace"] == "custom-ws"
        assert request.url.params["project"] == "custom-proj"
        return httpx.Response(200, json=[])

    client._transport = httpx.MockTransport(handler)
    client.search("q", workspace="custom-ws", project="custom-proj")


def _ok_response(json_data: object) -> httpx.Response:
    return httpx.Response(
        200,
        json=json_data,
        request=httpx.Request("GET", "http://test"),
    )


def test_client_search_uses_search_timeout(client: AiMemoryClient) -> None:
    client._request = MagicMock()
    client._request.return_value = _ok_response([])
    client.search("test query")
    client._request.assert_called_once_with(
        "GET",
        "/admin/search",
        params={"q": "test query", "limit": 3},
        timeout=SEARCH_TIMEOUT,
    )


def test_client_search_timeout_stays_under_hermes_prefetch_bound() -> None:
    # Hermes abandons a provider prefetch after 8s
    # (agent/memory_manager.py:42), so the search budget must sit below it.
    assert SEARCH_TIMEOUT < 8.0
    # Session end is not a prefetch and keeps its longer write budget.
    assert SESSION_END_TIMEOUT > SEARCH_TIMEOUT


def test_client_send_hook_uses_hook_timeout(client: AiMemoryClient) -> None:
    client._request = MagicMock()
    client._request.return_value = _ok_response({"ok": True})
    client.send_hook("user-prompt", "test-session")
    client._request.assert_called_once_with(
        "POST", "/hook", params=ANY, json=ANY, timeout=HOOK_TIMEOUT
    )


def test_client_search_handles_non_dict_response(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "dict"])

    client._transport = httpx.MockTransport(handler)
    results = client.search("test query")
    assert results == []


def test_client_search_normalizes_legacy_envelope_and_applies_limit(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{"path": "first.md"}, "invalid", {"path": "second.md"}],
            },
        )

    client._transport = httpx.MockTransport(handler)
    assert client.search("test query", limit=1) == [{"path": "first.md"}]


def test_client_write_page_with_tier_and_pinned(client: AiMemoryClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tier"] == "semantic"
        assert body["pinned"] is True
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    result = client.write_page(
        "notes/test.md",
        "# Hello",
        tier="semantic",
        pinned=True,
        workspace="hermes",
        project="hermes-test",
    )
    assert result["ok"] is True


def test_client_send_hook_passes_cwd(client: AiMemoryClient) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    client.send_hook("user-prompt-submit", "test-session", cwd="/repo/app")
    assert seen[0].url.params["cwd"] == "/repo/app"


def test_client_send_hook_timeout_override(client: AiMemoryClient) -> None:
    client._request = MagicMock()
    client._request.return_value = _ok_response({"ok": True})
    client.send_hook("session-end", "test-session", timeout=SESSION_END_TIMEOUT)
    assert client._request.call_args.kwargs["timeout"] == SESSION_END_TIMEOUT


def test_client_pauses_after_repeated_transport_failures(client: AiMemoryClient) -> None:
    """A server that is down must not cost a timeout on every single turn."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client._transport = httpx.MockTransport(handler)
    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(httpx.ConnectError):
            client.status()

    assert "ConnectError" in client.last_failure()
    with pytest.raises(RuntimeError, match="paused"):
        client.status()


def test_client_clears_failure_state_after_a_successful_request(
    client: AiMemoryClient,
) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client._transport = httpx.MockTransport(failing)
    with pytest.raises(httpx.ConnectError):
        client.status()

    client._transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    client.status()
    assert client.last_failure() == ""


def test_client_send_hook_is_dropped_while_paused(client: AiMemoryClient) -> None:
    """While paused, a hook is dropped instead of paying the timeout again."""

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client._transport = httpx.MockTransport(failing)
    for _ in range(FAILURE_THRESHOLD):
        client.send_hook("user-prompt-submit", "test-session")

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    client.send_hook("user-prompt-submit", "test-session")
    assert calls == []
