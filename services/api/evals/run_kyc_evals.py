"""Run the 12 specimen applicants through Smart KYC and compare with evals/kyc_expected.yaml.

    .venv/bin/python -m evals.run_kyc_evals [-v]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent


def run(verbose: bool = False) -> int:
    from app import store
    store.use_memory()
    from app.kyc import consent, pipeline
    from app.kyc.models import KycCase

    expected = yaml.safe_load((HERE / "kyc_expected.yaml").read_text())
    ok_count = 0
    for applicant, exp in expected.items():
        case = KycCase()
        case.consent_id = consent.record(case.id, ["kyc_verification"], "en")["id"]
        pipeline.load_sample(case, applicant)
        pipeline.verify(case)
        raised = {c.code for c in case.checks if c.status not in ("pass", "info")}
        infos = {c.code for c in case.checks if c.status == "info"}
        problems = []
        if case.verdict != exp["verdict"]:
            problems.append(f"verdict {case.verdict} != {exp['verdict']}")
        missing = set(exp.get("codes", [])) - raised
        if missing:
            problems.append(f"missing {sorted(missing)}")
        missing_info = set(exp.get("info", [])) - infos - raised
        if missing_info:
            problems.append(f"missing info {sorted(missing_info)}")
        ok = not problems
        ok_count += ok
        print(f"{'PASS' if ok else 'FAIL'}  {applicant}  {case.verdict:<12} raised={sorted(raised)}" + ("" if ok else "  ← " + "; ".join(problems)))
        if verbose or not ok:
            for c in case.checks:
                if c.status != "pass":
                    print(f"        [{c.status}] {c.code}: {c.title} — {c.message}")
    print(f"\n{ok_count}/{len(expected)} applicants match the expected verdict")
    return 0 if ok_count == len(expected) else 1


if __name__ == "__main__":
    sys.exit(run("-v" in sys.argv))
