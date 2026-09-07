#!/usr/bin/env python3
"""Cluster sub-domains of research WITHIN each domain, by semantic similarity.

Backends, best first -- whichever is installed is used, and the choice is
recorded in the output:

  1. sentence-transformers embeddings  (best: true semantic similarity)
  2. scikit-learn TF-IDF + TruncatedSVD (good: latent semantic space)
  3. pure standard-library TF-IDF       (always available; lexical only)

Writes <run-dir>/topics/:
  publication_topics.csv   uid -> topic_id, topic_label, topic_terms
  topic_labels.csv         EDITABLE: rewrite topic_label, then --relabel-only
  topics_report.md         cluster sizes, terms, exemplar titles

Clustering runs per domain, so a topic is always a sub-domain of one of the
five domains rather than a cross-cutting theme.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idlib  # noqa: E402

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can cannot could did do does doing done down during each few for from
further had has have having he her here hers herself him himself his how i if in into is it its
itself just me more most my myself no nor not now of off on once only or other ought our ours
ourselves out over own same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves
study studies aim aims objective objectives method methods result results conclusion conclusions
background introduction discussion findings data analysis analyses using used use significant
significantly associated association compared comparison increase increased decrease decreased
higher lower total overall respectively however therefore thus among between within across
patients patient cases case participants subjects cohort group groups control controls
we our this these those was were been being had has have paper article report reports
p n ci or rr hr aor 95 one two three four five first second new high low large small
singapore singaporean
""".split())

TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------

def doc_text(rec):
    parts = [rec.get("title") or "", rec.get("abstract") or ""]
    parts += rec.get("keywords") or []
    parts += rec.get("mesh_terms") or []
    return " ".join(parts)


def tokenize(text):
    toks = TOKEN_RE.findall(idlib.strip_accents((text or "").lower()))
    return [t.strip("-") for t in toks if t not in STOPWORDS and len(t) > 2]


# --------------------------------------------------------------------------
# Vectorisation
# --------------------------------------------------------------------------

def tfidf_vectors(docs, min_df=2, max_df_ratio=0.85):
    """Sparse L2-normalised TF-IDF as {term: weight} dicts. Standard library."""
    tokenised = [tokenize(d) for d in docs]
    n = len(tokenised)
    df = Counter()
    for toks in tokenised:
        for t in set(toks):
            df[t] += 1
    max_df = max(1, int(max_df_ratio * n))
    vocab = {t for t, c in df.items() if c >= min(min_df, n) and c <= max_df}
    if not vocab:
        vocab = set(df)

    vecs = []
    for toks in tokenised:
        tf = Counter(t for t in toks if t in vocab)
        if not tf:
            vecs.append({})
            continue
        maxtf = max(tf.values())
        v = {}
        for t, c in tf.items():
            idf = math.log((1.0 + n) / (1.0 + df[t])) + 1.0
            v[t] = (0.5 + 0.5 * c / maxtf) * idf
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def try_embeddings(docs):
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        return None, None
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(docs, normalize_embeddings=True, show_progress_bar=False)
        return [dict(enumerate(map(float, row))) for row in emb], "sentence-transformers/all-MiniLM-L6-v2"
    except Exception as exc:  # noqa: BLE001
        idlib.eprint("  sentence-transformers failed (%s); falling back" % exc)
        return None, None


def try_sklearn_svd(docs, n_components=64):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import normalize
    except ImportError:
        return None, None
    try:
        vec = TfidfVectorizer(stop_words=sorted(STOPWORDS), min_df=2, max_df=0.85,
                              sublinear_tf=True, token_pattern=r"[a-z][a-z0-9\-]{2,}")
        X = vec.fit_transform([d.lower() for d in docs])
        k = min(n_components, max(2, X.shape[1] - 1), max(2, X.shape[0] - 1))
        svd = TruncatedSVD(n_components=k, random_state=42)
        Z = normalize(svd.fit_transform(X))
        return [dict(enumerate(map(float, row))) for row in Z], "sklearn TF-IDF+SVD(%d)" % k
    except Exception as exc:  # noqa: BLE001
        idlib.eprint("  sklearn path failed (%s); falling back" % exc)
        return None, None


