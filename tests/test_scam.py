from backend.app import scam

LISTING = {"title": "iPhone 15 Pro", "category": "Phones", "price": 420.0, "ref_price": 880.0,
           "condition": "New", "description": "sealed"}
OLD_SELLER = {"handle": "maya", "joined_days_ago": 400, "completed_sales": 150, "rating": 4.9}
NEW_SELLER = {"handle": "deals", "joined_days_ago": 3, "completed_sales": 0, "rating": None}
FAIR = {**LISTING, "price": 850.0}


def chat(*lines):
    return [{"sender": s, "text": t} for s, t in lines]


def keys(signals):
    return {s["key"] for s in signals}


# ---------- rules ----------

def test_friends_and_family_request_from_seller_is_a_strong_signal():
    sig = scam.rule_signals(FAIR, OLD_SELLER, chat(("buyer", "hi"), ("seller", "send it friends and family pls")))
    hit = next(s for s in sig if s["key"] == "friends_family")
    assert hit["strong"] and hit["line"] == 2


def test_rules_only_read_seller_lines():
    sig = scam.rule_signals(FAIR, OLD_SELLER, chat(("buyer", "can I pay friends & family to save fees?"),
                                                   ("seller", "no, please use the checkout")))
    assert "friends_family" not in keys(sig)


def test_obfuscated_and_off_platform_variants():
    sig = scam.rule_signals(FAIR, OLD_SELLER, chat(("seller", "f & f only"), ("seller", "or apple gift card works")))
    assert {"friends_family", "off_platform"} <= keys(sig)


def test_lookalike_payment_link_is_strong_but_ordinary_links_are_weak():
    bad = {s["key"]: s for s in scam.rule_signals(FAIR, OLD_SELLER, chat(("seller", "pay at https://paypa1-secure-checkout.com/x")))}
    ok = {s["key"]: s for s in scam.rule_signals(FAIR, OLD_SELLER, chat(("seller", "more photos: https://imgur.com/a/1")))}
    assert bad["lookalike_link"]["strong"]
    assert "lookalike_link" not in ok and not ok["external_link"]["strong"]


def test_price_anomaly_and_new_seller_are_weak_signals():
    sig = {s["key"]: s for s in scam.rule_signals(LISTING, NEW_SELLER, chat(("seller", "hello")))}
    assert not sig["price_anomaly"]["strong"] and not sig["new_seller"]["strong"]


def test_combined_rule_score_is_probabilistic_or():
    assert abs(scam._combine([0.5, 0.5]) - 0.75) < 1e-9
    assert scam._combine([]) == 0


# ---------- grounding ----------

def test_fabricated_quotes_are_dropped_and_wrong_line_numbers_corrected(fake_llm):
    msgs = chat(("buyer", "is it available?"), ("seller", "yes, pay friends and family and I ship today"))
    fake_llm.scam = {"risk": 0.9, "scam_type": "protection_bypass", "explanation": "x", "spell_breaker": "y",
                     "safe_next_step": "z", "evidence": [
                         {"line": 2, "quote": "pay friends and family", "why": "real"},
                         {"line": 1, "quote": "and I ship today", "why": "real quote, wrong line"},
                         {"line": 2, "quote": "send me your password", "why": "invented"}]}
    ai = scam.llm_assess(FAIR, OLD_SELLER, msgs)
    assert ai["dropped_evidence"] == 1
    assert [e["line"] for e in ai["evidence"]] == [2, 2]
    assert ai["evidence"][1].get("line_corrected")


def test_unknown_scam_type_and_out_of_range_risk_are_normalised(fake_llm):
    fake_llm.scam = {"risk": 7, "scam_type": "made_up", "evidence": []}
    ai = scam.llm_assess(FAIR, OLD_SELLER, chat(("seller", "hi")))
    assert ai["risk"] == 1.0 and ai["scam_type"] == "none"


# ---------- fused decision ----------

def test_llm_alone_without_grounded_evidence_cannot_pause(fake_llm):
    fake_llm.scam = {"risk": 0.95, "scam_type": "impersonation", "evidence": [{"line": 9, "quote": "nope"}]}
    r = scam.assess(FAIR, OLD_SELLER, chat(("seller", "the camera ships tomorrow")))
    assert r["verdict"] != "PAUSE"


def test_rules_and_llm_agreeing_pause(fake_llm):
    msgs = chat(("seller", "send $420 friends and family, no goods and services please"))
    fake_llm.scam = {"risk": 0.9, "scam_type": "protection_bypass",
                     "evidence": [{"line": 1, "quote": "friends and family", "why": "bypass"}]}
    r = scam.assess(LISTING, NEW_SELLER, msgs)
    assert r["verdict"] == "PAUSE" and r["score"] >= scam.PAUSE_AT


def test_honest_seller_warning_against_ff_is_not_paused(fake_llm):
    # The regex fires on "friends and family", but the LLM reads the intent; fusion keeps it below PAUSE.
    msgs = chat(("seller", "please don't use friends and family, use the checkout so you're protected"))
    fake_llm.scam = {"risk": 0.02, "scam_type": "none", "evidence": []}
    r = scam.assess(FAIR, OLD_SELLER, msgs)
    assert "friends_family" in keys(r["signals"]) and r["verdict"] != "PAUSE"


def test_clean_chat_is_clear(fake_llm):
    r = scam.assess(FAIR, OLD_SELLER, chat(("buyer", "still available?"), ("seller", "yes, ships tomorrow")))
    assert r["verdict"] == "CLEAR"


def test_falls_back_to_rules_when_every_llm_is_down(fake_llm):
    fake_llm.down = True
    r = scam.assess(LISTING, NEW_SELLER, chat(("seller", "zelle only, plus a $60 courier fee first")))
    assert r["ai"] is None and r["ai_error"]
    assert r["verdict"] == "PAUSE"  # two strong rules corroborate each other


def test_rules_mode_never_calls_the_llm(fake_llm):
    fake_llm.down = True
    r = scam.assess(FAIR, OLD_SELLER, chat(("seller", "hi")), mode="rules")
    assert r["verdict"] == "CLEAR" and r["ai_error"] is None
