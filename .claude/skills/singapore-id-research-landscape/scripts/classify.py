#!/usr/bin/env python3
"""Assign domains, sub-domains, research types and affiliations for every
included record.

Reads screening/included.jsonl, writes:

  classification/classified.jsonl        records + all classification + resolved authors
  classification/unassigned.jsonl        included records matching no domain
  classification/subdomain_vocabulary.csv     the MeSH terms chosen as this run's
                                          sub-domains, one row per (domain, term)
  classification/unassigned_subdomain.jsonl   records with no sub-domain match (per domain)
  classification/unassigned_research_type.jsonl  records matching no research type
  classification/unmapped_affiliations.csv   affiliation strings needing an alias
  classification/classification_report.md

Domain and research-type classification are curated term lists, read at
runtime, no code change needed to retune:

  reference/domain-taxonomy.md         the 5 domains (all records)
  reference/research-type-taxonomy.md  cross-cutting "what kind of research"
                                        tags (multi-label, e.g. Genomics +
                                        Surveillance and epidemiology)

**Sub-domains are not curated.** They are derived from the corpus itself: for
each domain, this script counts how often each MeSH heading appears across
that domain's own included records (after excluding generic/demographic MeSH
noise via data/mesh_stoplist.csv -- infrastructure, not domain content), keeps
the most frequent headings that clear --subdomain-min-records, and assigns
each record's primary_subdomain to its own highest-ranked matching heading.
The "Sub-domains of X" donut chart is therefore built entirely from what this
run's publications actually say they are about, in the corpus's own MeSH
vocabulary -- nothing here is invented in advance. Display labels for the
chosen MeSH headings can still be hand-edited afterwards in
subdomain_vocabulary.csv (e.g. renaming "Tuberculosis, Multidrug-Resistant" to
"Multidrug-resistant TB"); re-running this script preserves those edits for
any heading that still qualifies.

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
UNSPECIFIED = "Other/unspecified"


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


def build_mesh_vocabulary(records, stoplist, top_k, min_records):
    """For each domain, rank its own records' MeSH headings by frequency and
    keep the top ones that clear min_records.

    Returns {domain_id: OrderedDict(mesh_term -> rank)} (rank 1 = most
    frequent) and {domain_id: [{'mesh_term','frequency','rank'}, ...]} for
    reporting/output. Excludes anything in `stoplist` (case-insensitive) and
    counts each domain's own records only -- a term popular in one domain but
    absent from another simply won't appear in the other's vocabulary.
    """
    by_domain = OrderedDict()
    for rec in records:
        by_domain.setdefault(rec["primary_domain"], []).append(rec)

    vocab_rank = {}
    vocab_rows = {}
    for dom, recs in by_domain.items():
        freq = Counter()
        casing = {}
        for rec in recs:
            seen_this_record = set()
            for term in rec.get("mesh_terms") or []:
                key = (term or "").strip()
                if not key:
                    continue
                lower = key.lower()
                if lower in stoplist or lower in seen_this_record:
                    continue
                seen_this_record.add(lower)
                freq[lower] += 1
                casing.setdefault(lower, key)

        qualifying = [(lower, n) for lower, n in freq.items() if n >= min_records]
        qualifying.sort(key=lambda kv: (-kv[1], casing[kv[0]]))
        top = qualifying[:top_k]

        rank_map = OrderedDict()
        rows = []
        for i, (lower, n) in enumerate(top, 1):
            term = casing[lower]
            rank_map[term] = i
            rows.append({"mesh_term": term, "rank": i, "frequency": n,
                        "n_records_in_domain": len(recs),
                        "share_pct": round(100.0 * n / len(recs), 1) if recs else 0.0})
        vocab_rank[dom] = rank_map
        vocab_rows[dom] = rows

    return vocab_rank, vocab_rows


def assign_subdomain(rec, vocab_rank, label_overrides):
    """Match rec's own MeSH terms against its domain's vocabulary.

    primary_subdomain (display label) drives the donut chart, one mutually
    exclusive slice per record. subdomains/subdomain_labels keep the full
    multi-label view. A record whose MeSH terms don't intersect the domain's
    vocabulary -- because the domain had too few records to build one, or
    because this record's own terms simply aren't common in its domain --
    gets UNSPECIFIED, which is a legitimate, informative outcome here, not a
    taxonomy gap to fill in by hand.
    """
    rank_map = vocab_rank.get(rec["primary_domain"]) or {}
    if not rank_map:
        rec["subdomains"] = []
        rec["subdomain_labels"] = []
        rec["subdomain_ranks"] = []
        rec["primary_subdomain"] = UNSPECIFIED
        rec["primary_subdomain_mesh"] = ""
        return

    own_terms = {(t or "").strip().lower(): (t or "").strip()
                for t in (rec.get("mesh_terms") or [])}
    matches = []
    for vocab_term, rank in rank_map.items():
        if vocab_term.lower() in own_terms:
            matches.append((rank, vocab_term))
    matches.sort()

    rec["subdomains"] = [t for _, t in matches]
    rec["subdomain_labels"] = [label_overrides.get((rec["primary_domain"], t), t) for _, t in matches]
    rec["subdomain_ranks"] = [r for r, _ in matches]
    if matches:
        top_term = matches[0][1]
        rec["primary_subdomain"] = label_overrides.get((rec["primary_domain"], top_term), top_term)
        rec["primary_subdomain_mesh"] = top_term
    else:
        rec["primary_subdomain"] = UNSPECIFIED
        rec["primary_subdomain_mesh"] = ""


def classify_research_types(rec, type_blocks):
    """Cross-cutting, multi-label 'what kind of research' tags. No primary."""
    scores = idlib.score_taxa(rec, type_blocks, id_field="type_id")
    assigned = idlib.assigned_taxa(scores)
    label_by_id = {b["type_id"]: b.get("label", b["type_id"]) for b in type_blocks}
    rec["research_type_scores"] = {k: v["score"] for k, v in scores.items()}
    rec["research_types"] = assigned
    rec["research_type_labels"] = [label_by_id.get(t, t) for t in assigned]


def classify_record(rec, domains, type_blocks, resolver):
    """Domain, research-type and affiliation classification. Sub-domain is
    NOT done here -- it needs corpus-wide MeSH frequency across every
    record's primary_domain, computed once after this pass (see main())."""
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
    L.append("`(domain, primary_subdomain)` pair, summing to that domain's total. Sub-domains")
    L.append("are **derived from this run's own MeSH-term frequency** (see")
    L.append("`subdomain_vocabulary.csv`), not a predefined list.")
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
        L.append("`%s` records: **%d**. This means either the domain had too few "
                 "records to clear `--subdomain-min-records`, or this particular "
                 "record's own MeSH terms simply aren't common in its domain -- "
                 "not a taxonomy gap to fill in by hand. If a whole domain is "
                 "mostly unspecified, lower `--subdomain-min-records` and re-run; "
                 "if only scattered records are, that's expected." % (UNSPECIFIED, len(unassigned_subdomain)))
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