# --------------------------------------------------------------------------
# Spherical k-means
# --------------------------------------------------------------------------

def centroid(vecs, members):
    acc = defaultdict(float)
    for i in members:
        for t, w in vecs[i].items():
            acc[t] += w
    norm = math.sqrt(sum(x * x for x in acc.values())) or 1.0
    return {t: x / norm for t, x in acc.items()}


def kmeans(vecs, k, seed=42, iterations=60):
    n = len(vecs)
    rng = random.Random(seed)
    # k-means++ style seeding on cosine distance
    first = max(range(n), key=lambda i: len(vecs[i]))
    centres = [vecs[first]]
    while len(centres) < k:
        d2 = []
        for v in vecs:
            best = max((cosine(v, c) for c in centres), default=0.0)
            d2.append(max(0.0, 1.0 - best) ** 2)
        total = sum(d2)
        if total <= 0:
            centres.append(vecs[rng.randrange(n)])
            continue
        r = rng.random() * total
        acc = 0.0
        for i, w in enumerate(d2):
            acc += w
            if acc >= r:
                centres.append(vecs[i])
                break

    assign = [0] * n
    for _ in range(iterations):
        changed = False
        for i, v in enumerate(vecs):
            best, bi = -2.0, 0
            for ci, c in enumerate(centres):
                s = cosine(v, c)
                if s > best:
                    best, bi = s, ci
            if assign[i] != bi:
                assign[i] = bi
                changed = True
        groups = defaultdict(list)
        for i, a in enumerate(assign):
            groups[a].append(i)
        for ci in range(k):
            if groups[ci]:
                centres[ci] = centroid(vecs, groups[ci])
        if not changed:
            break
    return assign, centres


def silhouette(vecs, assign):
    """Mean cosine silhouette. O(n^2); fine for per-domain sizes."""
    n = len(vecs)
    groups = defaultdict(list)
    for i, a in enumerate(assign):
        groups[a].append(i)
    if len(groups) < 2:
        return -1.0
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = cosine(vecs[i], vecs[j])
            sim[i][j] = sim[j][i] = s
    total = 0.0
    for i in range(n):
        own = groups[assign[i]]
        if len(own) <= 1:
            continue
        a = sum(1.0 - sim[i][j] for j in own if j != i) / (len(own) - 1)
        b = min((sum(1.0 - sim[i][j] for j in g) / len(g)
                 for lbl, g in groups.items() if lbl != assign[i] and g), default=None)
        if b is None:
            continue
        denom = max(a, b)
        if denom > 0:
            total += (b - a) / denom
    return total / n


def choose_k(vecs, kmin, kmax, seed):
    best = (None, -2.0, None)
    for k in range(kmin, kmax + 1):
        assign, centres = kmeans(vecs, k, seed=seed)
        if len({tuple(sorted(c)) for c in ({a} for a in assign)}) < 2:
            continue
        score = silhouette(vecs, assign)
        if score > best[1]:
            best = (k, score, (assign, centres))
    return best


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------

def cluster_terms(docs, assign, cluster, top=8):
    """Terms most distinctive of this cluster versus the rest of the domain."""
    inside, outside = Counter(), Counter()
    n_in = n_out = 0
    for i, d in enumerate(docs):
        toks = set(tokenize(d))
        if assign[i] == cluster:
            inside.update(toks)
            n_in += 1
        else:
            outside.update(toks)
            n_out += 1
    if not n_in:
        return []
    scored = []
    for t, c in inside.items():
        if c < max(2, 0.15 * n_in):
            continue
        p_in = c / n_in
        p_out = (outside.get(t, 0) / n_out) if n_out else 0.0
        scored.append((p_in - p_out, t))
    scored.sort(reverse=True)
    return [t for _, t in scored[:top]]


