def entries(env, **kw):
    return env.run(env.mu.audit.recent, **kw)


def test_admin_views_are_recorded_with_their_outcome(env):
    sid = env.as_("alice").chat("alice", "secret plan")
    env.as_("root").get(f"/u/alice/?session={sid}")
    env.as_("root").get(f"/u/alice/api/sessions/{sid}")
    env.as_("root").get("/u/alice/api/schedules/nope")

    got = [(e.actor, e.owner, e.action, e.detail, e.status) for e in entries(env)]
    assert got == [
        ("root", "alice", "http", "GET /api/schedules/nope", 404),
        ("root", "alice", "http", f"GET /api/sessions/{sid}", 200),
        ("root", "alice", "http", f"GET /?session={sid}", 200),
    ]


def test_ui_refreshes_are_not_recorded(env):
    env.as_("alice").chat("alice", "hi")
    root = env.as_("root")
    for path in ("/api/info", "/api/agents", "/api/sessions?limit=51", "/api/runs"):
        assert root.get(f"/u/alice{path}").status_code == 200
    assert entries(env) == []


def test_denied_writes_and_probes_are_recorded(env):
    env.as_("root").post("/u/alice/api/chat", json={"message": "x"})
    env.as_("bob").get("/u/alice/api/sessions")
    got = {(e.actor, e.owner, e.detail, e.status) for e in entries(env)}
    assert got == {
        ("root", "alice", "POST /api/chat", 403),
        ("bob", "alice", "GET /api/sessions", 404),
    }


def test_own_space_and_static_assets_are_not_recorded(env):
    env.as_("alice").chat("alice", "hi")
    env.as_("alice").get("/u/alice/api/sessions")
    html = env.as_("root").get("/u/alice/").text
    asset = html.split('href="/u/alice/static/', 1)[1].split('"', 1)[0]
    env.as_("root").get(f"/u/alice/static/{asset}")
    assert [e.detail for e in entries(env)] == ["GET /"]


def test_account_actions_are_recorded_and_shown(env):
    root = env.as_("root")
    root.post("/admin/users/bob/disable")
    root.post("/admin/users/bob/enable")
    assert [(e.action, e.owner) for e in entries(env, actor="root")] == [
        ("user.enable", "bob"),
        ("user.disable", "bob"),
    ]
    page = root.get("/admin/audit?owner=bob").text
    assert "停用账号" in page and "启用账号" in page
    assert "停用账号" in root.get("/admin/users/bob").text
