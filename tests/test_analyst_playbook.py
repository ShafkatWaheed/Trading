from api.services import analyst_playbook as pb


def test_read_autocreates_with_version_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    content = pb.read()
    assert pb._VERSION_TAG in content


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    pb.write(pb._VERSION_TAG + "\n# learned\n- tech gaps win")
    assert "tech gaps win" in pb.read()


def test_rewrite_rejects_response_missing_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    before = pb.read()
    res = pb.rewrite(history=[{"x": 1}], accuracy={}, claude=lambda *a, **k: "no tag here")
    assert res["updated"] is False
    assert pb.read() == before   # unchanged on bad response


def test_rewrite_writes_when_tag_present(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    new_md = pb._VERSION_TAG + "\n# updated\n- momentum + congress combo wins"
    res = pb.rewrite(history=[{"x": 1}], accuracy={"hit_rate": 0.3},
                     claude=lambda *a, **k: "preamble junk " + new_md)
    assert res["updated"] is True
    # preamble trimmed: file starts at the version tag
    assert pb.read().startswith(pb._VERSION_TAG)
    assert "momentum + congress combo wins" in pb.read()


def test_rewrite_no_history_skips(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    res = pb.rewrite(history=[], accuracy={}, claude=lambda *a, **k: "ignored")
    assert res["updated"] is False
