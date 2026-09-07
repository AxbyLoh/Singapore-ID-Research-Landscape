#!/usr/bin/env python3
"""Emit the Tableau-ready dataset from classification/classified.jsonl.

Writes <run-dir>/dataset/:

  publications.csv                 fact table, one row per publication
  publication_domains.csv          long: publication x domain
  publication_authors.csv          long: publication x author
  publication_author_affiliations.csv  long: publication x author x affiliation
  publication_institutions.csv     long: publication x institution (deduped)
  publication_countries.csv        long: publication x country (deduped)
  coauthor_institution_edges.csv   institution pairs, per domain, weighted
  coauthor_country_edges.csv       country pairs, per domain, weighted
  coauthor_author_edges.csv        author pairs, weighted
  network_institution_nodes.csv    node table with x/y for a network view
  network_institution_paths.csv    edge table in Tableau path form
  network_country_nodes.csv        "
  network_country_paths.csv        "
  summary_by_domain_year.csv       convenience aggregate
  README.md                        what each file is and how to join them

Every table keys on `uid`. See reference/dataset-schema.md for column meanings
and the Tableau field/mark setup for each chart type.
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402


def pipe(values):
    return "|".join(str(v) for v in values if v not in (None, ""))


def pub_date(rec):
    y, m, d = rec.get("year") or "", rec.get("month") or "", rec.get("day") or ""
    if not y:
        return ""
    return "%s-%s-%s" % (y, (m or "01").zfill(2), (d or "01").zfill(2))


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def build_publications(records, domain_labels, topics):
    rows = []
    for r in records:
        t = topics.get(r["uid"], {})
        scr = r.get("screening", {})
        rows.append({
            "uid": r["uid"],
            "pmid": r.get("pmid", ""),
            "pmc": r.get("pmc", ""),
            "doi": r.get("doi", ""),
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "journal": r.get("journal", ""),
            "journal_abbrev": r.get("journal_abbrev", ""),
            "year": r.get("year", ""),
            "pub_date": pub_date(r),
            "language": r.get("language", ""),
            "article_types": pipe(r.get("article_types") or []),
            "n_authors": r.get("author_count", 0),
            "n_institutions": r.get("n_institutions", 0),
            "n_countries": r.get("n_countries", 0),
            "primary_domain": r.get("primary_domain", ""),
            "primary_domain_label": domain_labels.get(r.get("primary_domain", ""), ""),
            "domains": pipe(r.get("domains") or []),
            "is_multi_domain": int(bool(r.get("is_multi_domain"))),
            "singapore_led": int(bool(r.get("singapore_led"))),
            "is_international": int(bool(r.get("is_international"))),
            "first_author": r.get("first_author", ""),
            "last_author": r.get("last_author", ""),
            "first_author_country": r.get("first_author_country", ""),
            "last_author_country": r.get("last_author_country", ""),
            "sg_institutions": pipe(r.get("sg_institutions") or []),
            "countries": pipe(r.get("countries") or []),
            "institutions": pipe(r.get("institutions") or []),
            "topic_id": t.get("topic_id", ""),
            "topic_label": t.get("topic_label", ""),
            "topic_terms": t.get("topic_terms", ""),
            "screening_decision": scr.get("decision", ""),
            "screening_decided_by": scr.get("decided_by", ""),
            "screening_rules": pipe(scr.get("rules_fired") or []),
            "screening_flags": pipe(scr.get("flags") or []),
            "sources": pipe(r.get("sources") or []),
            "query_ids": pipe(r.get("query_ids") or []),
            "needs_manual_metadata": int(bool(r.get("needs_manual_metadata"))),
        })
    return rows


def build_domains(records, domain_labels):
    rows = []
    for r in records:
        for i, d in enumerate(r.get("domains") or []):
            rows.append({
                "uid": r["uid"],
                "domain_id": d,
                "domain_label": domain_labels.get(d, d),
                "is_primary": int(i == 0),
                "domain_score": (r.get("domain_scores") or {}).get(d, ""),
                "year": r.get("year", ""),
                "singapore_led": int(bool(r.get("singapore_led"))),
            })
    return rows


def build_authors(records):
    rows, aff_rows = [], []
    for r in records:
        for a in r.get("authors_resolved") or []:
            rows.append({
                "uid": r["uid"],
                "author_key": a["author_key"],
                "author_name": a["author_name"],
                "position": a["position"],
                "is_first": int(a["is_first"]),
                "is_last": int(a["is_last"]),
                "institution": a["institutions"][0] if a["institutions"] else "",
                "country": a["countries"][0] if a["countries"] else "",
                "sector": a["sectors"][0] if a["sectors"] else "",
                "n_affiliations": len(a["affiliations"]),
                "year": r.get("year", ""),
                "primary_domain": r.get("primary_domain", ""),
            })
            for aff in a["affiliations"]:
                aff_rows.append({
                    "uid": r["uid"],
                    "author_key": a["author_key"],
                    "author_name": a["author_name"],
                    "position": a["position"],
                    "affiliation_raw": aff["affiliation_raw"],
                    "institution": aff["institution"],
                    "institution_short": aff["institution_short"],
                    "sector": aff["sector"],
                    "country": aff["country"],
                    "iso3": aff["iso3"],
                    "region": aff["region"],
                    "resolved": int(aff["resolved"]),
                })
    return rows, aff_rows


def build_institution_country(records):
    inst_rows, ctry_rows = [], []
    for r in records:
        inst_counts = Counter()
        inst_meta = {}
        ctry_counts = Counter()
        ctry_meta = {}
        for a in r.get("authors_resolved") or []:
            for aff in a["affiliations"]:
                if aff["institution"]:
                    inst_counts[aff["institution"]] += 1
                    inst_meta[aff["institution"]] = aff
                if aff["country"]:
                    ctry_counts[aff["country"]] += 1
                    ctry_meta[aff["country"]] = aff
        for inst, n in inst_counts.items():
            m = inst_meta[inst]
            inst_rows.append({
                "uid": r["uid"], "institution": inst,
                "institution_short": m["institution_short"], "sector": m["sector"],
                "country": m["country"], "iso3": m["iso3"], "region": m["region"],
                "n_authors_here": n, "year": r.get("year", ""),
                "primary_domain": r.get("primary_domain", ""),
                "is_singapore": int(m["country"] == "Singapore"),
            })
        for ctry, n in ctry_counts.items():
            m = ctry_meta[ctry]
            ctry_rows.append({
                "uid": r["uid"], "country": ctry, "iso3": m["iso3"], "region": m["region"],
                "n_authors_here": n, "year": r.get("year", ""),
                "primary_domain": r.get("primary_domain", ""),
                "is_singapore": int(ctry == "Singapore"),
            })
    return inst_rows, ctry_rows


def build_edges(records, key, extra_lookup, min_weight=1, max_edges=None):
    """Undirected co-occurrence edges, split by primary_domain.

    key: 'institutions' | 'countries' -- the record-level deduped list.
    """
    counts = Counter()
    for r in records:
        items = sorted(set(r.get(key) or []))
        dom = r.get("primary_domain", "")
        for a, b in itertools.combinations(items, 2):
            counts[(a, b, dom)] += 1

    rows = []
    for (a, b, dom), w in counts.items():
        if w < min_weight:
            continue
        ma, mb = extra_lookup.get(a, {}), extra_lookup.get(b, {})
        rows.append({
            "edge_id": "%s--%s#%s" % (a, b, dom or "none"),
            "pair_id": "%s--%s" % (a, b),
            "source": a, "target": b, "domain": dom, "weight": w,
            "source_country": ma.get("country", ""), "target_country": mb.get("country", ""),
            "source_region": ma.get("region", ""), "target_region": mb.get("region", ""),
            "is_cross_border": int(bool(ma.get("country")) and bool(mb.get("country"))
                                   and ma.get("country") != mb.get("country")),
            "involves_singapore": int("Singapore" in (ma.get("country", ""), mb.get("country", ""))
                                      or "Singapore" in (a, b)),
        })
    rows.sort(key=lambda r: -r["weight"])
    if max_edges:
        rows = rows[:max_edges]
    return rows


def build_author_edges(records, min_weight=1, max_edges=5000):
    counts = Counter()
    names = {}
    meta = {}
    for r in records:
        authors = r.get("authors_resolved") or []
        keys = []
        for a in authors:
            if a["author_key"]:
                keys.append(a["author_key"])
                names[a["author_key"]] = a["author_name"]
                meta.setdefault(a["author_key"], {
                    "institution": a["institutions"][0] if a["institutions"] else "",
                    "country": a["countries"][0] if a["countries"] else ""})
        for a, b in itertools.combinations(sorted(set(keys)), 2):
            counts[(a, b)] += 1
    rows = []
    for (a, b), w in counts.items():
        if w < min_weight:
            continue
        rows.append({
            "edge_id": "%s--%s" % (a, b),
            "source": a, "target": b,
            "source_name": names.get(a, a), "target_name": names.get(b, b),
            "source_institution": meta.get(a, {}).get("institution", ""),
            "target_institution": meta.get(b, {}).get("institution", ""),
            "source_country": meta.get(a, {}).get("country", ""),
            "target_country": meta.get(b, {}).get("country", ""),
            "weight": w,
        })
    rows.sort(key=lambda r: -r["weight"])
    return rows[:max_edges]


def build_network(edge_rows, node_meta, node_pubs, max_nodes):
    """Node table with x/y plus an edge table in Tableau's two-row path form."""
    agg = Counter()
    for e in edge_rows:
        agg[(e["source"], e["target"])] += e["weight"]

    strength = Counter()
    for (s, t), w in agg.items():
        strength[s] += w
        strength[t] += w

    keep = {n for n, _ in strength.most_common(max_nodes)}
    truncated = len(strength) - len(keep)

    edges = [(s, t, w) for (s, t), w in agg.items() if s in keep and t in keep]
    pos = idlib.force_layout(sorted(keep), edges)

    degree = Counter()
    for s, t, _ in edges:
        degree[s] += 1
        degree[t] += 1

    nodes = []
    for n in sorted(keep):
        m = node_meta.get(n, {})
        x, y = pos.get(n, (0.5, 0.5))
        nodes.append({
            "node_id": n, "label": n,
            "country": m.get("country", ""), "region": m.get("region", ""),
            "sector": m.get("sector", ""), "iso3": m.get("iso3", ""),
            "is_singapore": int(m.get("country") == "Singapore" or n == "Singapore"),
            "x": x, "y": y,
            "degree": degree.get(n, 0),
            "weighted_degree": strength.get(n, 0),
            "n_publications": node_pubs.get(n, 0),
        })

    def emit(edge_id, pair_id, src, tgt, domain, weight, cross, sg):
        for order, node in ((1, src), (2, tgt)):
            x, y = pos.get(node, (0.5, 0.5))
            paths.append({
                "edge_id": edge_id, "pair_id": pair_id, "domain": domain,
                "path_order": order, "node_id": node, "label": node,
                "x": x, "y": y, "weight": weight,
                "source": src, "target": tgt,
                "is_cross_border": cross, "involves_singapore": sg,
            })

    paths = []
    meta_by_pair = {}
    for e in edge_rows:
        if e["source"] not in keep or e["target"] not in keep:
            continue
        pair = e.get("pair_id") or "%s--%s" % (e["source"], e["target"])
        meta_by_pair.setdefault(pair, e)
        emit(e["edge_id"], pair, e["source"], e["target"], e.get("domain", "") or "none",
             e["weight"], e.get("is_cross_border", ""), e.get("involves_singapore", ""))

    # domain="ALL": one path per pair, weights summed across domains
    for (s_, t_), w in agg.items():
        if s_ not in keep or t_ not in keep:
            continue
        pair = "%s--%s" % (s_, t_)
        m = meta_by_pair.get(pair, {})
        emit(pair + "#ALL", pair, s_, t_, "ALL", w,
             m.get("is_cross_border", ""), m.get("involves_singapore", ""))

    return nodes, paths, truncated


