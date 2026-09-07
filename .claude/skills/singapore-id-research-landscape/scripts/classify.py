#!/usr/bin/env python3
"""Assign domains, sub-domains, research types and affiliations for every
included record.

Reads screening/included.jsonl, writes:

  classification/classified.jsonl        records + all classification + resolved authors
  classification/unassigned.jsonl        included records matching no domain
  classification/unassigned_subdomain.jsonl   records with no sub-domain match (per domain)
  classification/unassigned_research_type.jsonl  records matching no research type
  classification/unmapped_affiliations.csv   affiliation strings needing an alias
  classification/classification_report.md

Three taxonomies drive this, all human-maintained and read at runtime -- no
code change needed to retune:

  reference/domain-taxonomy.md         the 5 domains (all records)
  reference/subdomain-taxonomy.md      named sub-domains WITHIN each domain
                                        (e.g. "Dengue virus" within vector_borne)
  reference/research-type-taxonomy.md  cross-cutting "what kind of research"
                                        tags (multi-label, e.g. Genomics +
                                        Surveillance and epidemiology)

Institution and country come from data/institution_aliases.csv and
data/country_aliases.csv.
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


def classify_subdomain(rec, subdomains_by_domain):
    """Sub-domain within rec['primary_domain'], scoped to that domain's blocks.

    primary_subdomain drives the donut chart (mutually exclusive slices);
    subdomains (pipe-joined at dataset build time) keeps the full multi-label
    view for anyone who wants it.
    """
    blocks = subdomains_by_domain.get(rec["primary_domain"]) or []
    if not blocks:
        rec["subdomain_scores"] = {}
        rec["subdomains"] = []
        rec["primary_subdomain"] = "Other/unspecified"
        return

    scores = idlib.score_taxa(rec, blocks, id_field="subdomain_id")
    assigned = idlib.assigned_taxa(scores)
    rec["subdomain_scores"] = {k: v["score"] for k, v in scores.items()}
    rec["subdomains"] = assigned
    label_by_id = {b["subdomain_id"]: b.get("label", b["subdomain_id"]) for b in blocks}
    rec["primary_subdomain"] = label_by_id.get(assigned[0]) if assigned else "Other/unspecified"


def classify_research_types(rec, type_blocks):
    """Cross-cutting, multi-label 'what kind of research' tags. No primary."""
    scores = idlib.score_taxa(rec, type_blocks, id_field="type_id")
    assigned = idlib.assigned_taxa(scores)
    label_by_id = {b["type_id"]: b.get("label", b["type_id"]) for b in type_blocks}
    rec["research_type_scores"] = {k: v["score"] for k, v in scores.items()}
    rec["research_types"] = assigned
    rec["research_type_labels"] = [label_by_id.get(t, t) for t in assigned]


def classify_record(rec, domains, subdomains_by_domain, type_blocks, resolver):
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

    classify_subdomain(rec, subdomains_by_domain)
    classify_research_types(rec, type_blocks)

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
                 unmapped_ctry, multi, no_aff, subdomain_counts, type_counts,
                 unassigned_subdomain, unassigned_type):
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
    L.append("## Sub-domain distribution (`primary_subdomain`, mutually exclusive per domain)")
    L.append("")
    L.append("This is the field for the \"Sub-domains of X\" donut chart -- one slice per")
    L.append("`(domain, primary_subdomain)` pair, summing to that domain's total.")
    L.append("")
    L.append("| Domain | Sub-domain | Records | Share of domain |")
    L.append("|---|---|---|---|")
    domain_totals = Counter()
    for (dom, _sd), n in subdomain_counts.items():
        domain_totals[dom] += n
    for (dom, sd), n in sorted(subdomain_counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        dt = domain_totals[dom] or 1
        L.append("| %s | %s | %d | %.1f%% |" % (dom, sd, n, 100.0 * n / dt))
    L.append("")
    if unassigned_subdomain:
        L.append("`Other/unspecified` records: **%d**. Read "
                 "`unassigned_subdomain.jsonl` -- a recurring theme there is a gap "
                 "in `reference/subdomain-taxonomy.md`, not a data problem. "
                 "`topic_model.py` can help find the missing name." % len(unassigned_subdomain))
        L.append("")
    L.append("## Research-type distribution (multi-label)")
    L.append("")
    L.append("Feeds the \"Types of research\" bar chart. Each publication may carry")
    L.append("several types, so counts sum above the publication total.")
    L.append("")
    L.append("| Research type | Records |")
    L.append("|---|---|")
    for t, n in type_counts.most_common():
        L.append("| %s | %d |" % (t, n))
    L.append("")
    if unassigned_type:
        L.append("**%d** record(s) matched no research type -- read "
                 "`unassigned_research_type.jsonl` and consider adding a term to "
                 "`reference/research-type-taxonomy.md`." % len(unassigned_type))
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
    subdomains_by_domain = idlib.load_subdomain_taxonomy()
    type_blocks = idlib.load_research_type_taxonomy()
    resolver = idlib.AffiliationResolver()

    domain_counts = Counter()
    subdomain_counts = Counter()
    type_counts = Counter()
    unassigned = []
    unassigned_subdomain = []
    unassigned_type = []
    multi = 0
    no_aff = 0

    for rec in records:
        classify_record(rec, domains, subdomains_by_domain, type_blocks, resolver)
        for d in rec["domains"]:
            domain_counts[d] += 1
        if rec["domains"] == [OTHER]:
            unassigned.append(rec)
        if rec["is_multi_domain"]:
            multi += 1
        if not rec["institutions"] and not rec["countries"]:
            no_aff += 1

        subdomain_counts[(rec["primary_domain"], rec["primary_subdomain"])] += 1
        if rec["primary_subdomain"] == "Other/unspecified":
            unassigned_subdomain.append(rec)

        for t in rec["research_type_labels"]:
            type_counts[t] += 1
        if not rec["research_types"]:
            unassigned_type.append(rec)

    idlib.ensure_dirs(p["classification"])
    idlib.write_jsonl(os.path.join(p["classification"], "classified.jsonl"), records)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned.jsonl"), unassigned)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned_subdomain.jsonl"), unassigned_subdomain)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned_research_type.jsonl"), unassigned_type)

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
                 resolver.unmapped_institution, resolver.unmapped_country, multi, no_aff,
                 subdomain_counts, type_counts, unassigned_subdomain, unassigned_type)

    print("Classification complete: %d records" % len(records))
    for dom, n in domain_counts.most_common():
        print("  %-14s %4d" % (dom, n))
    print("  (%d multi-domain, %d unassigned -> other_id)" % (multi, len(unassigned)))
    print("")
    print("Sub-domains: %d Other/unspecified (of %d)" % (len(unassigned_subdomain), len(records)))
    print("Research types: %d record(s) with none assigned" % len(unassigned_type))
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
