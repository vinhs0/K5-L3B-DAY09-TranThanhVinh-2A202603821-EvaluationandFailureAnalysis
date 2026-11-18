"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    if not isinstance(pr, dict) or not isinstance(base, dict):
        return ["report is not a JSON object"]
    man = pr.get("manifest") if isinstance(pr.get("manifest"), dict) else {}
    bman = base.get("manifest") if isinstance(base.get("manifest"), dict) else {}
    if not man:
        problems.append("manifest missing")
    for key in ("rows", "metrics"):
        if key not in pr:
            problems.append(f"report has no '{key}'")
    rows = pr.get("rows") if isinstance(pr.get("rows"), list) else []
    brows = base.get("rows") if isinstance(base.get("rows"), list) else []
    metrics = pr.get("metrics") if isinstance(pr.get("metrics"), dict) else {}

    # 1. non-finite numbers anywhere in metrics (nested) and rows
    for path, v in _numbers(metrics, "metrics"):
        if not math.isfinite(v):
            problems.append(f"{path} is {v} (NaN/inf is not a score)")
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            problems.append(f"row {i} is not an object")
            continue
        for path, v in _numbers(r, f"rows[{i}]"):
            if not math.isfinite(v):
                problems.append(f"{path} is {v} (NaN/inf is not a score)")
    rows = [r for r in rows if isinstance(r, dict)]
    brows = [r for r in brows if isinstance(r, dict)]

    # 2. evaluator failures
    if "evaluator_failures" not in pr:
        problems.append("evaluator_failures missing from report")
    elif pr["evaluator_failures"]:
        ef = pr["evaluator_failures"]
        n = len(ef) if hasattr(ef, "__len__") else 1
        first = ef[0] if isinstance(ef, list) and ef else ef
        problems.append(f"{n} evaluator failure(s) on this run, first: {first}")

    # 3. row accounting: count, duplicates, manifest, baseline (item, seed) set
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if any(k[0] is None or k[1] is None for k in keys):
        problems.append("some rows lack item_id or seed")
    seeds = man.get("seeds")
    n_items = man.get("items")
    if isinstance(seeds, list) and isinstance(n_items, int):
        if len(set(seeds)) != len(seeds):
            problems.append(f"manifest seeds contain duplicates: {seeds}")
        want = n_items * len(set(seeds))
        if len(rows) != want:
            problems.append(f"{len(rows)} rows but manifest says {n_items} items x {len(set(seeds))} seeds = {want}")
    else:
        problems.append("manifest lacks items/seeds")
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicated (item_id, seed) rows: {dup[:5]}{' ...' if len(dup) > 5 else ''}")
    kset = set(keys)
    if isinstance(seeds, list):
        extra = {k for k in kset if k[1] not in seeds}
        if extra:
            problems.append(f"rows with seeds outside the manifest: {sorted(extra, key=str)[:5]}")
        if isinstance(n_items, int) and len({k[0] for k in kset}) != n_items:
            problems.append(f"{len({k[0] for k in kset})} distinct items in rows but manifest says {n_items}")
    bkset = {(r.get("item_id"), r.get("seed")) for r in brows}
    if kset != bkset:
        missing, added = sorted(bkset - kset, key=str), sorted(kset - bkset, key=str)
        problems.append(f"(item, seed) set differs from the baseline: {len(missing)} missing {missing[:3]}, "
                        f"{len(added)} extra {added[:3]}")
    if isinstance(spec.get("seeds"), list) and isinstance(seeds, list) and sorted(spec["seeds"]) != sorted(seeds):
        problems.append(f"manifest seeds {seeds} differ from the spec's {spec['seeds']}")
    if isinstance(bman.get("seeds"), list) and isinstance(seeds, list) and sorted(bman["seeds"]) != sorted(seeds):
        problems.append(f"manifest seeds {seeds} differ from the baseline's {bman['seeds']}")
    if bman.get("items") is not None and n_items is not None and bman["items"] != n_items:
        problems.append(f"manifest items {n_items} differ from the baseline's {bman['items']}")
    if spec.get("eval_set") and man.get("eval_set") and spec["eval_set"] != man["eval_set"]:
        problems.append(f"report ran eval set {man['eval_set']} but the spec names {spec['eval_set']}")
    if man.get("metric_spec_version") and bman.get("metric_spec_version") \
            and man["metric_spec_version"] != bman["metric_spec_version"]:
        problems.append("metric_spec_version differs from the baseline's")

    # 4. every graded spec metric: valid in every row, and present in the report's metrics
    graded = [m["id"] for m in spec.get("metrics", []) if any(m["id"] in r for r in rows + brows)]
    for mid in graded:
        bad = [r.get("item_id") for r in rows if not _is_score(r.get(mid))]
        if bad:
            problems.append(f"{len(bad)} row(s) have no valid value for graded metric {mid} "
                            f"(None/NaN/missing), e.g. {bad[:3]}")
    for m in spec.get("metrics", []):
        mid = m["id"]
        if mid not in metrics:
            if m.get("blocking") or mid in graded:
                problems.append(f"spec metric {mid} is missing from the report's metrics")
        elif metrics[mid] is None and m.get("blocking"):
            problems.append(f"blocking metric {mid} is None in the report")
    # reported metrics must be what the rows say (no hand-edited numbers)
    try:
        ids = [i for i in graded if rows and all(_is_score(r.get(i)) for r in rows)]
        if rows and not dup and ids:
            again = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], ids, k_values=spec.get("pass_k", []))
            for k, v in again.items():
                mv = metrics.get(k)
                if isinstance(v, (int, float)) and isinstance(mv, (int, float)) and not isinstance(mv, bool) \
                        and math.isfinite(mv) and abs(v - mv) > 1e-3:
                    problems.append(f"reported {k}={mv} but the rows give {v}")
    except Exception as e:  # rows that cannot be re-aggregated are not trustworthy
        problems.append(f"cannot re-aggregate rows: {type(e).__name__}: {e}")

    # 5. slice tags must match the baseline's and be consistent per item
    def tags(rs):
        out: dict = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pt, bt = tags(rows), tags(brows)
    for item, ts in sorted(pt.items(), key=lambda kv: str(kv[0])):
        if len(ts) > 1:
            problems.append(f"item {item} has inconsistent slice tags across seeds")
        elif item in bt and ts != bt[item]:
            problems.append(f"item {item} slice tags {sorted(ts)} differ from the baseline's {sorted(bt[item])}")

    # 6. ratchet against the spec on main (same eval-set version only)
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _numbers(obj, path):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield path, float(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _numbers(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _numbers(v, f"{path}[{i}]")


def _is_score(v) -> bool:
    return isinstance(v, (bool, int, float)) and math.isfinite(float(v))


def _ratchet_entry(label: str, new: dict | None, old: dict, inline: bool) -> list[str]:
    if new is None:
        return [f"ratchet: {label} was removed from the spec"]
    out = []
    nt = new if inline else (new.get("threshold") or {})
    ot = old if inline else (old.get("threshold") or {})
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"ratchet: {label} is no longer blocking")
    if "metric" in old and new.get("metric") != old["metric"]:
        out.append(f"ratchet: {label} now measures {new.get('metric')} instead of {old['metric']}")
    for k in ("max", "max_increase"):
        if k in ot and (k not in nt or nt[k] > ot[k]):
            out.append(f"ratchet: {label} {k} loosened {ot[k]} -> {nt.get(k)}")
    if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
        out.append(f"ratchet: {label} min loosened {ot['min']} -> {nt.get('min')}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append(f"ratchet: {label} dropped no_significant_drop")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        out += _ratchet_entry(f"metric {m['id']}", new_m.get(m["id"]), m, inline=False)
    new_s = {s["name"]: s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        out += _ratchet_entry(f"slice {s['name']}", new_s.get(s["name"]), s, inline=True)
    for k in ("eval_set", "labels", "adversarial_pack"):
        if base_spec.get(k) != spec.get(k):
            out.append(f"ratchet: spec {k} changed {base_spec.get(k)} -> {spec.get(k)} on the same eval-set version")
    if sorted(base_spec.get("seeds") or []) != sorted(spec.get("seeds") or []):
        out.append(f"ratchet: spec seeds changed {base_spec.get('seeds')} -> {spec.get('seeds')}")
    ob, nb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if nb.get("confidence", 0.95) < ob.get("confidence", 0.95):
        out.append("ratchet: bootstrap confidence lowered")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        label_id = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "MISSING"               # an empty slice must not pass silently
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if "max" in sl and val > sl["max"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(label_id)
        tag = "ok" if verdict == "ok" else ("MISSING" if verdict == "MISSING" else ("BLOCK" if sl.get("blocking") else "warn"))
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        lines.append(f"  {label_id:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {tag} (n={len(a)})")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
