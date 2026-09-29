from conftest import session_ids


def test_admin_reads_any_space_but_cannot_change_it(env):
    alice, root = env.as_("alice"), env.as_("root")
    sid = alice.chat("alice", "secret plan")

    assert session_ids(root.get("/u/alice/api/sessions")) == [sid]
    assert "secret plan" in root.get(f"/u/alice/api/sessions/{sid}").text

    r = root.post("/u/alice/api/chat", json={"message": "hijack", "session_id": sid})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "read_only"
    assert root.delete(f"/u/alice/api/sessions/{sid}").status_code == 403
    assert session_ids(alice.get("/u/alice/api/sessions")) == [sid]


def test_console_is_for_admins_only(env):
    assert env.as_("alice").get("/admin").status_code == 404
    assert env.as_("alice").get("/admin/users/bob").status_code == 404
    r = env.anon().get("/admin/audit")
    assert (
        r.status_code == 303 and r.headers["location"] == "/login?next=%2Fadmin%2Faudit"
    )


def test_console_lists_users_and_their_recent_chats(env):
    sid = env.as_("alice").chat("alice", "quarterly report")
    page = env.as_("root").get("/admin").text
    for text in ("Alice", "Bob", "Root", "管理员", 'href="/u/bob/"'):
        assert text in page
    assert f'href="/u/alice/?session={sid}"' in page and "quarterly report" in page


def test_browsing_the_console_creates_no_data(env):
    env.as_("root").get("/admin")
    env.as_("root").get("/admin/users/bob")
    env.as_("root").get("/admin/search?q=x")
    assert not (env.data / "users" / "bob").exists()


def test_user_page_links_each_chat_into_the_read_only_ui(env):
    sid = env.as_("alice").chat("alice", "quarterly report")
    page = env.as_("root").get("/admin/users/alice").text
    assert f'href="/u/alice/?session={sid}"' in page
    assert "停用账号" in page and "（只读）" in page
    assert env.as_("root").get("/admin/users/nobody").status_code == 404
    # no disable button on your own page
    assert "停用账号" not in env.as_("root").get("/admin/users/root").text


def test_search_spans_every_user(env):
    a = env.as_("alice").chat("alice", "quarterly report")
    b = env.as_("bob").chat("bob", "quarterly budget")
    both = env.as_("root").get("/admin/search?q=quarterly").text
    assert f"/u/alice/?session={a}" in both and f"/u/bob/?session={b}" in both
    only = env.as_("root").get("/admin/search?q=budget").text
    assert f"/u/bob/?session={b}" in only and f"/u/alice/?session={a}" not in only


def test_chat_page_shows_who_is_looking(env):
    admin_view = env.as_("root").get("/u/alice/").text
    assert "只读查看" in admin_view and "Alice" in admin_view
    assert "#composer { display: none !important; }" in admin_view
    assert 'href="/admin/users/alice"' in admin_view

    own = env.as_("alice").get("/u/alice/").text
    assert "只读查看" not in own and "#composer { display: none" not in own
    assert "退出登录" in own and 'href="/admin"' not in own
    assert 'href="/admin"' in env.as_("root").get("/u/root/").text
