#!/usr/bin/env python3
"""Normalise and deduplicate raw search output into <run-dir>/records.jsonl.

Reads everything the agent saved under <run-dir>/raw/:

  pubmed_<query_id>_<n>.json   a verbatim `get_article_metadata` response
                               ({"articles": [...]}), or a `search_articles`
                               response (used only for provenance/coverage)
  scholar_<query_id>.jsonl     one JSON object per Scholar lead

Deduplication precedence: DOI -> PMID -> normalised title. Records merge rather
than overwrite: identifiers, query provenance and sources are unioned, and the
richer metadata wins field by field.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

PUBMED_FILE_RE = re.compile(r"^pubmed_(?P<qid>.+?)(?:_(?P<part>\d+))?\.json$")
SCHOLAR_FILE_RE = re.compile(r"^scholar_(?P<qid>.+?)\.jsonl$")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def norm_pubmed_article(art, query_id):
    ids = art.get("identifiers") or {}
    pmid = str(ids.get("pmid") or art.get("pmid") or "").strip()
    doi = idlib.norm_doi(ids.get("doi") or art.get("doi") or "")
    pmc = str(ids.get("pmc") or "").strip()

    pd = art.get("publication_date") or {}
    year = str(pd.get("year") or "").strip()
    journal = art.get("journal") or {}

    authors = []
    for pos, a in enumerate(art.get("authors") or [], 1):
        affs = []
        for raw in (a.get("affiliations") or []):
            affs.extend(idlib.split_affiliation(raw))
        authors.append({
            "position": pos,
            "last_name": (a.get("last_name") or "").strip(),
            "fore_name": (a.get("fore_name") or "").strip(),
            "initials": (a.get("initials") or "").strip(),
            "collective_name": (a.get("collective_name") or "").strip(),
            "affiliations": affs,
            "affiliations_raw": list(a.get("affiliations") or []),
        })

    return {
        "uid": "",
        "pmid": pmid,
        "pmc": pmc,
        "doi": doi,
        "pii": str(ids.get("pii") or ""),
        "title": (art.get("title") or "").strip(),
        "abstract": (art.get("abstract") or "").strip(),
        "journal": (journal.get("title") or "").strip(),
        "journal_abbrev": (journal.get("iso_abbreviation") or "").strip(),
        "year": year,
        "month": str(pd.get("month") or ""),
        "day": str(pd.get("day") or ""),
        "authors": authors,
        "author_count": len(authors),
        "keywords": [k for k in (art.get("keywords") or []) if k],
        "mesh_terms": [m for m in (art.get("mesh_terms") or []) if m],
        "article_types": [t for t in (art.get("article_types") or []) if t],
        "language": (art.get("language") or "").strip(),
        "citation": art.get("citation") or {},
        "sources": ["pubmed"],
        "query_ids": [query_id] if query_id else [],
        "url": "https://pubmed.ncbi.nlm.nih.gov/%s/" % pmid if pmid else "",
        "needs_manual_metadata": False,
    }


def norm_scholar_hit(hit, query_id):
    title = (hit.get("title") or "").strip()
    return {
        "uid": "",
        "pmid": str(hit.get("pmid") or "").strip(),
        "pmc": "",
        "doi": idlib.norm_doi(hit.get("doi") or ""),
        "pii": "",
        "title": title,
        "abstract": (hit.get("snippet") or hit.get("abstract") or "").strip(),
        "journal": (hit.get("venue") or "").strip(),
        "journal_abbrev": "",
        "year": str(hit.get("year") or "").strip(),
        "month": "", "day": "",
        "authors": parse_scholar_authors(hit.get("authors_raw") or ""),
        "author_count": len(parse_scholar_authors(hit.get("authors_raw") or "")),
        "keywords": [], "mesh_terms": [], "article_types": [], "language": "",
        "citation": {},
        "sources": ["scholar"],
        "query_ids": [query_id] if query_id else [],
        "url": (hit.get("url") or "").strip(),
        "needs_manual_metadata": True,
    }


def parse_scholar_authors(raw):
    """Scholar author strings are unreliable; keep names, claim no affiliations."""
    out = []
    for pos, name in enumerate([n.strip() for n in re.split(r",| and ", raw) if n.strip()], 1):
        toks = name.split()
        out.append({
            "position": pos,
            "last_name": toks[-1] if toks else name,
            "fore_name": " ".join(toks[:-1]) if len(toks) > 1 else "",
            "initials": "",
            "collective_name": "",
            "affiliations": [],
            "affiliations_raw": [],
        })
    return out


# --------------------------------------------------------------------------
# Deduplication
# --------------------------------------------------------------------------

def dedupe_keys(rec):
    keys = []
    if rec.get("doi"):
        keys.append("doi:" + rec["doi"])
    if rec.get("pmid"):
        keys.append("pmid:" + rec["pmid"])
    nt = idlib.norm_title(rec.get("title"))
    if len(nt) >= 25:
        keys.append("title:" + nt)
    return keys


def richness(rec):
    return (len(rec.get("abstract") or ""), len(rec.get("authors") or []),
            len(rec.get("mesh_terms") or []), 1 if "pubmed" in rec.get("sources", []) else 0)


def merge_into(base, new):
    for field in ("pmid", "pmc", "doi", "pii", "abstract", "journal",
                  "journal_abbrev", "year", "month", "day", "language", "url"):
        if not base.get(field) and new.get(field):
            base[field] = new[field]
    for field in ("keywords", "mesh_terms", "article_types"):
        merged = list(dict.fromkeys((base.get(field) or []) + (new.get(field) or [])))
        base[field] = merged
    base["sources"] = sorted(set(base.get("sources", []) + new.get("sources", [])))
    base["query_ids"] = sorted(set(base.get("query_ids", []) + new.get("query_ids", [])))
    if richness(new) > richness(base):
        base["title"] = new.get("title") or base["title"]
        if new.get("authors"):
            base["authors"] = new["authors"]
            base["author_count"] = len(new["authors"])
        if new.get("abstract"):
            base["abstract"] = new["abstract"]
        if not new.get("needs_manual_metadata"):
            base["needs_manual_metadata"] = False
    if "pubmed" in base["sources"]:
        base["needs_manual_metadata"] = False
    return base


def assign_uid(rec):
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    if rec.get("pmid"):
        return "pmid:" + rec["pmid"]
    return "title:" + idlib.norm_title(rec.get("title"))[:80]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def load_raw(raw_dir):
    records = []
    coverage = OrderedDict()
    files = 0
    skipped = []

    for path in sorted(glob.glob(os.path.join(raw_dir, "*.json"))):
        name = os.path.basename(path)
        m = PUBMED_FILE_RE.match(name)
        if not m:
            skipped.append(name)
            continue
        qid = m.group("qid")
        try:
            payload = idlib.read_json(path)
        except json.JSONDecodeError as exc:
            idlib.eprint("  ! %s is not valid JSON (%s) -- skipped" % (name, exc))
            skipped.append(name)
            continue
        files += 1
        if isinstance(payload, dict) and "articles" in payload:
            for art in payload["articles"]:
                records.append(norm_pubmed_article(art, qid))
            cov = coverage.setdefault(qid, {"fetched": 0, "reported_total": None})
            cov["fetched"] += len(payload["articles"])
        elif isinstance(payload, dict) and "pmids" in payload:
            cov = coverage.setdefault(qid, {"fetched": 0, "reported_total": None})
            cov["reported_total"] = payload.get("total_count")
        elif isinstance(payload, list):
            for art in payload:
                records.append(norm_pubmed_article(art, qid))
            cov = coverage.setdefault(qid, {"fetched": 0, "reported_total": None})
            cov["fetched"] += len(payload)
        else:
            skipped.append(name)

    for path in sorted(glob.glob(os.path.join(raw_dir, "*.jsonl"))):
        name = os.path.basename(path)
        m = SCHOLAR_FILE_RE.match(name)
        if not m:
            skipped.append(name)
            continue
        qid = m.group("qid")
        files += 1
        for hit in idlib.read_jsonl(path):
            if (hit.get("title") or "").strip():
                records.append(norm_scholar_hit(hit, qid))
        coverage.setdefault(qid, {"fetched": 0, "reported_total": None})

    return records, coverage, files, skipped


def dedupe(records):
    index = {}
    kept = []
    dupes = 0
    for rec in records:
        hit = None
        for k in dedupe_keys(rec):
            if k in index:
                hit = index[k]
                break
        if hit is None:
            kept.append(rec)
            for k in dedupe_keys(rec):
                index[k] = rec
        else:
            merge_into(hit, rec)
            dupes += 1
            for k in dedupe_keys(hit):
                index.setdefault(k, hit)
    for rec in kept:
        rec["uid"] = assign_uid(rec)
    # a merge can make two survivors share a uid; keep the richer one
    final = {}
    for rec in kept:
        prev = final.get(rec["uid"])
        if prev is None:
            final[rec["uid"]] = rec
        else:
            merge_into(prev, rec)
            dupes += 1
    return list(final.values()), dupes


def write_report(path, stats, coverage, skipped):
    L = ["# Ingest report", ""]
    L.append("| Stage | Count |")
    L.append("|---|---|")
    for k, v in stats.items():
        L.append("| %s | %s |" % (k, v))
    L.append("")
    L.append("## Coverage by query")
    L.append("")
    L.append("`reported_total` is what PubMed said the query matched; `fetched` is how")
    L.append("many metadata records were actually saved. A large gap means paging stopped")
    L.append("early — the dataset is incomplete for that query.")
    L.append("")
    L.append("| query_id | fetched | reported_total | gap |")
    L.append("|---|---|---|---|")
    for qid, cov in coverage.items():
        total = cov["reported_total"]
        gap = "" if total is None else max(0, total - cov["fetched"])
        L.append("| `%s` | %d | %s | %s |" % (qid, cov["fetched"],
                                              "?" if total is None else total, gap))
    if skipped:
        L.append("")
        L.append("## Unrecognised files in raw/ (ignored)")
        L.append("")
        for s in skipped:
            L.append("- `%s`" % s)
        L.append("")
        L.append("Expected names: `pubmed_<query_id>_<n>.json`, `scholar_<query_id>.jsonl`.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    if not os.path.isdir(p["raw"]):
        raise SystemExit("No raw/ directory at %s -- run the searches first." % p["raw"])

    raw, coverage, files, skipped = load_raw(p["raw"])
    if not raw:
        raise SystemExit(
            "raw/ contains no readable results. Save each get_article_metadata "
            "response as raw/pubmed_<query_id>_<n>.json before running ingest.")

    records, dupes = dedupe(raw)
    records.sort(key=lambda r: (r.get("year") or "", r.get("title") or ""), reverse=True)
    idlib.write_jsonl(p["records"], records)

    scholar_only = sum(1 for r in records if r["sources"] == ["scholar"])
    no_abstract = sum(1 for r in records if not r["abstract"])
    stats = OrderedDict([
        ("raw files read", files),
        ("raw records parsed", len(raw)),
        ("duplicates merged", dupes),
        ("unique records", len(records)),
        ("Scholar-only (need metadata)", scholar_only),
        ("no abstract", no_abstract),
    ])
    write_report(os.path.join(args.run_dir, "ingest_report.md"), stats, coverage, skipped)

    print("Ingest complete")
    for k, v in stats.items():
        print("  %-30s %d" % (k, v))
    print("\n  -> %s" % p["records"])
    print("  -> %s" % os.path.join(args.run_dir, "ingest_report.md"))
    if scholar_only:
        print("\n%d Scholar-only record(s) are flagged needs_manual_metadata: resolve each"
              % scholar_only)
        print("to a PubMed record where one exists, or complete its metadata by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
