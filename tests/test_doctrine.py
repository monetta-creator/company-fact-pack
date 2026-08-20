"""Unit tests for the doctrine mechanisms: gate, tagger, deterministic verify,
chunker table atomicity, deep-loop caps. These are the enforcement artifacts —
if one fails, a doctrine principle is absent.
"""

from factpack import citations, config, verify
from factpack.tags import Tagger
from scripts.compile.chunk import pack_section, split_sections


# --- D5: citation gate ---

def test_gate_keeps_allowlisted_and_drops_foreign():
    allow = {"C1", "obs:abc123", "ent:cof"}
    text = "Revenue rose. [C1] CET1 was strong. [obs:abc123] Made up. [C9] Also [ent:dfs]."
    res = citations.enforce(text, allow)
    assert "[C1]" in res.text and "[obs:abc123]" in res.text
    assert "[C9]" not in res.text and "[ent:dfs]" not in res.text
    assert res.audit == ["C9", "ent:dfs"]          # dropped + audited
    assert res.citations == ["C1", "obs:abc123"]   # first-use order


def test_gate_never_repairs():
    res = citations.enforce("Claim. [C2]", {"C1"})
    assert "[C1]" not in res.text  # a wrong citation is never guessed into a plausible one
    assert res.audit == ["C2"]


# --- D7/D8: tagger ---

def test_tagger_shared_counter_and_seeding():
    t = Tagger({"C3": "chunk-x"})
    assert t.mint("chunk-x") == "C3"      # rediscovered chunk keeps its original tag
    assert t.mint("chunk-y") == "C4"      # counter continues past the seed
    assert t.mint("chunk-y") == "C4"      # idempotent per chunk


# --- D6: deterministic verify ---

def test_verify_flags_unsupported_quote_and_number():
    pack_text = 'The company reported net income of $4,582 million for the year.'
    rep = verify.deterministic(
        'It earned "net income of $4,582 million" [C1]. Charge-offs hit 9.99% [C1].',
        pack_text, obs_values=[],
    )
    kinds = [f["kind"] for f in rep.flags]
    assert "quote" not in kinds           # exact quote passes
    assert "number" in kinds              # 9.99 appears nowhere


def test_verify_accepts_observation_values():
    rep = verify.deterministic("The rate was 4.62% [obs:x].", "", obs_values=[4.62])
    assert not rep.flags


# --- D1: chunker table atomicity ---

def test_tables_are_never_split():
    big_table = "[TABLE]\n" + "\n".join(f"row {i} | {i * 100}" for i in range(400)) + "\n[/TABLE]"
    text = ("Intro paragraph. " * 50) + "\n\n" + big_table + "\n\n" + ("Outro. " * 50)
    chunks = pack_section(text)
    table_chunks = [c for c in chunks if "[TABLE]" in c]
    assert len(table_chunks) == 1
    assert table_chunks[0].startswith("[TABLE]") and table_chunks[0].endswith("[/TABLE]")
    # no chunk contains a partial table
    for c in chunks:
        assert c.count("[TABLE]") == c.count("[/TABLE]")


def test_item_sections_never_merge():
    text = (
        "ITEM 1. Business\n" + ("About the business. " * 200)
        + "\nITEM 1A. Risk Factors\n" + ("Risks described here. " * 200)
        + "\nITEM 7. MD&A\n" + ("Analysis text. " * 200)
    )
    sections = split_sections(text, "10-K")
    ids = [s for s, _ in sections]
    assert any("ITEM1A" in s for s in ids) and any("ITEM7" in s for s in ids)
    # a chunk from ITEM 1A must not contain ITEM 7 text
    for sid, stext in sections:
        if "ITEM1A" in sid:
            assert "Analysis text" not in stext


# --- D7: caps exist and are sane ---

def test_deep_caps_are_bounded_constants():
    assert config.MAX_ROUNDS <= 6
    assert config.MAX_CALLS_PER_ROUND <= 8
    assert config.RESULT_CAP_CHARS <= 4000
    assert config.TOTAL_TOOL_CHARS <= 100_000
    assert config.WALL_CLOCK_CAP_S <= 600
