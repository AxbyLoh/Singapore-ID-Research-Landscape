#!/usr/bin/env python3
"""Emit the Tableau-ready dataset from classification/classified.jsonl.

Writes <run-dir>/dataset/:

  publications.csv                 fact table, one row per publication
  publication_domains.csv          long: publication x domain
  publication_subdomains.csv       long: publication x sub-domain (within primary_domain)
  publication_research_types.csv   long: publication x research type (multi-label)
  publication_authors.csv          long: publication x author
  publication_author_affiliations.csv  long: publication x author x affiliation
  publication_institutions.csv     long: publication x institution (deduped)
  publication_countries.csv        long: publication x country (deduped)
  coauthor_institution_edges.csv   institution pairs, per domain, weighted
  coauthor_country_edges.csv       country pairs, per domain, weighted
  coauthor_author_edges.csv        author pairs, per domain, weighted
  network_institution_nodes.csv    node table with x/y for a network view
  network_institution_paths.csv    edge table in Tableau path form
  network_country_nodes.csv        "
  network_country_paths.csv        "
  network_author_nodes.csv         "  -- x/y stable across domains; filter edges by domain
  network_author_paths.csv         "
  summary_top_authors.csv          author x domain, ranked by publication count
  summary_by_domain_year.csv       domain x year aggregate
  summary_subdomain_year.csv       domain x sub-domain x year -- the donut chart's data
  summary_research_type_year.csv   research type x year -- the "Types of research" bar chart's data
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
            "primary_subdomain": r.get("primary_subdomain", ""),
            "subdomains": pipe(r.get("subdomains") or []),
            "research_types": pipe(r.get("research_type_labels") or []),
            "n_research_types": len(r.get("research_types") or []),
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


def build_subdomains(records, subdomain_labels):
    """Long: publication x sub-domain. is_primary marks the donut-chart slice.

    subdomain_labels: {(domain_id, subdomain_id): label}
    """
    rows = []
    for r in records:
        dom = r.get("primary_domain", "")
        all_ids = r.get("subdomains") or []
        scores = r.get("subdomain_scores") or {}
        ranked = sorted(all_ids, key=lambda k: -scores.get(k, 0))
        for i, sid in enumerate(ranked):
            rows.append({
                "uid": r["uid"], "domain_id": dom, "subdomain_id": sid,
                "subdomain_label": subdomain_labels.get((dom, sid), sid),
                "is_primary": int(i == 0), "subdomain_score": scores.get(sid, ""),
                "year": r.get("year", ""),
            })
        if not ranked:
            rows.append({
                "uid": r["uid"], "domain_id": dom, "subdomain_id": "other",
                "subdomain_label": r.get("primary_subdomain") or "Other/unspecified",
                "is_primary": 1, "subdomain_score": "", "year": r.get("year", ""),
            })
    return rows


def build_research_types(records):
    """Long: publication x research type. Multi-label, no primary."""
    rows = []
    for r in records:
        for t, label in zip(r.get("research_types") or [], r.get("research_type_labels") or []):
            rows.append({
                "uid": r["uid"], "type_id": t, "type_label": label,
                "type_score": (r.get("research_type_scores") or {}).get(t, ""),
                "year": r.get("year", ""), "primary_domain": r.get("primary_domain", ""),
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


def build_author_edges(records, min_weight=1, max_edges=8000):
    """Author co-publication pairs, split by primary_domain (plus 'ALL' via
    build_network's aggregation), mirroring build_edges() for institutions.
    """
    counts = Counter()
    names = {}
    meta = {}
    for r in records:
        authors = r.get("authors_resolved") or []
        dom = r.get("primary_domain", "")
        keys = []
        for a in authors:
            if a["author_key"]:
                keys.append(a["author_key"])
                names[a["author_key"]] = a["author_name"]
                meta.setdefault(a["author_key"], {
                    "institution": a["institutions"][0] if a["institutions"] else "",
                    "country": a["countries"][0] if a["countries"] else ""})
        for a, b in itertools.combinations(sorted(set(keys)), 2):
            counts[(a, b, dom)] += 1
    rows = []
    for (a, b, dom), w in counts.items():
        if w < min_weight:
            continue
        rows.append({
            "edge_id": "%s--%s#%s" % (a, b, dom or "none"),
            "pair_id": "%s--%s" % (a, b),
            "source": a, "target": b, "domain": dom, "weight": w,
            "source_name": names.get(a, a), "target_name": names.get(b, b),
            "source_institution": meta.get(a, {}).get("institution", ""),
            "target_institution": meta.get(b, {}).get("institution", ""),
            "source_country": meta.get(a, {}).get("country", ""),
            "target_country": meta.get(b, {}).get("country", ""),
        })
    rows.sort(key=lambda r: -r["weight"])
    return rows[:max_edges]


def build_top_authors(records, domain_labels):
    """Ranked author x domain publication counts, plus an 'ALL' domain.

    This is the table behind the reference dashboard's "top N authors" list:
    filter to one domain_id, sort by n_publications descending.
    """
    counts = Counter()
    meta = {}
    for r in records:
        seen_authors = set()
        for a in r.get("authors_resolved") or []:
            if not a["author_key"] or a["author_key"] in seen_authors:
                continue
            seen_authors.add(a["author_key"])
            meta.setdefault(a["author_key"], {
                "author_name": a["author_name"],
                "institution": a["institutions"][0] if a["institutions"] else "",
                "country": a["countries"][0] if a["countries"] else ""})
            for dom in (r.get("domains") or []):
                counts[(dom, a["author_key"])] += 1
            counts[("ALL", a["author_key"])] += 1

    by_domain = defaultdict(list)
    for (dom, key), n in counts.items():
        by_domain[dom].append((key, n))

    rows = []
    for dom, entries in by_domain.items():
        entries.sort(key=lambda kv: -kv[1])
        for rank, (key, n) in enumerate(entries, 1):
            m = meta.get(key, {})
            rows.append({
                "domain_id": dom,
                "domain_label": "All domains" if dom == "ALL" else domain_labels.get(dom, dom),
                "author_key": key, "author_name": m.get("author_name", key),
                "institution": m.get("institution", ""), "country": m.get("country", ""),
                "n_publications": n, "rank_in_domain": rank,
            })
    rows.sort(key=lambda r: (r["domain_id"], r["rank_in_domain"]))
    return rows


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


def build_subdomain_summary(records, domain_labels):
    """domain x primary_subdomain x year -- the donut chart's data, pre-aggregated.

    Mutually exclusive within a domain (uses primary_subdomain only), so
    values sum to that domain's publication count for a given year.
    """
    counts = Counter()
    for r in records:
        dom = r.get("primary_domain", "")
        sd = r.get("primary_subdomain") or "Other/unspecified"
        y = r.get("year", "")
        counts[(dom, sd, y)] += 1
    rows = []
    for (dom, sd, y), n in sorted(counts.items()):
        rows.append({
            "domain_id": dom, "domain_label": domain_labels.get(dom, dom),
            "subdomain_label": sd, "year": y, "publications": n,
        })
    return rows


def build_research_type_summary(records):
    """type x year, multi-label -- the "Types of research" bar chart's data."""
    counts = Counter()
    for r in records:
        y = r.get("year", "")
        for label in r.get("research_type_labels") or []:
            counts[(label, y)] += 1
    rows = []
    for (label, y), n in sorted(counts.items()):
        rows.append({"type_label": label, "year": y, "publications": n})
    return rows


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
| `publication_subdomains.csv` | publication x sub-domain | `uid` |
| `publication_research_types.csv` | publication x research type | `uid` |
| `publication_authors.csv` | publication x author | `uid` |
| `publication_author_affiliations.csv` | publication x author x affiliation | `uid`, `author_key` |
| `publication_institutions.csv` | publication x institution | `uid` |
| `publication_countries.csv` | publication x country | `uid` |
| `coauthor_institution_edges.csv` | institution pair x domain | standalone |
| `coauthor_country_edges.csv` | country pair x domain | standalone |
| `coauthor_author_edges.csv` | author pair x domain | standalone |
| `network_*_nodes.csv` | node | `node_id` |
| `network_*_paths.csv` | edge x endpoint | `edge_id`, join nodes on `node_id` |
| `summary_top_authors.csv` | author x domain | standalone -- ranked, for a "top N" list |
| `summary_by_domain_year.csv` | domain x year | standalone |
| `summary_subdomain_year.csv` | domain x sub-domain x year | standalone -- donut chart source |
| `summary_research_type_year.csv` | research type x year | standalone -- research-type bar chart source |

## Counting rule

Use `publications.csv` for totals. Use `publication_domains.csv` (or the other
long tables) when slicing by domain, institution or country -- a publication
with three countries appears three times there, so `COUNTD([uid])` is the
correct measure, never `SUM(1)`.

## Sub-domain vs. domain vs. research type

Three independent classification axes, all in `publications.csv`:

- `primary_domain` / `domains` -- the 5 domains (a publication can be multi-domain)
- `primary_subdomain` / `subdomains` -- named sub-domain **within** the primary
  domain (e.g. "Dengue virus" within Vector-borne diseases); `primary_subdomain`
  is mutually exclusive per domain and is what the donut chart should use
- `research_types` -- cross-cutting "what kind of research" tags (Genomics,
  Surveillance and epidemiology, ...), multi-label, no primary
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--min-edge-weight", type=int, default=1)
    ap.add_argument("--max-network-nodes", type=int, default=150,
                    help="nodes kept in the laid-out institution/country network tables")
    ap.add_argument("--max-author-network-nodes", type=int, default=250,
                    help="nodes kept in the laid-out author network table")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    src = os.path.join(p["classification"], "classified.jsonl")
    records = idlib.read_jsonl(src)
    if not records:
        raise SystemExit("No classified records at %s -- run classify.py first." % src)

    domain_labels = {d["domain_id"]: d.get("label", d["domain_id"])
                     for d in idlib.load_taxonomy()}
    domain_labels.setdefault("other_id", "Other infectious disease")

    subdomain_labels = {}
    for dom, blocks in idlib.load_subdomain_taxonomy().items():
        for b in blocks:
            subdomain_labels[(dom, b["subdomain_id"])] = b.get("label", b["subdomain_id"])

    topics = {}
    topics_path = os.path.join(p["topics"], "publication_topics.csv")
    for row in idlib.read_csv(topics_path):
        topics[row.get("uid", "")] = row

    out = p["dataset"]
    idlib.ensure_dirs(out)

    pubs = build_publications(records, domain_labels, topics)
    doms = build_domains(records, domain_labels)
    subdoms = build_subdomains(records, subdomain_labels)
    rtypes = build_research_types(records)
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
    top_authors = build_top_authors(records, domain_labels)

    author_meta = {}
    for a in auth_affs:
        if a["author_key"] not in author_meta and a["institution"]:
            author_meta[a["author_key"]] = {
                "country": a["country"], "region": a["region"],
                "sector": a["sector"], "iso3": a["iso3"]}
    author_pubs = Counter(r["author_key"] for r in auths)

    inodes, ipaths, itrunc = build_network(inst_edges, inst_meta, inst_pubs, args.max_network_nodes)
    cnodes, cpaths, ctrunc = build_network(ctry_edges, ctry_meta, ctry_pubs, args.max_network_nodes)
    anodes, apaths, atrunc = build_network(auth_edges, author_meta, author_pubs,
                                           args.max_author_network_nodes)
    # build_network labels nodes by node_id (author_key); swap in the display name
    author_names = {a["author_key"]: a["author_name"] for a in auths}
    for n in anodes:
        n["label"] = author_names.get(n["node_id"], n["node_id"])
    for pr in apaths:
        pr["label"] = author_names.get(pr["node_id"], pr["node_id"])

    written = []
    def w(name, rows, fields=None):
        n = idlib.write_csv(os.path.join(out, name), rows, fields)
        written.append((name, n))

    w("publications.csv", pubs)
    w("publication_domains.csv", doms)
    w("publication_subdomains.csv", subdoms)
    w("publication_research_types.csv", rtypes)
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
    w("network_author_nodes.csv", anodes)
    w("network_author_paths.csv", apaths)
    w("summary_top_authors.csv", top_authors)
    w("summary_by_domain_year.csv", build_summary(records, domain_labels))
    w("summary_subdomain_year.csv", build_subdomain_summary(records, domain_labels))
    w("summary_research_type_year.csv", build_research_type_summary(records))

    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(README)

    print("Dataset written to %s" % os.path.abspath(out))
    for name, n in written:
        print("  %-40s %6d rows" % (name, n))
    if not topics:
        print("")
        print("topic_id/topic_label are empty: run topic_model.py, then re-run this")
        print("script to fold the topics into publications.csv.")
    if itrunc or ctrunc or atrunc:
        print("")
        print("Network truncated to the top nodes by weighted degree: %d institution "
              "(cap %d), %d country (cap %d), %d author (cap %d) dropped."
              % (itrunc, args.max_network_nodes, ctrunc, args.max_network_nodes,
                 atrunc, args.max_author_network_nodes))
        print("Edge tables are complete; only the laid-out network_* tables are capped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
