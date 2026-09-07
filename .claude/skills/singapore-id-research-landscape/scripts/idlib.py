"""Shared helpers for the Singapore ID research landscape skill.

Standard library only, so the pipeline runs anywhere Python 3.8+ exists.
Optional accelerators (numpy/scikit-learn/sentence-transformers) are used only
by topic_model.py and are always optional.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from collections import OrderedDict

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_DIR = os.path.join(SKILL_DIR, "reference")
DATA_DIR = os.path.join(SKILL_DIR, "data")

TAXONOMY_PATH = os.path.join(REFERENCE_DIR, "domain-taxonomy.md")
RESEARCH_TYPE_TAXONOMY_PATH = os.path.join(REFERENCE_DIR, "research-type-taxonomy.md")
CRITERIA_PATH = os.path.join(REFERENCE_DIR, "screening-criteria.md")
EXPERTS_PATH = os.path.join(DATA_DIR, "directory_of_experts.csv")
INSTITUTIONS_PATH = os.path.join(DATA_DIR, "institution_aliases.csv")
COUNTRIES_PATH = os.path.join(DATA_DIR, "country_aliases.csv")
MESH_STOPLIST_PATH = os.path.join(DATA_DIR, "mesh_stoplist.csv")


def run_paths(run_dir):
    """Standard sub-paths inside a run directory."""
    j = lambda *p: os.path.join(run_dir, *p)
    return {
        "root": run_dir,
        "raw": j("raw"),
        "records": j("records.jsonl"),
        "screening": j("screening"),
        "classification": j("classification"),
        "dataset": j("dataset"),
        "topics": j("topics"),
        "queries": j("queries.json"),
        "manifest": j("manifest.json"),
    }


def ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv(path, rows, fieldnames=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not rows:
        # still write the header when we know it, so downstream joins don't break
        if fieldnames:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                csv.DictWriter(fh, fieldnames=fieldnames).writeheader()
        return 0
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Reference-file parsing
# --------------------------------------------------------------------------

_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def _json_blocks(path):
    if not os.path.exists(path):
        raise SystemExit("Missing reference file: %s" % path)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    blocks = []
    for i, raw in enumerate(_JSON_BLOCK.findall(text)):
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "Malformed JSON block #%d in %s: %s\nFix the fenced json block and re-run."
                % (i + 1, os.path.basename(path), exc)
            )
    return blocks


def load_taxonomy():
    """Domain definitions from reference/domain-taxonomy.md, in file order."""
    domains = [b for b in _json_blocks(TAXONOMY_PATH) if "domain_id" in b]
    if not domains:
        raise SystemExit("No domain blocks found in %s" % TAXONOMY_PATH)
    for d in domains:
        d.setdefault("terms", {})
        d.setdefault("mesh_terms", {})
        d.setdefault("blockers", [])
        d.setdefault("threshold", 4)
    return domains


def load_mechanical_rules():
    """Machine-applicable rules from reference/screening-criteria.md."""
    return [b for b in _json_blocks(CRITERIA_PATH) if "rule_id" in b]


def load_mesh_stoplist():
    """Generic/demographic/methodological MeSH headings to exclude when
    deriving sub-domains from MeSH-term frequency (see classify.py).

    This is noise-filtering infrastructure, not domain content: it excludes
    headings like "Humans", "Female", "Retrospective Studies" that would
    otherwise dominate every domain's frequency ranking without describing
    what the research is actually about. It contains no disease or pathogen
    names, and it is never used to decide what a sub-domain IS -- that comes
    only from which MeSH terms the corpus itself uses most.

    Returns a lowercase set for case-insensitive matching.
    """
    rows = read_csv(MESH_STOPLIST_PATH)
    return {(r.get("mesh_term") or "").strip().lower() for r in rows if r.get("mesh_term")}


def load_research_type_taxonomy():
    """Cross-cutting research-type blocks from reference/research-type-taxonomy.md.

    Each block is shaped for score_taxa(..., id_field='type_id').
    """
    blocks = [b for b in _json_blocks(RESEARCH_TYPE_TAXONOMY_PATH) if "type_id" in b]
    for b in blocks:
        b.setdefault("terms", {})
        b.setdefault("mesh_terms", {})
        b.setdefault("blockers", [])
        b.setdefault("threshold", 3)
    return blocks


def load_experts():
    rows = read_csv(EXPERTS_PATH)
    return [r for r in rows if (r.get("full_name") or "").strip()]


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------

def strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def norm_title(title):
    """Aggressive normalisation used only as a dedupe key."""
    t = strip_accents((title or "").lower())
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def norm_doi(doi):
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/)", "", d)
    return d.rstrip(".")


def _term_regex(term):
    """Compile a taxonomy term. Trailing '*' means prefix match."""
    prefix = term.endswith("*")
    core = term[:-1] if prefix else term
    pat = re.escape(core.strip().lower())
    # collapse escaped whitespace so "sars cov 2" spacing variants still match
    pat = pat.replace(r"\ ", r"[\s\-]+")
    tail = r"\w*" if prefix else ""
    return re.compile(r"(?<!\w)" + pat + tail + r"(?!\w)", re.I)


_TERM_CACHE = {}


def term_regex(term):
    if term not in _TERM_CACHE:
        _TERM_CACHE[term] = _term_regex(term)
    return _TERM_CACHE[term]


def contains_term(text, term):
    if not text:
        return False
    return bool(term_regex(term).search(text))


# --------------------------------------------------------------------------
# Affiliation parsing
# --------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\S+@\S+")
_ELECTRONIC_RE = re.compile(r"electronic address\s*:.*$", re.I)


def split_affiliation(raw):
    """One PubMed affiliation string may pack several affiliations, ';'-joined."""
    if not raw:
        return []
    s = _ELECTRONIC_RE.sub("", raw)
    s = _EMAIL_RE.sub("", s)
    parts = [p.strip(" .;,") for p in s.split(";")]
    return [p for p in parts if len(p) > 2]


class AffiliationResolver:
    """Maps a free-text affiliation segment to an institution and a country."""

    def __init__(self, institutions=None, countries=None):
        inst = institutions if institutions is not None else read_csv(INSTITUTIONS_PATH)
        ctry = countries if countries is not None else read_csv(COUNTRIES_PATH)
        # longest pattern first so "papua new guinea" beats "guinea"
        self.inst = sorted(inst, key=lambda r: -len(r.get("pattern", "")))
        self.ctry = sorted(ctry, key=lambda r: -len(r.get("pattern", "")))
        self._inst_re = [(re.compile(r"(?<!\w)" + re.escape(r["pattern"].lower()) + r"(?!\w)"), r)
                         for r in self.inst if r.get("pattern")]
        self._ctry_re = [(re.compile(r"(?<!\w)" + re.escape(r["pattern"].lower()) + r"(?!\w)"), r)
                         for r in self.ctry if r.get("pattern")]
        self.unmapped_institution = OrderedDict()
        self.unmapped_country = OrderedDict()

    def resolve(self, segment):
        seg = strip_accents(segment.lower())
        out = {
            "affiliation_raw": segment.strip(),
            "institution": "",
            "institution_short": "",
            "sector": "",
            "country": "",
            "iso3": "",
            "region": "",
            "resolved": False,
        }

        for rx, row in self._inst_re:
            if rx.search(seg):
                out["institution"] = row["institution_canonical"]
                out["institution_short"] = row.get("institution_short", "")
                out["sector"] = row.get("sector", "")
                if row.get("country"):
                    out["country"] = row["country"]
                break

        # Country from the string itself wins over the alias table's default,
        # because an institution can appear at an overseas campus or unit.
        best = None
        for rx, row in self._ctry_re:
            m = None
            for m in rx.finditer(seg):
                pass  # keep the last occurrence: country sits at the end
            if m is not None:
                if best is None or m.start() > best[0]:
                    best = (m.start(), row)
        if best is not None:
            row = best[1]
            out["country"] = row["country_canonical"]
            out["iso3"] = row.get("iso3", "")
            out["region"] = row.get("region", "")
        elif out["country"]:
            for _, row in self._ctry_re:
                if row["country_canonical"] == out["country"]:
                    out["iso3"] = row.get("iso3", "")
                    out["region"] = row.get("region", "")
                    break

        if not out["institution"]:
            self.unmapped_institution[segment.strip()] = \
                self.unmapped_institution.get(segment.strip(), 0) + 1
        if not out["country"]:
            self.unmapped_country[segment.strip()] = \
                self.unmapped_country.get(segment.strip(), 0) + 1

        out["resolved"] = bool(out["institution"] and out["country"])
        return out


# --------------------------------------------------------------------------
# Author utilities
# --------------------------------------------------------------------------

def author_display(author):
    fore = (author.get("fore_name") or "").strip()
    last = (author.get("last_name") or "").strip()
    if last and fore:
        return "%s, %s" % (last, fore)
    return last or fore or (author.get("collective_name") or "").strip()


def author_key(author):
    """Stable-ish author identity: lastname + first initial, accent-folded.

    PubMed has no universal author ID, so this will merge some distinct people
    who share a surname and initial. That limitation is stated in
    reference/dataset-schema.md; ORCID from the expert roster is preferred
    wherever it is available.
    """
    last = strip_accents((author.get("last_name") or "").lower())
    fore = strip_accents((author.get("fore_name") or "").lower())
    initials = strip_accents((author.get("initials") or "").lower())
    first = (fore[:1] or initials[:1] or "")
    last = re.sub(r"[^a-z]", "", last)
    if not last:
        coll = strip_accents((author.get("collective_name") or "").lower())
        return re.sub(r"[^a-z0-9]+", "-", coll).strip("-")
    return "%s-%s" % (last, first) if first else last


def eprint(*args):
    print(*args, file=sys.stderr)


# --------------------------------------------------------------------------
# Domain scoring (shared by screen.py and classify.py)
# --------------------------------------------------------------------------

def record_fields(rec):
    """The four text surfaces a domain is scored over."""
    return {
        "title": rec.get("title") or "",
        "abstract": rec.get("abstract") or "",
        "keywords": " ; ".join(rec.get("keywords") or []),
        "mesh": " ; ".join(rec.get("mesh_terms") or []),
    }


def score_domain(rec, domain, fields=None):
    """Score one record against one domain.

    Title, keyword and MeSH hits count double; abstract hits count once. Each
    term scores at most once per field. A blocker term in the title zeroes the
    domain. Returns (score, matched_terms).
    """
    f = fields or record_fields(rec)
    title = f["title"]

    for b in domain.get("blockers", []):
        if contains_term(title, b):
            return 0, []

    score = 0
    matched = []

    for term, weight in domain.get("terms", {}).items():
        hit_strong = (contains_term(title, term) or contains_term(f["keywords"], term)
                      or contains_term(f["mesh"], term))
        hit_weak = contains_term(f["abstract"], term)
        if hit_strong:
            score += weight * 2
            matched.append(term)
        elif hit_weak:
            score += weight
            matched.append(term)

    mesh_set = {m.lower() for m in (rec.get("mesh_terms") or [])}
    for mterm, weight in domain.get("mesh_terms", {}).items():
        if mterm.lower() in mesh_set:
            score += weight * 2
            matched.append("MeSH:" + mterm)

    return score, matched


def score_taxa(rec, taxa, id_field="domain_id"):
    """{taxon_id: {'score', 'matched', 'assigned', 'label'}} for a list of
    domain-shaped taxonomy blocks (terms/mesh_terms/threshold/blockers).

    Generic over id_field so the same scorer drives domains, sub-domains
    (id_field='subdomain_id') and research types (id_field='type_id').
    """
    fields = record_fields(rec)
    out = OrderedDict()
    for t in taxa:
        score, matched = score_domain(rec, t, fields)
        out[t[id_field]] = {
            "score": score,
            "matched": matched,
            "assigned": score >= t.get("threshold", 4),
            "label": t.get("label", t[id_field]),
        }
    return out


def assigned_taxa(scores):
    """Assigned taxon ids from a score_taxa() result, highest score first."""
    return [k for k, v in sorted(scores.items(), key=lambda kv: -kv[1]["score"]) if v["assigned"]]


def score_domains(rec, domains):
    """{domain_id: {...}} for all domains. Thin wrapper over score_taxa()."""
    return score_taxa(rec, domains, id_field="domain_id")


def assigned_domains(scores):
    """Assigned domain ids, highest score first. Alias of assigned_taxa()."""
    return assigned_taxa(scores)


# --------------------------------------------------------------------------
# Network layout (for Tableau network views)
# --------------------------------------------------------------------------

def force_layout(nodes, edges, iterations=250, seed=42):
    """Deterministic Fruchterman-Reingold layout, standard library only.

    nodes: iterable of node ids
    edges: iterable of (source, target, weight)
    Returns {node_id: (x, y)} normalised into [0, 1].

    O(n^2) per iteration, so it is intended for up to a few hundred nodes --
    build_dataset.py caps the node count and says so in the report.
    """
    import math
    import random

    vs = list(dict.fromkeys(nodes))
    n = len(vs)
    if n == 0:
        return {}
    if n == 1:
        return {vs[0]: (0.5, 0.5)}
    if n == 2:
        return {vs[0]: (0.15, 0.5), vs[1]: (0.85, 0.5)}

    rng = random.Random(seed)
    # deterministic ring start, jittered: avoids the degenerate all-random collapse
    pos = {}
    for i, v in enumerate(vs):
        ang = 2 * math.pi * i / n
        pos[v] = [0.5 * math.cos(ang) + rng.uniform(-0.02, 0.02),
                  0.5 * math.sin(ang) + rng.uniform(-0.02, 0.02)]

    idx = {v: i for i, v in enumerate(vs)}
    elist = [(idx[s], idx[t], float(w or 1))
             for s, t, w in edges if s in idx and t in idx and s != t]
    maxw = max((w for _, _, w in elist), default=1.0)

    k = math.sqrt(1.0 / n)
    temp = 0.12
    eps = 1e-9

    for _ in range(iterations):
        disp = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            xi, yi = pos[vs[i]]
            for j in range(i + 1, n):
                xj, yj = pos[vs[j]]
                dx, dy = xi - xj, yi - yj
                d2 = dx * dx + dy * dy
                d = math.sqrt(d2) if d2 > eps else eps
                rep = (k * k) / d
                ux, uy = dx / d, dy / d
                disp[i][0] += ux * rep
                disp[i][1] += uy * rep
                disp[j][0] -= ux * rep
                disp[j][1] -= uy * rep
        for si, ti, w in elist:
            xi, yi = pos[vs[si]]
            xj, yj = pos[vs[ti]]
            dx, dy = xi - xj, yi - yj
            d = math.sqrt(dx * dx + dy * dy) or eps
            att = (d * d) / k * (0.4 + 0.6 * (w / maxw))
            ux, uy = dx / d, dy / d
            disp[si][0] -= ux * att
            disp[si][1] -= uy * att
            disp[ti][0] += ux * att
            disp[ti][1] += uy * att
        for i, v in enumerate(vs):
            dx, dy = disp[i]
            d = math.sqrt(dx * dx + dy * dy) or eps
            step = min(d, temp)
            pos[v][0] += dx / d * step
            pos[v][1] += dy / d * step
        temp *= 0.97

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    sx = (maxx - minx) or 1.0
    sy = (maxy - miny) or 1.0
    return {v: (round((p[0] - minx) / sx, 6), round((p[1] - miny) / sy, 6))
            for v, p in pos.items()}
