import time

from conftest import PASSWORD, Browser

from lovia_multiuser.auth import COOKIE


def login(env, user_id, password=PASSWORD, next="/"):
    return env.anon().post(
        "/login", data={"user_id": user_id, "password": password, "next": next}
    )


def test_login_sets_a_hardened_cookie_and_returns_to_next(env):
    r = login(env, "alice", next="/u/alice/?session=abc")
    assert r.status_code == 303
    assert r.headers["location"] == "/u/alice/?session=abc"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    # the issued cookie works
    session = r.cookies[COOKIE]
    assert Browser(env.client, session).get("/u/alice/api/sessions").status_code == 200


def test_user_id_is_case_insensitive_at_sign_in(env):
    assert login(env, " Alice ").headers["location"] == "/"


def test_wrong_password_and_unknown_user_fail_alike(env):
    for user_id, password in (("alice", "wrong password"), ("nobody", PASSWORD)):
        r = login(env, user_id, password)
        assert r.status_code == 401
        assert "用户名或密码错误" in r.text
        assert COOKIE not in r.cookies


def test_next_cannot_redirect_off_site(env):
    for target in ("//evil.example/x", "https://evil.example", "/\\evil.example", ""):
        assert login(env, "alice", next=target).headers["location"] == "/"


def test_disabled_user_cannot_sign_in(env):
    env.run(env.mu.directory.set_disabled, "bob", True)
    r = login(env, "bob")
    assert r.status_code == 403 and "该账号已停用" in r.text


def test_forged_and_expired_cookies_are_rejected(env):
    good = env.mu.auth.issue("alice")
    forged = "bob" + good[len("alice") :]  # alice's signature, bob's id
    expired = env.mu.auth.issue("alice", now=time.time() - 8 * 86400)
    for cookie in (forged, expired, "garbage", "a.b.c"):
        r = Browser(env.client, cookie).get("/u/alice/api/sessions")
        assert r.status_code == 401, cookie


def test_logout_clears_the_cookie_and_the_drafts(env):
    r = env.as_("alice").post("/logout")
    assert r.status_code == 303 and r.headers["location"] == "/login?bye=1"
    assert (
        f'{COOKIE}=""' in r.headers["set-cookie"]
        or "Max-Age=0" in r.headers["set-cookie"]
    )
    page = env.anon().get("/login?bye=1").text
    assert "已退出登录" in page and "lovia-draft:" in page


def test_home_routes_by_role(env):
    assert env.anon().get("/").headers["location"] == "/login?next=%2F"
    assert env.as_("alice").get("/").headers["location"] == "/u/alice/"
    assert env.as_("root").get("/").headers["location"] == "/admin"