def auto_label(terms):
    return ", ".join(terms[:4]) if terms else "unlabelled"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def run_domain(domain_id, records, args):
    docs = [doc_text(r) for r in records]
    n = len(docs)

    vecs, backend = (None, None)
    if not args.no_embeddings:
        vecs, backend = try_embeddings(docs)
    if vecs is None and not args.no_sklearn:
        vecs, backend = try_sklearn_svd(docs)
    if vecs is None:
        vecs, backend = tfidf_vectors(docs), "stdlib TF-IDF"

    kmax = args.max_topics or max(2, min(8, int(round(math.sqrt(n / 2.0)))))
    kmax = max(2, min(kmax, n - 1))
    kmin = min(2, kmax)

    if args.topics:
        k = max(2, min(args.topics, n - 1))
        assign, centres = kmeans(vecs, k, seed=args.seed)
        score = silhouette(vecs, assign)
    else:
        k, score, result = choose_k(vecs, kmin, kmax, args.seed)
        if result is None:
            return None
        assign, centres = result

    groups = defaultdict(list)
    for i, a in enumerate(assign):
        groups[a].append(i)

    topics = []
    for ci in sorted(groups, key=lambda c: -len(groups[c])):
        members = groups[ci]
        terms = cluster_terms(docs, assign, ci)
        exemplars = sorted(members, key=lambda i: -cosine(vecs[i], centres[ci]))[:3]
        topics.append({
            "topic_id": "%s_t%d" % (domain_id, len(topics) + 1),
            "members": members,
            "terms": terms,
            "exemplars": [records[i].get("title", "") for i in exemplars],
            "size": len(members),
        })
    return {"domain_id": domain_id, "backend": backend, "k": k,
            "silhouette": score, "topics": topics, "n": n}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--min-docs", type=int, default=12,
                    help="skip clustering a domain with fewer records than this")
    ap.add_argument("--topics", type=int, help="force this many topics per domain")
    ap.add_argument("--max-topics", type=int, help="upper bound when choosing k automatically")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-embeddings", action="store_true", help="skip sentence-transformers")
    ap.add_argument("--no-sklearn", action="store_true", help="skip the sklearn backend")
    ap.add_argument("--relabel-only", action="store_true",
                    help="do not re-cluster; just reapply edited topic_labels.csv")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    idlib.ensure_dirs(p["topics"])
    assign_path = os.path.join(p["topics"], "publication_topics.csv")
    labels_path = os.path.join(p["topics"], "topic_labels.csv")

    human_labels = {}
    for row in idlib.read_csv(labels_path):
        key = (row.get("domain_id", ""), row.get("topic_id", ""))
        human_labels[key] = row

    if args.relabel_only:
        rows = idlib.read_csv(assign_path)
        if not rows:
            raise SystemExit("Nothing to relabel: %s not found. Run without "
                             "--relabel-only first." % assign_path)
        changed = 0
        for r in rows:
            lab = human_labels.get((r.get("domain_id", ""), r.get("topic_id", "")))
            if lab and lab.get("topic_label") and lab["topic_label"] != r.get("topic_label"):
                r["topic_label"] = lab["topic_label"]
                changed += 1
        idlib.write_csv(assign_path, rows)
        print("Relabelled %d of %d assignment rows from %s" % (changed, len(rows), labels_path))
        print("Re-run build_dataset.py to fold the labels into publications.csv.")
        return 0

    records = idlib.read_jsonl(os.path.join(p["classification"], "classified.jsonl"))
    if not records:
        raise SystemExit("No classified records -- run classify.py first.")

    by_domain = OrderedDict()
    for r in records:
        by_domain.setdefault(r.get("primary_domain", "other_id"), []).append(r)

    assignments = []
    label_rows = []
    results = []
    skipped = []

    for domain_id, recs in by_domain.items():
        if len(recs) < args.min_docs:
            skipped.append((domain_id, len(recs)))
            for r in recs:
                assignments.append({
                    "uid": r["uid"], "domain_id": domain_id,
                    "topic_id": "%s_t0" % domain_id,
                    "topic_label": "(too few records to cluster)",
                    "topic_terms": "", "topic_size": len(recs),
                    "title": r.get("title", ""), "year": r.get("year", ""),
                })
            continue

        print("Clustering %s (%d records)..." % (domain_id, len(recs)))
        res = run_domain(domain_id, recs, args)
        if res is None:
            skipped.append((domain_id, len(recs)))
            continue
        results.append(res)
        print("  backend=%s  k=%d  silhouette=%.3f" % (res["backend"], res["k"], res["silhouette"]))

        for t in res["topics"]:
            key = (domain_id, t["topic_id"])
            human = human_labels.get(key, {})
            auto = auto_label(t["terms"])
            label = (human.get("topic_label") or "").strip() or auto
            is_human = bool((human.get("topic_label") or "").strip()) and label != auto
            label_rows.append({
                "domain_id": domain_id, "topic_id": t["topic_id"],
                "topic_label": label, "auto_label": auto,
                "top_terms": ", ".join(t["terms"]), "size": t["size"],
                "exemplar_title": t["exemplars"][0] if t["exemplars"] else "",
                "human_edited": int(is_human),
                "notes": human.get("notes", ""),
            })
            for i in t["members"]:
                r = recs[i]
                assignments.append({
                    "uid": r["uid"], "domain_id": domain_id, "topic_id": t["topic_id"],
                    "topic_label": label, "topic_terms": ", ".join(t["terms"]),
                    "topic_size": t["size"], "title": r.get("title", ""),
                    "year": r.get("year", ""),
                })

    idlib.write_csv(assign_path, assignments,
                    ["uid", "domain_id", "topic_id", "topic_label", "topic_terms",
                     "topic_size", "title", "year"])
    idlib.write_csv(labels_path, label_rows,
                    ["domain_id", "topic_id", "topic_label", "auto_label", "top_terms",
                     "size", "exemplar_title", "human_edited", "notes"])
    write_report(os.path.join(p["topics"], "topics_report.md"), results, skipped, args)

    print("")
    print("Topics written: %d assignments, %d topics across %d domain(s)"
          % (len(assignments), len(label_rows), len(results)))
    if skipped:
        print("Skipped (fewer than --min-docs=%d records): %s"
              % (args.min_docs, ", ".join("%s(%d)" % s for s in skipped)))
    print("")
    print("Next: read %s, replace each machine `topic_label` with a readable" % labels_path)
    print("sub-domain name, then run this script with --relabel-only and re-run")
    print("build_dataset.py.")
    return 0


