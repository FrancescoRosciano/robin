import json
from robin.ndjson import interim, final


def test_interim_line():
    line = interim("Let me check that.")
    assert line.endswith("\n")
    assert json.loads(line) == {"text": "Let me check that.", "interim": True}


def test_final_line_plain():
    assert json.loads(final("Done."))["text"] == "Done."
    assert "interim" not in json.loads(final("Done."))


def test_final_with_hangup():
    obj = json.loads(final("Bye.", hangup=True))
    assert obj == {"text": "Bye.", "hangup": True}