def build_summary(records, domain_labels):
    counts = Counter()
    sg_led = Counter()
    intl = Counter()
    for r in records:
        y = r.get("year", "")
        for d in r.get("domains") or []:
            counts[(d, y)] += 1
            if r.get("singapore_led"):
                sg_led[(d, y)] += 1
            if r.get("is_international"):
                intl[(d, y)] += 1
    rows = []
    for (d, y), n in sorted(counts.items()):
        rows.append({
            "domain_id": d, "domain_label": domain_labels.get(d, d), "year": y,
            "publications": n, "singapore_led": sg_led[(d, y)],
            "international": intl[(d, y)],
        })
    return rows


README = """# Dataset

One run of the Singapore ID research landscape pipeline. Every table keys on
`uid`. Column meanings and the Tableau setup for each chart live in
`reference/dataset-schema.md`.

| File | Grain | Join |
|---|---|---|
| `publications.csv` | one publication | primary table, key `uid` |
| `publication_domains.csv` | publication x domain | `uid` |
| `publication_authors.csv` | publication x author | `uid` |
| `publication_author_affiliations.csv` | publication x author x affiliation | `uid`, `author_key` |
| `publication_institutions.csv` | publication x institution | `uid` |
| `publication_countries.csv` | publication x country | `uid` |
| `coauthor_institution_edges.csv` | institution pair x domain | standalone |
| `coauthor_country_edges.csv` | country pair x domain | standalone |
| `coauthor_author_edges.csv` | author pair | standalone |
| `network_*_nodes.csv` | node | `node_id` |
| `network_*_paths.csv` | edge x endpoint | `edge_id`, join nodes on `node_id` |
| `summary_by_domain_year.csv` | domain x year | standalone |

## Counting rule

Use `publications.csv` for totals. Use `publication_domains.csv` (or the other
long tables) when slicing by domain, institution or country -- a publication
with three countries appears three times there, so `COUNTD([uid])` is the
correct measure, never `SUM(1)`.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--min-edge-weight", type=int, default=1)
    ap.add_argument("--max-network-nodes", type=int, default=150,
                    help="nodes kept in the laid-out network tables (by weighted degree)")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    src = os.path.join(p["classification"], "classified.jsonl")
    records = idlib.read_jsonl(src)
    if not records:
        raise SystemExit("No classified records at %s -- run classify.py first." % src)

    domain_labels = {d["domain_id"]: d.get("label", d["domain_id"])
                     for d in idlib.load_taxonomy()}
    domain_labels.setdefault("other_id", "Other infectious disease")

    topics = {}
    topics_path = os.path.join(p["topics"], "publication_topics.csv")
    for row in idlib.read_csv(topics_path):
        topics[row.get("uid", "")] = row

    out = p["dataset"]
    idlib.ensure_dirs(out)

    pubs = build_publications(records, domain_labels, topics)
    doms = build_domains(records, domain_labels)
    auths, auth_affs = build_authors(records)
    inst_rows, ctry_rows = build_institution_country(records)

    inst_meta, ctry_meta = {}, {}
    for r in inst_rows:
        inst_meta.setdefault(r["institution"], {
            "country": r["country"], "region": r["region"],
            "sector": r["sector"], "iso3": r["iso3"]})
    for r in ctry_rows:
        ctry_meta.setdefault(r["country"], {
            "country": r["country"], "region": r["region"], "iso3": r["iso3"]})

    inst_pubs = Counter(r["institution"] for r in inst_rows)
    ctry_pubs = Counter(r["country"] for r in ctry_rows)

    inst_edges = build_edges(records, "institutions", inst_meta, args.min_edge_weight)
    ctry_edges = build_edges(records, "countries", ctry_meta, args.min_edge_weight)
    auth_edges = build_author_edges(records, args.min_edge_weight)

    inodes, ipaths, itrunc = build_network(inst_edges, inst_meta, inst_pubs, args.max_network_nodes)
    cnodes, cpaths, ctrunc = build_network(ctry_edges, ctry_meta, ctry_pubs, args.max_network_nodes)

    written = []
    def w(name, rows, fields=None):
        n = idlib.write_csv(os.path.join(out, name), rows, fields)
        written.append((name, n))

    w("publications.csv", pubs)
    w("publication_domains.csv", doms)
    w("publication_authors.csv", auths)
    w("publication_author_affiliations.csv", auth_affs)
    w("publication_institutions.csv", inst_rows)
    w("publication_countries.csv", ctry_rows)
    w("coauthor_institution_edges.csv", inst_edges)
    w("coauthor_country_edges.csv", ctry_edges)
    w("coauthor_author_edges.csv", auth_edges)
    w("network_institution_nodes.csv", inodes)
    w("network_institution_paths.csv", ipaths)
    w("network_country_nodes.csv", cnodes)
    w("network_country_paths.csv", cpaths)
    w("summary_by_domain_year.csv", build_summary(records, domain_labels))

    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(README)

    print("Dataset written to %s" % os.path.abspath(out))
    for name, n in written:
        print("  %-40s %6d rows" % (name, n))
    if not topics:
        print("")
        print("topic_id/topic_label are empty: run topic_model.py, then re-run this")
        print("script to fold the topics into publications.csv.")
    if itrunc or ctrunc:
        print("")
        print("Network truncated to the top %d nodes by weighted degree "
              "(%d institution, %d country nodes dropped)."
              % (args.max_network_nodes, itrunc, ctrunc))
        print("Edge tables are complete; only the laid-out network_* tables are capped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
