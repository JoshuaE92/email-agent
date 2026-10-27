from eval.metrics import passes, score
from eval.run_eval import main as eval_main


def row(id, exp_act, got_act, exp_dl=None, got_dl=None, cat="career", got_cat="career",
        urg="low", got_urg="low", invalid=False):
    got = None if invalid else {"is_actionable": got_act, "deadline": got_dl,
                                "category": got_cat, "urgency": got_urg}
    return {"id": id, "expected": {"is_actionable": exp_act, "deadline": exp_dl,
                                   "category": cat, "urgency": urg},
            "got": got, "valid_first_try": not invalid, "latency_s": 1.0, "tokens": 100}


def test_precision_recall_f1():
    rows = [row("a", True, True, "2026-10-30", "2026-10-30"),
            row("b", True, False, "2026-10-30"),           # miss
            row("c", False, True),                          # false alarm
            row("d", False, False)]
    m = score(rows)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5


def test_invalid_output_counts_as_a_miss():
    m = score([row("a", True, None, "2026-10-30", invalid=True)])
    assert m["recall"] == 0 and m["json_valid_after_retry"] == 0
    assert m["mistakes"][0][3] == "INVALID OUTPUT"


def test_deadline_exact_and_within_one_day():
    rows = [row("a", True, True, "2026-10-30", "2026-10-30"),
            row("b", True, True, "2026-10-30", "2026-10-31"),
            row("c", True, True, "2026-10-30", None),
            row("d", True, True, None, None)]
    m = score(rows)
    assert m["deadline_exact"] == 0.5 and m["deadline_within1"] == 0.75


def test_pass_bar():
    good = score([row(str(i), True, True, "2026-10-30", "2026-10-30") for i in range(20)])
    assert passes(good)
    bad = score([row(str(i), True, True, "2026-10-30", "2026-11-30") for i in range(20)])
    assert not passes(bad)


def test_harness_runs_end_to_end_offline(capsys):
    results = eval_main(["--mock", "--quiet", "--limit", "10"])
    assert results[0]["n"] == 10
    assert "Recall*" in capsys.readouterr().out
