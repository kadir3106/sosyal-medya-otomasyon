import json
from pathlib import Path

import pytest

from app.jsonstore import locked_json, read_json, write_atomic


def test_write_atomic_leaves_no_partial_file_on_failure(tmp_path, monkeypatch):
    """A failed write must not leave a half-written file behind."""
    target = tmp_path / "state.json"
    target.write_text(json.dumps({"keep": True}), encoding="utf-8")

    class Boom(Exception):
        pass

    def exploding_dump(obj, fh, **kwargs):
        fh.write('{"partial": ')
        raise Boom()

    monkeypatch.setattr(json, "dump", exploding_dump)
    with pytest.raises(Boom):
        write_atomic(target, {"new": 1})
    monkeypatch.undo()

    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == [], f"temp files left behind: {leftovers}"


def test_read_json_moves_corrupt_file_aside(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("{broken", encoding="utf-8")

    assert read_json(target, {"used_topics": []}) == {"used_topics": []}
    assert target.with_suffix(".json.corrupt").read_text(encoding="utf-8") == "{broken"


def test_locked_json_round_trips_and_creates_parent(tmp_path):
    target = tmp_path / "nested" / "state.json"

    with locked_json(target, {"used_topics": []}) as state:
        state["used_topics"].append("t1")

    assert json.loads(target.read_text(encoding="utf-8")) == {"used_topics": ["t1"]}
