#!/usr/bin/env python3
"""Apply the mechanical screening rules and partition records for agent review.

This script deliberately decides ONLY what can be decided without judgement.
Everything else lands in screening/uncertain.jsonl for the agent to read
(escalating to full text, then to the user, per SKILL.md step 3).

Agent decisions are read back from screening/decisions.jsonl, one object per
line:

  {"uid": "...", "decision": "include"|"exclude", "rule_id": "INC-GEO-02",
   "reason": "...", "decided_by": "agent"|"user", "evidence": "abstract"|"full_text",
   "flags": ["regional_participation"]}

Decisions always override the mechanical outcome, so re-running after a
criteria amendment is safe and idempotent.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import OrderedDict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

INDUSTRY_ONLY_NOTE = ("Only Singapore link is an industry regional/branch office "
                      "(criteria EXC-GEO-02)")


# --------------------------------------------------------------------------
# Derived facts
# --------------------------------------------------------------------------

def derive(rec, resolver):
    """Everything the mechanical rules need, computed once."""
    countries, institutions, sectors = [], [], []
    for a in rec.get("authors") or []:
        for seg in a.get("affiliations") or []:
            r = resolver.resolve(seg)
            if r["country"]:
                countries.append(r["country"])
            if r["institution"]:
                institutions.append(r["institution"])
                sectors.append(r["sector"])

    sg_positions = []
    n_authors = len(rec.get("authors") or [])
    for a in rec.get("authors") or []:
        for seg in a.get("affiliations") or []:
            if resolver.resolve(seg)["country"] == "Singapore":
                sg_positions.append(a.get("position"))
                break

    text = " ".join([rec.get("title") or "", rec.get("abstract") or "",
                     " ".join(rec.get("keywords") or []),
                     " ".join(rec.get("mesh_terms") or [])])

    sg_sectors = set()
    for a in rec.get("authors") or []:
        for seg in a.get("affiliations") or []:
            r = resolver.resolve(seg)
            if r["country"] == "Singapore":
                sg_sectors.add(r["sector"] or "unknown")

    year = None
    try:
        year = int(str(rec.get("year") or "")[:4])
    except (TypeError, ValueError):
        year = None

    return {
        "affiliation_country": sorted(set(countries)),
        "institutions": sorted(set(institutions)),
        "sectors": sorted(set(s for s in sectors if s)),
        "sg_affiliation": "Singapore" in countries,
        "sg_author_positions": sg_positions,
        "sg_leading": bool(sg_positions) and (1 in sg_positions or n_authors in sg_positions),
        "sg_sectors": sorted(sg_sectors),
        "singapore_in_text": idlib.contains_term(text, "singapore"),
        "has_abstract": bool((rec.get("abstract") or "").strip()),
        "article_types": rec.get("article_types") or [],
        "language": (rec.get("language") or "").lower(),
        "year": year,
        "n_countries": len(set(countries)),
        "n_authors": n_authors,
    }


# --------------------------------------------------------------------------
# Mechanical rules
# --------------------------------------------------------------------------

def apply_mechanical(rec, facts, rules, window):
    """Returns (excludes, passes) as lists of (rule_id, reason)."""
    excludes, passes = [], []

    for rule in rules:
        rid = rule["rule_id"]
        field = rule.get("applies_to")
        op = rule.get("operator")
        val = rule.get("value")
        outcome = rule.get("outcome")
        fired, reason = False, ""

        if field == "affiliation_country" and op == "any_equals":
            if val in facts["affiliation_country"]:
                fired, reason = True, "author affiliated in %s" % val

        elif field == "article_types" and op == "any_in":
            hits = [t for t in facts["article_types"] if t in (val or [])]
            if hits:
                fired, reason = True, "publication type %s" % ", ".join(hits)

        elif field == "language" and op == "not_equals":
            lang = facts["language"]
            if lang and lang != val:
                fired, reason = True, "language is '%s', not '%s'" % (lang, val)

        elif field == "year" and op == "outside_run_window":
            y = facts["year"]
            if y is not None and window and (y < window[0] or y > window[1]):
                fired, reason = True, "publication year %d outside window %d-%d" % (
                    y, window[0], window[1])

        if not fired:
            continue
        if outcome == "exclude":
            excludes.append((rid, reason))
        elif outcome == "pass_geography":
            passes.append((rid, reason))

    return excludes, passes


def triage(rec, facts, rules, window, domains):
    """Mechanical partition: 'include', 'exclude' or 'uncertain', with reasons."""
    excludes, geo_passes = apply_mechanical(rec, facts, rules, window)
    flags = ["scholar_only"] if rec.get("needs_manual_metadata") else []
    rules_fired = [r for r, _ in excludes] + [r for r, _ in geo_passes]
    # supporting reasons first, so the decisive one is always last
    reasons = ["%s: %s" % (r, why) for r, why in geo_passes]

    if excludes:
        return ("exclude", rules_fired,
                reasons + ["%s: %s" % (r, why) for r, why in excludes], flags)

    # --- geography ---------------------------------------------------------
    if not facts["sg_affiliation"]:
        if facts["singapore_in_text"]:
            return ("uncertain", rules_fired,
                    reasons + ["No Singapore author affiliation, but Singapore appears in "
                               "the text — decide between INC-GEO-02 (Singapore setting) "
                               "and EXC-GEO-01 (mentioned only in passing)"], flags)
        if not rec.get("authors"):
            return ("uncertain", rules_fired,
                    reasons + ["No author affiliations available (Scholar-only record) — "
                               "geography cannot be assessed mechanically"],
                    flags + ["scholar_only"])
        return ("exclude", rules_fired,
                reasons + ["EXC-GEO-01: no Singapore affiliation and no mention of "
                           "Singapore in title, abstract, keywords or MeSH"], flags)

    if facts["sg_sectors"] and set(facts["sg_sectors"]) <= {"industry"}:
        return ("uncertain", rules_fired, reasons + [INDUSTRY_ONLY_NOTE],
                flags + ["industry_regional_office"])

    if facts["n_countries"] > 3 and not facts["sg_leading"]:
        flags.append("regional_participation")

    # --- type --------------------------------------------------------------
    types = set(facts["article_types"])
    if "Case Reports" in types:
        return ("uncertain", rules_fired,
                reasons + ["EXC-TYP-02: case report — exclude if a single patient, "
                           "include if a series of 5 or more"], flags)
    if "Letter" in types:
        return ("uncertain", rules_fired,
                reasons + ["EXC-TYP-01 note: letters are not auto-excluded — include "
                           "only if it carries original data"], flags)

    # --- topic -------------------------------------------------------------
    if not facts["has_abstract"]:
        return ("uncertain", rules_fired,
                reasons + ["EXC-GEN-03: no abstract — fetch full text before deciding"], flags)

    scores = idlib.score_domains(rec, domains)
    hits = idlib.assigned_domains(scores)
    if not hits:
        return ("uncertain", rules_fired,
                reasons + ["Passes geography but matches no domain above threshold — "
                           "decide whether this is infectious disease research at all "
                           "(INC-TOP-01/02), and tag other_id if it is"], flags)

    return ("include", rules_fired,
            reasons + ["Domain evidence: %s" % ", ".join(hits)], flags)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def write_report(path, buckets, decisions, uncertain_reasons, window):
    L = ["# Screening report", ""]
    L.append("Window: **%s-%s**" % window if window else "Window: (none)")
    L.append("")
    L.append("| Bucket | Count |")
    L.append("|---|---|")
    for k in ("include", "exclude", "uncertain"):
        L.append("| %s | %d |" % (k, len(buckets[k])))
    L.append("| **total** | **%d** |" % sum(len(v) for v in buckets.values()))
    L.append("")
    if decisions:
        by = Counter((d.get("decided_by") or "agent") for d in decisions.values())
        L.append("Agent/user decisions applied: %d (%s)" %
                 (len(decisions), ", ".join("%s=%d" % kv for kv in sorted(by.items()))))
        L.append("")
    L.append("## Why records are uncertain")
    L.append("")
    L.append("| Reason | Count |")
    L.append("|---|---|")
    for reason, n in uncertain_reasons.most_common():
        L.append("| %s | %d |" % (reason.replace("|", "\\|")[:110], n))
    L.append("")
    L.append("## Next step")
    L.append("")
    L.append("Read `screening/uncertain.jsonl`. For each record: judge against")
    L.append("`reference/screening-criteria.md`; if unsure, fetch full text; if still")
    L.append("unsure, ask the user. Append every decision to")
    L.append("`screening/decisions.jsonl`, amend the criteria file when the user rules,")
    L.append("then re-run this script.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--from-year", type=int)
    ap.add_argument("--to-year", type=int)
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    records = idlib.read_jsonl(p["records"])
    if not records:
        raise SystemExit("No records at %s -- run ingest.py first." % p["records"])

    plan = idlib.read_json(p["queries"], {}) or {}
    from_year = args.from_year or plan.get("from_year")
    to_year = args.to_year or plan.get("to_year")
    window = (int(from_year), int(to_year)) if from_year and to_year else None
    if window is None:
        idlib.eprint("WARNING: no date window (no queries.json and no --from-year/--to-year); "
                     "EXC-TYP-04 will not be applied.")

    rules = idlib.load_mechanical_rules()
    domains = idlib.load_taxonomy()
    resolver = idlib.AffiliationResolver()

    decisions_path = os.path.join(p["screening"], "decisions.jsonl")
    decisions = {}
    for d in idlib.read_jsonl(decisions_path):
        if d.get("uid"):
            decisions[d["uid"]] = d

    buckets = {"include": [], "exclude": [], "uncertain": []}
    uncertain_reasons = Counter()
    unknown_decisions = []

    known_uids = {r["uid"] for r in records}
    for uid in decisions:
        if uid not in known_uids:
            unknown_decisions.append(uid)

    for rec in records:
        facts = derive(rec, resolver)
        decision, rules_fired, reasons, flags = triage(rec, facts, rules, window, domains)
        source = "mechanical"

        override = decisions.get(rec["uid"])
        if override and override.get("decision") in ("include", "exclude"):
            decision = override["decision"]
            source = override.get("decided_by") or "agent"
            reasons = ["%s: %s" % (override.get("rule_id", "(no rule id)"),
                                   override.get("reason", "(no reason given)"))]
            if override.get("evidence"):
                reasons.append("evidence: %s" % override["evidence"])
            flags = sorted(set(flags + list(override.get("flags") or [])))
            rules_fired = [override.get("rule_id")] if override.get("rule_id") else rules_fired

        rec["screening"] = {
            "decision": decision,
            "primary_reason": reasons[-1] if reasons else "",
            "decided_by": source,
            "rules_fired": rules_fired,
            "reasons": reasons,
            "flags": flags,
        }
        rec["facts"] = facts
        buckets[decision].append(rec)
        if decision == "uncertain":
            for r in reasons:
                if not r.startswith("INC-GEO-01"):
                    uncertain_reasons[r] += 1

    idlib.ensure_dirs(p["screening"])
    idlib.write_jsonl(os.path.join(p["screening"], "auto_include.jsonl"),
                      [r for r in buckets["include"] if r["screening"]["decided_by"] == "mechanical"])
    idlib.write_jsonl(os.path.join(p["screening"], "auto_exclude.jsonl"),
                      [r for r in buckets["exclude"] if r["screening"]["decided_by"] == "mechanical"])
    idlib.write_jsonl(os.path.join(p["screening"], "uncertain.jsonl"), buckets["uncertain"])
    idlib.write_jsonl(os.path.join(p["screening"], "included.jsonl"), buckets["include"])
    idlib.write_jsonl(os.path.join(p["screening"], "excluded.jsonl"), buckets["exclude"])
    write_report(os.path.join(p["screening"], "screening_report.md"),
                 buckets, decisions, uncertain_reasons, window)

    print("Screening complete (window %s)" % ("%d-%d" % window if window else "none"))
    print("  include    %4d" % len(buckets["include"]))
    print("  exclude    %4d" % len(buckets["exclude"]))
    print("  uncertain  %4d   <- needs your judgement" % len(buckets["uncertain"]))
    if decisions:
        print("  (%d prior decision(s) applied from decisions.jsonl)" % len(decisions))
    if unknown_decisions:
        print("")
        print("WARNING: %d decision(s) reference uids not in records.jsonl:" % len(unknown_decisions))
        for uid in unknown_decisions[:5]:
            print("  - %s" % uid)
    if buckets["uncertain"]:
        print("")
        print("Top reasons for uncertainty:")
        for reason, n in uncertain_reasons.most_common(6):
            print("  %3d  %s" % (n, reason[:96]))
        print("")
        print("Read %s next." % os.path.join(p["screening"], "uncertain.jsonl"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
