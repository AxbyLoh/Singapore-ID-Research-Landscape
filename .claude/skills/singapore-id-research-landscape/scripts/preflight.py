#!/usr/bin/env python3
"""Preflight checks for the Singapore ID research landscape skill.

Verifies the Python side of the environment and the state of the maintained
reference/data files. It CANNOT see the agent's MCP connectors -- the agent
must confirm the PubMed connector itself (see SKILL.md step 0).

Exit code 0 = ready, 1 = blocked.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

OPTIONAL_PACKAGES = [
    ("sentence_transformers", "best-quality topic embeddings"),
    ("sklearn", "TF-IDF + SVD + KMeans topic modelling"),
    ("numpy", "faster vector maths"),
]

OK, WARN, FAIL = "PASS", "WARN", "FAIL"


def check_python():
    v = sys.version_info
    ver = "%d.%d.%d" % (v.major, v.minor, v.micro)
    if v < (3, 8):
        return FAIL, "Python %s -- 3.8+ required" % ver
    return OK, "Python %s at %s" % (ver, sys.executable)


def check_optional():
    rows = []
    for mod, why in OPTIONAL_PACKAGES:
        try:
            importlib.import_module(mod)
            rows.append((OK, "%s available (%s)" % (mod, why)))
        except ImportError:
            rows.append((WARN, "%s not installed -- %s unavailable; a "
                               "standard-library fallback will be used" % (mod, why)))
    return rows


def check_taxonomy():
    try:
        domains = idlib.load_taxonomy()
    except SystemExit as exc:
        return FAIL, str(exc)
    n_terms = sum(len(d["terms"]) for d in domains)
    return OK, "%d domains, %d terms (%s)" % (
        len(domains), n_terms, ", ".join(d["domain_id"] for d in domains))


def check_criteria():
    if not os.path.exists(idlib.CRITERIA_PATH):
        return FAIL, "screening-criteria.md missing"
    try:
        rules = idlib.load_mechanical_rules()
    except SystemExit as exc:
        return FAIL, str(exc)
    with open(idlib.CRITERIA_PATH, encoding="utf-8") as fh:
        text = fh.read()
    if "## Amendment log" not in text:
        return WARN, ("%d mechanical rules, but no '## Amendment log' section -- "
                      "criteria amendments will have nowhere to go" % len(rules))
    return OK, "%d mechanical rules, amendment log present" % len(rules)


def check_experts():
    rows = idlib.load_experts()
    if not rows:
        return WARN, ("directory_of_experts.csv has no entries -- expert-based "
                      "searching will be skipped. Run fetch_experts.py, or add "
                      "rows by hand. Do NOT invent entries.")
    no_query = [r for r in rows
                if not (r.get("name_variants") or r.get("pubmed_author_query"))]
    if no_query:
        return WARN, ("%d experts loaded, but %d have neither name_variants nor "
                      "pubmed_author_query and cannot be searched"
                      % (len(rows), len(no_query)))
    return OK, "%d experts loaded" % len(rows)


def check_aliases():
    inst = idlib.read_csv(idlib.INSTITUTIONS_PATH)
    ctry = idlib.read_csv(idlib.COUNTRIES_PATH)
    if not inst or not ctry:
        return FAIL, "institution_aliases.csv or country_aliases.csv missing/empty"
    sg = sum(1 for r in inst if r.get("country") == "Singapore")
    return OK, "%d institution aliases (%d Singapore), %d country aliases" % (
        len(inst), sg, len(ctry))


def check_run_dir(run_dir):
    if not run_dir:
        return WARN, "No --run-dir given; pass one before searching"
    p = idlib.run_paths(run_dir)
    idlib.ensure_dirs(p["root"], p["raw"], p["screening"],
                      p["classification"], p["dataset"], p["topics"])
    existing = [k for k in ("records", "queries") if os.path.exists(p[k])]
    note = " (existing run: %s present)" % ", ".join(existing) if existing else " (new run)"
    return OK, "run directory ready at %s%s" % (os.path.abspath(run_dir), note)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", help="run directory to create/verify, e.g. runs/2026-09-07")
    args = ap.parse_args()

    checks = [
        ("Python runtime", check_python()),
        ("Domain taxonomy", check_taxonomy()),
        ("Screening criteria", check_criteria()),
        ("Expert directory", check_experts()),
        ("Alias tables", check_aliases()),
        ("Run directory", check_run_dir(args.run_dir)),
    ]

    print("Preflight -- Singapore ID research landscape")
    print("=" * 68)
    worst = OK
    for name, (status, detail) in checks:
        print("[%-4s] %-20s %s" % (status, name, detail))
        if status == FAIL:
            worst = FAIL
        elif status == WARN and worst != FAIL:
            worst = WARN

    print("-" * 68)
    print("Optional accelerators:")
    for status, detail in check_optional():
        print("[%-4s] %s" % (status, detail))

    print("-" * 68)
    print("NOT CHECKED HERE -- the agent must confirm these itself:")
    print("  * PubMed connector tools (search_articles, get_article_metadata,")
    print("    get_full_text_article, find_related_articles, convert_article_ids)")
    print("  * Web search availability, for Google Scholar coverage")
    print("  See reference/setup.md for what to tell the user if either is missing.")
    print("=" * 68)
    print("Result: %s" % ("BLOCKED - fix the FAIL rows above" if worst == FAIL
                          else "ready (with warnings)" if worst == WARN else "ready"))
    return 1 if worst == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
