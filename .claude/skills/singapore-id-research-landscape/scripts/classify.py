#!/usr/bin/env python3
"""Assign domains and resolve affiliations for every included record.

Reads screening/included.jsonl, writes:

  classification/classified.jsonl        records + domains + resolved authors
  classification/unassigned.jsonl        included records matching no domain
  classification/unmapped_affiliations.csv   affiliation strings needing an alias
  classification/classification_report.md

Domains come from reference/domain-taxonomy.md; institution and country come
from data/institution_aliases.csv and data/country_aliases.csv. Editing those
files and re-running is the whole tuning loop -- no code changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

OTHER = "other_id"


def resolve_authors(rec, resolver):
    """Attach resolved institution/country to each author."""
    out = []
    n = len(rec.get("authors") or [])
    for a in rec.get("authors") or []:
        affs = []
        for seg in a.get("affiliations") or []:
            affs.append(resolver.resolve(seg))
        pos = a.get("position") or 0
        out.append({
            "author_key": idlib.author_key(a),
            "author_name": idlib.author_display(a),
            "last_name": a.get("last_name", ""),
            "fore_name": a.get("fore_name", ""),
            "initials": a.get("initials", ""),
            "position": pos,
            "is_first": pos == 1,
            "is_last": pos == n and n > 1,
            "affiliations": affs,
            "institutions": sorted({x["institution"] for x in affs if x["institution"]}),
            "countries": sorted({x["country"] for x in affs if x["country"]}),
            "sectors": sorted({x["sector"] for x in affs if x["sector"]}),
        })
    return out


def classify_record(rec, domains, resolver):
    scores = idlib.score_domains(rec, domains)
    assigned = idlib.assigned_domains(scores)

    # An agent/user decision may have named a domain explicitly.
    forced = [d for d in (rec.get("screening", {}).get("domains") or []) if d]
    for d in forced:
        if d not in assigned:
            assigned.append(d)

    rec["domain_scores"] = {k: v["score"] for k, v in scores.items()}
    rec["domain_matches"] = {k: v["matched"][:12] for k, v in scores.items() if v["score"]}
    rec["domains"] = assigned or [OTHER]
    rec["primary_domain"] = rec["domains"][0]
    rec["is_multi_domain"] = len(assigned) > 1

    authors = resolve_authors(rec, resolver)
    rec["authors_resolved"] = authors
    rec["institutions"] = sorted({i for a in authors for i in a["institutions"]})
    rec["countries"] = sorted({c for a in authors for c in a["countries"]})
    rec["sg_institutions"] = sorted({
        x["institution"] for a in authors for x in a["affiliations"]
        if x["country"] == "Singapore" and x["institution"]})
    rec["is_international"] = len(rec["countries"]) > 1
    rec["n_countries"] = len(rec["countries"])
    rec["n_institutions"] = len(rec["institutions"])

    first = next((a for a in authors if a["is_first"]), None)
    last = next((a for a in authors if a["is_last"]), None)
    rec["first_author"] = first["author_name"] if first else ""
    rec["last_author"] = last["author_name"] if last else ""
    rec["first_author_country"] = (first["countries"][0] if first and first["countries"] else "")
    rec["last_author_country"] = (last["countries"][0] if last and last["countries"] else "")
    rec["singapore_led"] = bool(
        (first and "Singapore" in first["countries"]) or
        (last and "Singapore" in last["countries"]))
    return rec


def write_report(path, records, unassigned, domain_counts, unmapped_inst,
                 unmapped_ctry, multi, no_aff):
    L = ["# Classification report", ""]
    L.append("Included records classified: **%d**" % len(records))
    L.append("")
    L.append("## Domain distribution")
    L.append("")
    L.append("| Domain | Records | Share |")
    L.append("|---|---|---|")
    total = len(records) or 1
    for dom, n in domain_counts.most_common():
        L.append("| %s | %d | %.0f%% |" % (dom, n, 100.0 * n / total))
    L.append("")
    L.append("Domains overlap by design, so shares sum above 100%%. "
             "%d record(s) carry more than one domain." % multi)
    L.append("")
    if unassigned:
        L.append("## Unassigned (`other_id`) — %d record(s)" % len(unassigned))
        L.append("")
        L.append("Read these. Either assign a domain, keep `other_id`, or add the missing")
        L.append("term to `reference/domain-taxonomy.md` (preferred, when it generalises).")
        L.append("")
        for r in unassigned[:40]:
            L.append("- **%s** (%s) — `%s`" % (r["title"][:100], r.get("year", "?"), r["uid"]))
        if len(unassigned) > 40:
            L.append("- … and %d more, see `unassigned.jsonl`" % (len(unassigned) - 40))
        L.append("")
    if no_aff:
        L.append("## Records with no resolvable affiliation — %d" % no_aff)
        L.append("")
        L.append("These contribute to counts but not to the institution or country networks.")
        L.append("")
    L.append("## Affiliation resolution")
    L.append("")
    L.append("| | Distinct strings unresolved |")
    L.append("|---|---|")
    L.append("| Institution | %d |" % len(unmapped_inst))
    L.append("| Country | %d |" % len(unmapped_ctry))
    L.append("")
    L.append("Add the frequent ones to `data/institution_aliases.csv` /")
    L.append("`data/country_aliases.csv` and re-run. An unmapped institution is a")
    L.append("missing node in the co-authorship network.")
    L.append("")
    L.append("Full list, ordered by frequency: `unmapped_affiliations.csv`")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--input", help="override input (default screening/included.jsonl)")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    src = args.input or os.path.join(p["screening"], "included.jsonl")
    records = idlib.read_jsonl(src)
    if not records:
        raise SystemExit("No included records at %s -- run screen.py first." % src)

    domains = idlib.load_taxonomy()
    resolver = idlib.AffiliationResolver()

    domain_counts = Counter()
    unassigned = []
    multi = 0
    no_aff = 0

    for rec in records:
        classify_record(rec, domains, resolver)
        for d in rec["domains"]:
            domain_counts[d] += 1
        if rec["domains"] == [OTHER]:
            unassigned.append(rec)
        if rec["is_multi_domain"]:
            multi += 1
        if not rec["institutions"] and not rec["countries"]:
            no_aff += 1

    idlib.ensure_dirs(p["classification"])
    idlib.write_jsonl(os.path.join(p["classification"], "classified.jsonl"), records)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned.jsonl"), unassigned)

    rows = []
    for seg, n in sorted(resolver.unmapped_institution.items(), key=lambda kv: -kv[1]):
        rows.append({"affiliation_string": seg, "occurrences": n,
                     "missing": "institution", "suggested_pattern": suggest(seg)})
    for seg, n in sorted(resolver.unmapped_country.items(), key=lambda kv: -kv[1]):
        rows.append({"affiliation_string": seg, "occurrences": n,
                     "missing": "country", "suggested_pattern": ""})
    idlib.write_csv(os.path.join(p["classification"], "unmapped_affiliations.csv"), rows,
                    ["affiliation_string", "occurrences", "missing", "suggested_pattern"])

    write_report(os.path.join(p["classification"], "classification_report.md"),
                 records, unassigned, domain_counts,
                 resolver.unmapped_institution, resolver.unmapped_country, multi, no_aff)

    print("Classification complete: %d records" % len(records))
    for dom, n in domain_counts.most_common():
        print("  %-14s %4d" % (dom, n))
    print("  (%d multi-domain, %d unassigned -> other_id)" % (multi, len(unassigned)))
    print("")
    print("Unresolved affiliation strings: %d institution, %d country"
          % (len(resolver.unmapped_institution), len(resolver.unmapped_country)))
    if resolver.unmapped_institution:
        print("Most frequent unresolved institutions:")
        for seg, n in sorted(resolver.unmapped_institution.items(), key=lambda kv: -kv[1])[:5]:
            print("  %3dx  %s" % (n, seg[:88]))
    print("")
    print("  -> %s" % os.path.join(p["classification"], "classified.jsonl"))
    print("  -> %s" % os.path.join(p["classification"], "classification_report.md"))
    return 0


def suggest(segment):
    """A plausible alias pattern: the longest comma-part that looks like a body."""
    keywords = ("universit", "hospital", "institute", "school", "centre", "center",
                "college", "agency", "laborator", "ministry", "academy", "department of health")
    best = ""
    for part in segment.split(","):
        p = part.strip().lower()
        if any(k in p for k in keywords) and len(p) > len(best):
            best = p
    return best


if __name__ == "__main__":
    sys.exit(main())
