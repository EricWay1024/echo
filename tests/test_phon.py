"""Lexique SAMPA→IPA mapping + word lookup (offline; espeak not required)."""

from echo import phon


def test_sampa_to_ipa_known():
    assert phon.sampa_to_ipa("dolaR") == "dolaʁ"
    assert phon.sampa_to_ipa("b§ZuR") == "bɔ̃ʒuʁ"   # bonjour
    assert phon.sampa_to_ipa("gR@") == "ɡʁɑ̃"        # grand
    assert phon.sampa_to_ipa("k@piG") == "kɑ̃piŋ"     # camping
    assert phon.sampa_to_ipa("8it") == "ɥit"         # huit


def test_word_ipa_lexique():
    assert phon.word_ipa("vacille") == "vasij"
    assert phon.word_ipa("dollar") == "dolaʁ"
    # case + surrounding punctuation are stripped before lookup
    assert phon.word_ipa(" Dollar.") == "dolaʁ"


def test_word_ipa_oov_degrades_gracefully(monkeypatch):
    # With espeak unavailable, an OOV word returns None (not a crash); a Lexique
    # word still resolves. (Simulate espeak-absent so the test is deterministic.)
    monkeypatch.setattr(phon, "_phonemize", lambda text: None)
    assert phon.word_ipa("zzqxwk") is None
    assert phon.word_ipa("vacille") == "vasij"