def write_report(path, results, skipped, args):
    L = ["# Topic model report", ""]
    if not results:
        L.append("No domain had enough records to cluster (min-docs=%d)." % args.min_docs)
    for res in results:
        L.append("## %s — %d records, %d topics" % (res["domain_id"], res["n"], res["k"]))
        L.append("")
        L.append("Backend: `%s` · mean silhouette: %.3f" % (res["backend"], res["silhouette"]))
        if res["silhouette"] < 0.05:
            L.append("")
            L.append("> Silhouette is very low: these clusters barely separate. Treat them as")
            L.append("> provisional, and consider more records or a different `--topics`.")
        L.append("")
        for t in res["topics"]:
            L.append("### `%s` — %d records" % (t["topic_id"], t["size"]))
            L.append("")
            L.append("**Terms:** %s" % (", ".join(t["terms"]) or "(none distinctive)"))
            L.append("")
            L.append("**Exemplars:**")
            for ex in t["exemplars"]:
                L.append("- %s" % ex[:140])
            L.append("")
    if skipped:
        L.append("## Not clustered")
        L.append("")
        for d, n in skipped:
            L.append("- `%s`: %d record(s), below --min-docs=%d" % (d, n, args.min_docs))
    L.append("")
    L.append("## Labelling")
    L.append("")
    L.append("Machine terms are not a legend. Open `topic_labels.csv`, write a readable")
    L.append("sub-domain name in `topic_label` for each row, then run")
    L.append("`topic_model.py --relabel-only` and rebuild the dataset.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
