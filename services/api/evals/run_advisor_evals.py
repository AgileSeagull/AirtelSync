"""Run advisor scenarios and print a scorecard.

    .venv/bin/python -m evals.run_advisor_evals            # scripted mode (free, deterministic)
    .venv/bin/python -m evals.run_advisor_evals --llm      # Claude mode (needs ANTHROPIC_API_KEY; costs tokens)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
NUDGES = {"en": "That's all I need, please recommend a plan.", "hi": "बस इतना ही, प्लान बताइए।"}


def load() -> list[dict]:
    return yaml.safe_load((HERE / "advisor_scenarios.yaml").read_text())


def check(s, scen: dict) -> list[str]:
    from app.data_store import catalogue
    from app.engine.eligibility import validate_bundle
    from app.engine.models import LineItem, Profile

    exp = scen.get("expect", {})
    fails: list[str] = []
    if exp.get("handoff"):
        if not s.handoff:
            fails.append("expected handoff")
        return fails
    rec = s.recommendation
    if not rec:
        return ["no recommendation reached"]
    prof = Profile(**rec["profile"])
    for t in rec["tiers"]:
        v = validate_bundle(prof, [LineItem(product_id=i["product_id"], qty=i["qty"]) for i in t["items"]])
        if v:
            fails.append(f"{t['tier']} breaks rules: {[x.message for x in v]}")
    if "segment" in exp and rec["segment"] != exp["segment"]:
        fails.append(f"segment {rec['segment']} != {exp['segment']}")
    tier = next(t for t in rec["tiers"] if t["tier"] == exp.get("tier", "recommended"))
    ids = [i["product_id"] for i in tier["items"]]
    qty = {i["product_id"]: i["qty"] for i in tier["items"]}
    if "first" in exp and ids[0] != exp["first"]:
        fails.append(f"first item {ids[0]} != {exp['first']}")
    for pid in exp.get("include", []):
        if pid not in ids:
            fails.append(f"missing {pid}")
    for pid in exp.get("exclude", []):
        if pid in ids:
            fails.append(f"should not include {pid}")
    for pid, n in (exp.get("qty") or {}).items():
        if qty.get(pid) != n:
            fails.append(f"qty {pid}={qty.get(pid)} != {n}")
    excluded = {e["product_id"] for e in rec["excluded"]}
    for pid in exp.get("excluded", []):
        if pid not in excluded:
            fails.append(f"{pid} not reported as unavailable")
    if exp.get("no_gst_products"):
        gst = {p.id for p in catalogue().values() if p.requires_gstin}
        for t in rec["tiers"]:
            bad = gst.intersection(i["product_id"] for i in t["items"])
            if bad:
                fails.append(f"{t['tier']} has GST-only products {sorted(bad)}")
    if "note" in exp and not any(exp["note"].lower() in n.lower() for n in rec["notes"]):
        fails.append(f"note '{exp['note']}' missing (notes: {rec['notes']})")
    return fails


async def run_one(scen: dict) -> tuple[list[str], object]:
    from app.advisor import service

    s = service.start(scen.get("lang", "en"))
    for m in scen["messages"]:
        await service.message(s, m)
    nudges = 0
    while not s.recommendation and not s.handoff and nudges < 2:
        await service.message(s, NUDGES.get(s.lang, NUDGES["en"]))
        nudges += 1
    return check(s, scen), s


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("-v", action="store_true", help="print transcripts of failures")
    args = ap.parse_args(argv)
    if not args.llm:
        os.environ["UDYAM_ADVISOR_MODE"] = "scripted"
    from app import store
    store.use_memory()

    scenarios = [s for s in load() if not args.only or s["id"] == args.only]
    passed = 0
    for scen in scenarios:
        fails, s = await run_one(scen)
        ok = not fails
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {scen['id']}" + ("" if ok else "  ← " + "; ".join(fails)))
        if not ok and args.v:
            for t in s.transcript:
                print(f"      {t.role}: {t.text}")
    print(f"\n{passed}/{len(scenarios)} scenarios passed ({'LLM' if args.llm else 'scripted'} mode)")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
