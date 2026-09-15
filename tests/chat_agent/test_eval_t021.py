"""Model/discovery evaluation harness placeholder (T021). Live model results are separate evidence."""

from pathlib import Path
import json

DATASET = Path(__file__).resolve().parents[2] / "tests" / "chat_agent" / "eval_dataset.json"


def test_eval_dataset_exists_and_has_no_fabricated_passed_checks():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(data["cases"]) >= 3
    for case in data["cases"]:
        assert "expected" in case
        if "checks" in case["expected"]:
            for check in case["expected"]["checks"]:
                assert check["outcome"] in {"passed", "failed", "not_run"}
                # Dataset must not claim passed without evidence flag
                if check["outcome"] == "passed":
                    assert check.get("evidence") 


def test_architecture_question_expects_no_run():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    arch = next(c for c in data["cases"] if c["id"] == "arch-q")
    assert arch["expected"]["run"] is False