def load_label_overrides(vocab_csv_path):
    """Hand-edited display labels from a previous run's subdomain_vocabulary.csv.

    Only picks up rows where display_label was actually changed from
    mesh_term -- an untouched row's display_label equals mesh_term and is not
    treated as an override, so it doesn't block re-derivation.
    """
    overrides = {}
    for row in idlib.read_csv(vocab_csv_path):
        dom, term, label = row.get("domain_id", ""), row.get("mesh_term", ""), row.get("display_label", "")
        if dom and term and label and label != term:
            overrides[(dom, term)] = label
    return overrides


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--input", help="override input (default screening/included.jsonl)")
    ap.add_argument("--subdomain-top-k", type=int, default=12,
                    help="max sub-domains kept per domain, by MeSH-term frequency")
    ap.add_argument("--subdomain-min-records", type=int, default=3,
                    help="a MeSH term must appear on at least this many of a domain's "
                         "own records to qualify as a sub-domain")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    src = args.input or os.path.join(p["screening"], "included.jsonl")
    records = idlib.read_jsonl(src)
    if not records:
        raise SystemExit("No included records at %s -- run screen.py first." % src)

    domains = idlib.load_taxonomy()
    type_blocks = idlib.load_research_type_taxonomy()
    stoplist = idlib.load_mesh_stoplist()
    resolver = idlib.AffiliationResolver()

    vocab_csv_path = os.path.join(p["classification"], "subdomain_vocabulary.csv")
    label_overrides = load_label_overrides(vocab_csv_path)

    domain_counts = Counter()
    subdomain_counts = Counter()
    type_counts = Counter()
    unassigned = []
    unassigned_type = []
    multi = 0
    no_aff = 0

    # Pass 1: domain, research type, affiliations. Sub-domain needs the
    # corpus-wide MeSH frequency this pass produces, so it comes after.
    for rec in records:
        classify_record(rec, domains, type_blocks, resolver)
        for d in rec["domains"]:
            domain_counts[d] += 1
        if rec["domains"] == [OTHER]:
            unassigned.append(rec)
        if rec["is_multi_domain"]:
            multi += 1
        if not rec["institutions"] and not rec["countries"]:
            no_aff += 1
        for t in rec["research_type_labels"]:
            type_counts[t] += 1
        if not rec["research_types"]:
            unassigned_type.append(rec)

    vocab_rank, vocab_rows = build_mesh_vocabulary(
        records, stoplist, args.subdomain_top_k, args.subdomain_min_records)

    unassigned_subdomain = []
    for rec in records:
        assign_subdomain(rec, vocab_rank, label_overrides)
        subdomain_counts[(rec["primary_domain"], rec["primary_subdomain"])] += 1
        if rec["primary_subdomain"] == UNSPECIFIED:
            unassigned_subdomain.append(rec)

    domain_labels = {d["domain_id"]: d.get("label", d["domain_id"]) for d in domains}
    vocab_out_rows = []
    for dom, rows in vocab_rows.items():
        for r in rows:
            vocab_out_rows.append({
                "domain_id": dom, "domain_label": domain_labels.get(dom, dom),
                "mesh_term": r["mesh_term"],
                "display_label": label_overrides.get((dom, r["mesh_term"]), r["mesh_term"]),
                "rank": r["rank"], "frequency": r["frequency"],
                "n_records_in_domain": r["n_records_in_domain"], "share_pct": r["share_pct"],
            })

    idlib.ensure_dirs(p["classification"])
    idlib.write_jsonl(os.path.join(p["classification"], "classified.jsonl"), records)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned.jsonl"), unassigned)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned_subdomain.jsonl"), unassigned_subdomain)
    idlib.write_jsonl(os.path.join(p["classification"], "unassigned_research_type.jsonl"), unassigned_type)
    idlib.write_csv(vocab_csv_path, vocab_out_rows,
                    ["domain_id", "domain_label", "mesh_term", "display_label", "rank",
                     "frequency", "n_records_in_domain", "share_pct"])

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
    print("Sub-domains (derived from MeSH frequency, top-k=%d, min-records=%d):"
          % (args.subdomain_top_k, args.subdomain_min_records))
    for dom in domain_counts:
        n_terms = len(vocab_rank.get(dom, {}))
        if n_terms:
            print("  %-14s %2d sub-domain(s) found" % (dom, n_terms))
        else:
            print("  %-14s no sub-domains cleared the threshold -- try a lower "
                  "--subdomain-min-records for this domain" % dom)
    print("  %d/%d records are %s" % (len(unassigned_subdomain), len(records), UNSPECIFIED))
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
    print("  -> %s (edit display_label and re-run to rename slices)" % vocab_csv_path)
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
