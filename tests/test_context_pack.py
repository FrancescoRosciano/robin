# tests/test_context_pack.py
import json
import pytest
from robin.context_pack import load_context_pack, ContextPackError

VALID = "tests/fixtures/context_pack.valid.json"
UNFILLED = "tests/fixtures/context_pack.unfilled.json"


def test_loads_valid_pack():
    p = load_context_pack(VALID)
    assert p.caller_name == "Demo User"
    assert p.receptionist_to_number == "+15550000002"


def test_missing_file_raises():
    with pytest.raises(ContextPackError, match="not found"):
        load_context_pack("tests/fixtures/nope.json")


def test_unfilled_placeholder_raises():
    with pytest.raises(ContextPackError, match="unfilled placeholder in caller_name"):
        load_context_pack(UNFILLED)


def test_empty_field_raises(tmp_path):
    d = json.load(open(VALID))
    d["win_goal"] = ""
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="empty field: win_goal"):
        load_context_pack(str(f))


def test_bad_e164_raises(tmp_path):
    d = json.load(open(VALID))
    d["callback_number"] = "555-0001"
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="callback_number"):
        load_context_pack(str(f))


def test_missing_key_raises(tmp_path):
    d = json.load(open(VALID))
    del d["jurisdiction"]
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="missing field: jurisdiction"):
        load_context_pack(str(f))


def test_non_string_field_raises(tmp_path):
    with open(VALID, encoding="utf-8") as fh:
        d = json.load(fh)
    d["jurisdiction"] = 42
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="field must be a string: jurisdiction"):
        load_context_pack(str(f))


def test_non_dict_json_root_raises(tmp_path):
    f = tmp_path / "p.json"
    f.write_text("[]")
    with pytest.raises(ContextPackError, match="must be a JSON object"):
        load_context_pack(str(f))
