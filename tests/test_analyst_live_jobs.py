import api.main as m


def test_live_predict_job_uses_analyst(monkeypatch):
    called = {}
    monkeypatch.setattr(m, "_analyst_predict_for_date",
                        lambda d, mode: called.setdefault("predict", (d, mode)))
    m._generate_predictions_today()
    assert called["predict"][1] == "live"


def test_actuals_job_also_archives(monkeypatch):
    seq = []
    monkeypatch.setattr(m, "record_actuals_for_date", lambda d: seq.append(("actuals", d)))
    monkeypatch.setattr(m, "archive_signals_for_date", lambda d: seq.append(("archive", d)))
    m._record_predictions_actuals()
    assert [s[0] for s in seq] == ["actuals", "archive"]
