"""Slice 4: translation cache, explanation parsing/cap, lexeme upsert (offline)."""

import json
from types import SimpleNamespace

from echo import db, study


# --- db round-trips -----------------------------------------------------------
def _seed(tmp_path):
    dbp = tmp_path / "t.db"
    db.init_db(dbp)
    conn = db.connect(dbp)
    conn.execute("INSERT INTO videos (id, status) VALUES ('v', 'pipelined')")
    conn.commit()
    return conn


def test_translation_cache(tmp_path):
    conn = _seed(tmp_path)
    assert db.get_translation(conn, "v", 3, "zh") is None
    db.store_translation(conn, "v", 3, "zh", "美元在动摇")
    assert db.get_translation(conn, "v", 3, "zh") == "美元在动摇"
    assert db.get_translation(conn, "v", 3, "en") is None  # per-language


def test_explanation_cards_lexeme(tmp_path):
    conn = _seed(tmp_path)
    db.store_explanation(conn, "v", 5, 7, "en", "vaciller", "verb", "to waver")
    assert db.get_explanation(conn, "v", 5, 7)["lemma"] == "vaciller"
    db.replace_suggested_cards(conn, "v", 5, 7, [
        {"kind": "cloze", "front": "le dollar {{c1::vacille}}", "back": "wavers",
         "rationale": "key verb"},
    ])
    cards = db.load_cards(conn, "v")
    assert len(cards) == 1 and cards[0]["status"] == "suggested"
    # re-suggesting replaces prior suggestions for the span
    db.replace_suggested_cards(conn, "v", 5, 7, [
        {"kind": "vocab", "front": "vaciller", "back": "to waver", "rationale": "x"},
    ])
    assert len(db.load_cards(conn, "v")) == 1
    db.upsert_lexeme(conn, "vaciller", "fr", "learning")
    db.upsert_lexeme(conn, "vaciller", "fr", "known")  # upsert, not duplicate
    rows = conn.execute("SELECT status FROM lexemes WHERE lemma='vaciller'").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "known"


# --- study functions with a mocked LLM client ---------------------------------
class _FakeMsg:
    def __init__(self, text):
        self.content = [SimpleNamespace(type="text", text=text)]
        self.stop_reason = "end_turn"


class _FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(create=lambda **kw: _FakeMsg(text))


CFG = SimpleNamespace(llm_model="m", llm_translate_model="h", api_key="k", raw={})


def test_translate_clause(monkeypatch):
    monkeypatch.setattr(study, "_client", lambda cfg: _FakeClient("  美元在动摇  "))
    assert study.translate_clause(CFG, "le dollar vacille", "zh") == "美元在动摇"


def test_known_lemmas_in_prompt(monkeypatch):
    seen = {}

    class Rec:
        def __init__(self):
            self.messages = SimpleNamespace(
                create=lambda **kw: (seen.update(kw) or _FakeMsg('{"lemma":"x","pos":"n","lang":"en","explanation":"e","cards":[]}')))

    monkeypatch.setattr(study, "_client", lambda cfg: Rec())
    study.explain_and_suggest(CFG, "x", "clause", "fr B2", known=["dollar", "yuan"])
    user = seen["messages"][0]["content"]
    assert "dollar" in user and "yuan" in user


def test_explain_parses_and_caps(monkeypatch):
    payload = {
        "lemma": "vaciller", "pos": "verb", "lang": "en",
        "explanation": "to waver; here 3sg present.",
        "cards": [
            {"kind": "cloze", "front": "f1", "back": "b1", "rationale": "r"},
            {"kind": "vocab", "front": "f2", "back": "b2", "rationale": "r"},
            {"kind": "usage", "front": "f3", "back": "b3", "rationale": "r"},
            {"kind": "grammar", "front": "f4", "back": "b4", "rationale": "r"},
        ],
    }
    monkeypatch.setattr(study, "_client", lambda cfg: _FakeClient(json.dumps(payload)))
    out = study.explain_and_suggest(CFG, "vacille", "le dollar vacille", "fr B2")
    assert out["lemma"] == "vaciller"
    assert out["lang"] == "zh"  # fixed by config (default), not the model's "en"
    assert len(out["cards"]) == 3  # capped
