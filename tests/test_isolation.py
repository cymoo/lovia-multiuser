import re

import pytest
from conftest import session_ids


def test_users_see_only_their_own_chats(env):
    alice, bob = env.as_("alice"), env.as_("bob")
    sid = alice.chat("alice", "secret plan")

    assert session_ids(alice.get("/u/alice/api/sessions")) == [sid]
    assert session_ids(bob.get("/u/bob/api/sessions")) == []
    for path in (
        "/u/alice/",
        "/u/alice/api/sessions",
        f"/u/alice/api/sessions/{sid}",
        "/u/alice/api/schedules",
        "/u/alice/api/events",
    ):
        assert bob.get(path).status_code == 404, path


def test_a_guessed_id_reads_your_own_store(env):
    alice, bob = env.as_("alice"), env.as_("bob")
    sid = alice.chat("alice", "secret plan")

    assert "secret plan" not in bob.get(f"/u/bob/api/sessions/{sid}").text
    # Reusing alice's id as a client-chosen session_id starts bob's own chat.
    bob.post("/u/bob/api/chat", json={"message": "bob was here", "session_id": sid})
    assert "bob was here" not in alice.get(f"/u/alice/api/sessions/{sid}").text


def test_another_owner_looks_exactly_like_a_missing_one(env):
    bob = env.as_("bob")
    foreign, missing = (
        bob.get("/u/alice/api/sessions"),
        bob.get("/u/nobody/api/sessions"),
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_signed_out_api_gets_401_and_pages_go_to_login(env):
    anon = env.anon()
    r = anon.get("/u/alice/api/sessions")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "signed_out"
    r = anon.get("/u/alice/?session=abc")
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Fu%2Falice%2F%3Fsession%3Dabc"


def test_the_chat_page_and_its_assets_live_under_the_prefix(env):
    html = env.as_("alice").get("/u/alice/").text
    assert re.search(r'"base_path":\s*"/u/alice"', html)
    assert (
        '"login_url": "/login?next={next}"' in html
        or '"login_url":"/login?next={next}"' in html
    )
    assets = sorted(set(re.findall(r'(?:src|href)="(/u/alice/static/[^"]+)"', html)))
    assert assets, html[:500]
    for url in assets:
        assert env.as_("alice").get(url).status_code == 200, url
    assert env.as_("bob").get(assets[0]).status_code == 404


def test_a_non_slug_user_id_never_becomes_a_path(env):
    with pytest.raises(ValueError):
        env.mu.home("../alice")
    # an encoded ".." owner is just another missing user
    assert env.as_("root").get("/u/%2e%2e/api/sessions").status_code == 404


def test_each_user_has_their_own_directory(env):
    env.as_("alice").chat("alice", "hi")
    env.as_("bob").chat("bob", "hi")
    for user in ("alice", "bob"):
        assert (env.data / "users" / user / "chat.db").exists()
