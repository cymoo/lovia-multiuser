import time

from conftest import session_ids


def test_disabling_signs_the_user_out_and_stops_their_app(env):
    alice = env.as_("alice")
    alice.chat("alice", "hi")
    assert env.mu.tenants.is_live("alice")

    assert env.as_("root").post("/admin/users/alice/disable").status_code == 303
    assert alice.get("/u/alice/api/sessions").status_code == 401
    assert alice.get("/").headers["location"].startswith("/login")
    assert not env.mu.tenants.is_live("alice")


def test_admin_still_reads_a_disabled_users_records(env):
    sid = env.as_("alice").chat("alice", "secret plan")
    root = env.as_("root")
    root.post("/admin/users/alice/disable")

    assert session_ids(root.get("/u/alice/api/sessions")) == [sid]
    assert "账号已停用" in root.get("/u/alice/").text
    # served by a dormant app: reading it didn't revive the user's background work
    assert not env.mu.tenants.is_live("alice")


def test_a_disabled_users_schedules_stop_firing(env):
    alice, bob, root = env.as_("alice"), env.as_("bob"), env.as_("root")
    alice.chat("alice", "hi")
    bob.chat("bob", "hi")
    spec = {
        "input": "ping",
        "trigger_kind": "at",
        "trigger_expr": str(time.time() + 0.5),
    }
    a = alice.post("/u/alice/api/schedules", json=spec).json()["id"]
    b = bob.post("/u/bob/api/schedules", json=spec).json()["id"]

    root.post("/admin/users/alice/disable")
    deadline = time.time() + 5
    while bob.get(f"/u/bob/api/schedules/{b}").json()["fire_count"] == 0:
        assert time.time() < deadline, "control schedule never fired"
        time.sleep(0.05)
    time.sleep(0.3)  # alice's slot is equally due by now

    info = root.get(f"/u/alice/api/schedules/{a}").json()
    assert info["fire_count"] == 0 and info["active"]


def test_enabling_brings_the_user_back(env):
    alice, root = env.as_("alice"), env.as_("root")
    sid = alice.chat("alice", "hi")
    root.post("/admin/users/alice/disable")
    root.post("/admin/users/alice/enable")
    assert env.mu.tenants.is_live("alice")
    assert session_ids(alice.get("/u/alice/api/sessions")) == [sid]


def test_admin_cannot_disable_themselves(env):
    assert env.as_("root").post("/admin/users/root/disable").status_code == 400
    assert env.as_("root").get("/admin").status_code == 200


def test_reconcile_catches_changes_made_outside_the_process(env):
    env.as_("alice").chat("alice", "hi")
    directory = env.mu.directory

    # As `lovia-multiuser users disable` would, from another process.
    env.run(directory.set_disabled, "alice", True)
    assert env.mu.tenants.is_live("alice")  # not noticed yet
    env.run(env.mu.reconcile)
    assert not env.mu.tenants.is_live("alice")

    env.run(directory.set_disabled, "alice", False)
    env.run(env.mu.reconcile)
    assert env.mu.tenants.is_live("alice")
