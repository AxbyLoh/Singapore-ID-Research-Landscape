#!/usr/bin/env python3
"""Generate the search plan (queries.json) for a run.

Reads reference/search-strategy.md, reference/domain-taxonomy.md and
data/directory_of_experts.csv. Emits <run-dir>/queries.json plus a
human-readable <run-dir>/queries.md.

The agent executes these queries with the PubMed connector and web search;
this script has no network access of its own.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

STRATEGY_PATH = os.path.join(idlib.REFERENCE_DIR, "search-strategy.md")


def load_blocks():
    blocks = {}
    with open(STRATEGY_PATH, encoding="utf-8") as fh:
        text = fh.read()
    for raw in re.findall(r"```json\s*\n(.*?)\n```", text, re.S):
        try:
            b = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit("Malformed json block in search-strategy.md: %s" % exc)
        if "block_id" in b:
            blocks[b["block_id"]] = b
    for required in ("singapore_filter", "id_hedge", "build_options"):
        if required not in blocks:
            raise SystemExit("search-strategy.md is missing the '%s' json block" % required)
    return blocks


def or_join(clauses):
    return " OR ".join(clauses)


def quote_term(term):
    """Render a taxonomy term as a PubMed Title/Abstract clause."""
    t = term.strip()
    if t.endswith("*"):
        return "%s[Title/Abstract]" % t          # PubMed truncation, unquoted
    return '"%s"[Title/Abstract]' % t


def mesh_clause(term):
    return '"%s"[MeSH Terms]' % term


def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def build_geography(domains, blocks, opts):
    sg = "(%s)" % or_join(blocks["singapore_filter"]["clauses"])
    floor = opts["term_weight_floor"]
    cap = opts["max_terms_per_query"]
    out = []

    for d in domains:
        clauses = [quote_term(t) for t, w in sorted(d["terms"].items()) if w >= floor]
        clauses += [mesh_clause(m) for m in sorted(d["mesh_terms"])]
        # dedupe, preserve order
        clauses = list(dict.fromkeys(clauses))
        parts = chunk(clauses, cap)
        for i, part in enumerate(parts, 1):
            qid = "geo_%s_%d" % (d["domain_id"], i) if len(parts) > 1 else "geo_%s" % d["domain_id"]
            out.append({
                "query_id": qid,
                "family": "geography",
                "engine": "pubmed",
                "domain": d["domain_id"],
                "query": "(%s) AND %s" % (or_join(part), sg),
                "term_count": len(part),
                "max_results": opts["max_results_per_query"],
                "page_size": opts["page_size"],
            })

    hedge = blocks["id_hedge"]["clauses"]
    for i, part in enumerate(chunk(hedge, cap), 1):
        qid = "geo_all_id_%d" % i if len(hedge) > cap else "geo_all_id"
        out.append({
            "query_id": qid,
            "family": "geography",
            "engine": "pubmed",
            "domain": "other_id",
            "query": "(%s) AND %s" % (or_join(part), sg),
            "term_count": len(part),
            "max_results": opts["max_results_per_query"],
            "page_size": opts["page_size"],
            "notes": "Catch-all hedge: finds Singapore ID work outside the five domains.",
        })
    return out


def build_experts(experts, blocks, opts):
    sg = "(%s)" % or_join(blocks["singapore_filter"]["clauses"])
    out = []
    skipped = []
    for e in experts:
        if (e.get("active") or "yes").strip().lower() in ("no", "false", "0"):
            continue
        override = (e.get("pubmed_author_query") or "").strip()
        if override:
            query = override
            basis = "pubmed_author_query override"
        else:
            variants = [v.strip() for v in (e.get("name_variants") or "").split("|") if v.strip()]
            if not variants:
                skipped.append(e.get("full_name") or e.get("expert_id"))
                continue
            authors = or_join('"%s"[Author]' % v for v in variants)
            query = "(%s) AND %s" % (authors, sg)
            basis = "name_variants (%d)" % len(variants)
        out.append({
            "query_id": "exp_%s" % (e.get("expert_id") or idlib.norm_title(e.get("full_name"))[:40].replace(" ", "-")),
            "family": "experts",
            "engine": "pubmed",
            "expert_id": e.get("expert_id", ""),
            "expert_name": e.get("full_name", ""),
            "expert_institution": e.get("institution", ""),
            "query": query,
            "basis": basis,
            "max_results": opts["max_results_per_query"],
            "page_size": opts["page_size"],
        })
    return out, skipped


def build_scholar(domains, experts):
    out = [{
        "query_id": "sch_all_id",
        "family": "scholar",
        "engine": "web_search",
        "domain": "other_id",
        "query": "Singapore infectious disease epidemiology research",
        "site": "scholar.google.com",
    }]
    seeds = {
        "vector_borne": "Singapore dengue Aedes vector-borne transmission",
        "sti": "Singapore HIV sexually transmitted infection epidemiology",
        "tb": "Singapore tuberculosis screening treatment",
        "rti": "Singapore influenza COVID-19 respiratory infection",
        "amr_hai": "Singapore antimicrobial resistance healthcare-associated infection",
    }
    for d in domains:
        out.append({
            "query_id": "sch_%s" % d["domain_id"],
            "family": "scholar",
            "engine": "web_search",
            "domain": d["domain_id"],
            "query": seeds.get(d["domain_id"], "Singapore %s research" % d["label"]),
            "site": "scholar.google.com",
        })
    for e in experts:
        if (e.get("active") or "yes").strip().lower() in ("no", "false", "0"):
            continue
        name = (e.get("full_name") or "").strip()
        if not name:
            continue
        out.append({
            "query_id": "sch_exp_%s" % e.get("expert_id", idlib.norm_title(name).replace(" ", "-")),
            "family": "scholar",
            "engine": "web_search",
            "expert_id": e.get("expert_id", ""),
            "query": "%s Singapore infectious disease" % name,
            "site": "scholar.google.com",
        })
    return out


def write_markdown(path, plan):
    lines = ["# Search plan — %s" % plan["generated_at"][:10], ""]
    lines.append("Window: **%s to %s** (`datetype: %s`)" %
                 (plan["date_from"], plan["date_to"], plan["datetype"]))
    lines.append("")
    lines.append("Run every query below, page until `has_more` is false or the cap is hit,")
    lines.append("then save each `get_article_metadata` response verbatim to")
    lines.append("`raw/pubmed_<query_id>_<n>.json`.")
    lines.append("")
    for family in ("geography", "experts", "scholar"):
        qs = [q for q in plan["queries"] if q["family"] == family]
        if not qs:
            continue
        lines.append("## %s (%d queries)" % (family, len(qs)))
        lines.append("")
        for q in qs:
            lines.append("### `%s`" % q["query_id"])
            for k in ("domain", "expert_name", "basis", "site", "notes"):
                if q.get(k):
                    lines.append("- **%s:** %s" % (k, q[k]))
            lines.append("")
            lines.append("```")
            lines.append(q["query"])
            lines.append("```")
            lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--from-year", type=int, default=2015)
    ap.add_argument("--to-year", type=int, default=dt.date.today().year)
    ap.add_argument("--datetype", default="pdat", choices=["pdat", "edat", "mdat"])
    ap.add_argument("--medline-only", action="store_true",
                    help="append the medline[sb] subset filter to PubMed queries")
    ap.add_argument("--families", nargs="*", default=["geography", "experts", "scholar"])
    args = ap.parse_args()

    blocks = load_blocks()
    opts = blocks["build_options"]
    domains = idlib.load_taxonomy()
    experts = idlib.load_experts()

    queries = []
    skipped_experts = []
    if "geography" in args.families:
        queries += build_geography(domains, blocks, opts)
    if "experts" in args.families:
        eq, skipped_experts = build_experts(experts, blocks, opts)
        queries += eq
    if "scholar" in args.families:
        queries += build_scholar(domains, experts)

    if args.medline_only:
        suffix = opts.get("medline_only_suffix", " AND medline[sb]")
        for q in queries:
            if q["engine"] == "pubmed":
                q["query"] += suffix

    plan = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "from_year": args.from_year,
        "to_year": args.to_year,
        "date_from": str(args.from_year),
        "date_to": str(args.to_year),
        "datetype": args.datetype,
        "medline_only": args.medline_only,
        "domains": [d["domain_id"] for d in domains],
        "expert_count": len(experts),
        "queries": queries,
    }

    p = idlib.run_paths(args.run_dir)
    idlib.ensure_dirs(p["root"], p["raw"])
    idlib.write_json(p["queries"], plan)
    write_markdown(os.path.join(args.run_dir, "queries.md"), plan)

    by_family = {}
    for q in queries:
        by_family[q["family"]] = by_family.get(q["family"], 0) + 1
    print("Search plan written to %s" % p["queries"])
    print("Window: %s-%s (datetype=%s)%s" % (
        args.from_year, args.to_year, args.datetype,
        " [MEDLINE subset only]" if args.medline_only else ""))
    for fam in ("geography", "experts", "scholar"):
        if fam in by_family:
            print("  %-10s %3d queries" % (fam, by_family[fam]))
    print("  %-10s %3d total" % ("TOTAL", len(queries)))

    if not experts:
        print("")
        print("NOTE: the expert roster is empty, so no expert queries were built.")
        print("      Run fetch_experts.py or populate data/directory_of_experts.csv.")
    if skipped_experts:
        print("")
        print("SKIPPED %d expert(s) with no name_variants and no pubmed_author_query:"
              % len(skipped_experts))
        for n in skipped_experts[:10]:
            print("  - %s" % n)
    print("")
    print("Human-readable version: %s" % os.path.join(args.run_dir, "queries.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
