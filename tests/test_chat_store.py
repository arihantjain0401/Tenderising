from tenderising.chat import store


def test_session_lifecycle(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(provider="ollama", model="qwen3:8b", db_path=db)
    assert sid
    sessions = store.list_sessions(db_path=db)
    assert len(sessions) == 1
    assert sessions[0]["id"] == sid
    assert sessions[0]["title"] is None
    assert sessions[0]["provider"] == "ollama"


def test_messages_roundtrip_and_title(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(db_path=db)
    store.add_message(sid, "user", "how many bids are there?", db_path=db)
    store.add_message(
        sid,
        "assistant",
        "502 bids",
        tool_rounds=[{"tool": "get_stats", "arguments": {}, "result": {}}],
        db_path=db,
    )
    msgs = store.get_messages(sid, db_path=db)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "how many bids are there?"
    assert msgs[1]["content"] == "502 bids"
    assert msgs[1]["tool_rounds"][0]["tool"] == "get_stats"
    # Title is auto-derived from the first user message.
    assert store.list_sessions(db_path=db)[0]["title"] == "how many bids are there?"


def test_provider_model_recorded_per_message_and_session(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(db_path=db)
    store.add_message(sid, "user", "q", provider="deepseek", model="deepseek-chat", db_path=db)
    store.add_message(
        sid, "assistant", "a", provider="deepseek", model="deepseek-chat", db_path=db
    )
    msgs = store.get_messages(sid, db_path=db)
    assert msgs[0]["provider"] == "deepseek" and msgs[0]["model"] == "deepseek-chat"
    assert msgs[1]["provider"] == "deepseek"
    # Session is stamped from the first user message.
    sess = store.list_sessions(db_path=db)[0]
    assert sess["provider"] == "deepseek" and sess["model"] == "deepseek-chat"


def test_migrate_legacy_table_adds_columns(tmp_path):
    # Simulate a pre-existing messages table without provider/model columns.
    import sqlite3

    db = tmp_path / "chat.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, provider TEXT, model TEXT, "
        "created_at TEXT, updated_at TEXT)"
    )
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, "
        "role TEXT, content TEXT, tool_rounds TEXT, created_at TEXT)"
    )
    con.commit()
    con.close()
    # Opening the store migrates it; writes with provider/model must succeed.
    sid = store.create_session(db_path=db)
    store.add_message(sid, "user", "hi", provider="ollama", model="qwen3:8b", db_path=db)
    assert store.get_messages(sid, db_path=db)[0]["model"] == "qwen3:8b"


def test_title_truncates_long_first_message(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(db_path=db)
    store.add_message(sid, "user", "x" * 100, db_path=db)
    assert len(store.list_sessions(db_path=db)[0]["title"]) == 48


def test_delete_session_removes_messages(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(db_path=db)
    store.add_message(sid, "user", "hello", db_path=db)
    store.delete_session(sid, db_path=db)
    assert store.list_sessions(db_path=db) == []
    assert store.get_messages(sid, db_path=db) == []


def test_list_sessions_newest_first(tmp_path):
    db = tmp_path / "chat.db"
    a = store.create_session(db_path=db)
    b = store.create_session(db_path=db)
    store.add_message(a, "user", "touch a", db_path=db)
    ids = [s["id"] for s in store.list_sessions(db_path=db)]
    assert ids[0] == a
    assert ids[1] == b


def test_user_id_assigned_and_filtered(tmp_path):
    db = tmp_path / "chat.db"
    a = store.create_session(user_id="1", db_path=db)
    b = store.create_session(user_id="2", db_path=db)
    assert [s["id"] for s in store.list_sessions(user_id="1", db_path=db)] == [a]
    assert [s["id"] for s in store.list_sessions(user_id="2", db_path=db)] == [b]
    assert store.get_session(a, db_path=db)["user_id"] == "1"


def test_widgets_roundtrip(tmp_path):
    db = tmp_path / "chat.db"
    sid = store.create_session(db_path=db)
    assert store.get_session(sid, db_path=db)["widgets"] is None
    widgets = [{"id": "w1", "kind": "bid_table", "title": "t", "data": {"total": 3}}]
    store.set_widgets(sid, widgets, db_path=db)
    assert store.get_session(sid, db_path=db)["widgets"] == widgets
