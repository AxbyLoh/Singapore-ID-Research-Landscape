#!/usr/bin/env python3
"""Cluster records WITHIN each domain by semantic similarity, and lay them out
as a 2D topic MAP -- not a bar chart -- so that similar topics sit near each
other and dissimilar ones sit apart, the way a document/cluster landscape
should read.

Backends, best first -- whichever is installed is used, and the choice is
recorded in the output:

  1. sentence-transformers embeddings  (best: true semantic similarity)
  2. scikit-learn TF-IDF + TruncatedSVD (good: latent semantic space)
  3. pure standard-library TF-IDF       (always available; lexical only)

The map itself is a k-nearest-neighbour similarity graph (each record linked
to its most similar records in the same domain) laid out with the same
deterministic force-directed layout used for the co-authorship networks
(idlib.force_layout): records pulled together by many strong similarity
edges cluster spatially; records with few edges to a group drift away from
it. This is a lightweight, dependency-free stand-in for a UMAP/t-SNE plot,
not a size-ranked bar chart of cluster counts.

Writes <run-dir>/topics/:
  publication_topics.csv   uid -> topic_id, topic_label, topic_terms, map_x, map_y
  topic_centroids.csv      one row per topic: its label, top terms, size,
                            and (x, y) -- the mean position of its members,
                            for placing a text label on the map
  topic_labels.csv         EDITABLE: rewrite topic_label, then --relabel-only
  topics_report.md         cluster sizes, terms, exemplar titles

Clustering (and the map) run per domain, so a topic is always a sub-domain of
one of the five domains rather than a cross-cutting theme, and coordinates
from different domains are not comparable to each other -- always filter a
map view to one domain.
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
# Topic map (2D layout by similarity, NOT a bar chart)
# --------------------------------------------------------------------------

def similarity_knn_edges(vecs, k_neighbors):
    """Undirected k-NN graph over document vectors: each doc linked to its
    most similar other docs (cosine > 0), for force_layout to cluster on.
    """
    n = len(vecs)
    edges = {}
    for i in range(n):
        sims = []
        for j in range(n):
            if i == j:
                continue
            s = cosine(vecs[i], vecs[j])
            if s > 0:
                sims.append((s, j))
        sims.sort(reverse=True)
        for s, j in sims[:k_neighbors]:
            key = (i, j) if i < j else (j, i)
            if key not in edges or s > edges[key]:
                edges[key] = s
    return [(a, b, w) for (a, b), w in edges.items()]


def stratified_sample(assign, cap, seed):
    """Deterministic, cluster-proportional sample of doc indices, so a large
    domain's map still shows every cluster rather than truncating arbitrarily.
    """
    n = len(assign)
    if n <= cap:
        return list(range(n))
    groups = defaultdict(list)
    for i, a in enumerate(assign):
        groups[a].append(i)
    rng = random.Random(seed)
    keep = []
    remaining = cap
    for gi, (cluster, members) in enumerate(sorted(groups.items())):
        share = max(1, round(cap * len(members) / n))
        share = min(share, len(members), remaining - (len(groups) - gi - 1))
        share = max(share, 1)
        keep.extend(sorted(rng.sample(members, min(share, len(members)))))
        remaining -= share
    return sorted(set(keep))[:cap]


def layout_topic_map(vecs, assign, k_neighbors, max_docs, seed):
    """{doc_index: (x, y)} for docs actually placed on the map (up to
    max_docs, stratified by cluster if the domain is larger than that).
    """
    idx = stratified_sample(assign, max_docs, seed)
    if len(idx) < 2:
        return {i: (0.5, 0.5) for i in idx}
    sub_vecs = [vecs[i] for i in idx]
    edges = similarity_knn_edges(sub_vecs, k_neighbors)
    # force_layout works on arbitrary node ids; use local positions 0..len(idx)-1
    local_edges = edges  # already (local_i, local_j, w) since sub_vecs is 0-indexed
    pos = idlib.force_layout(list(range(len(idx))), local_edges, seed=seed)
    return {idx[local_i]: xy for local_i, xy in pos.items()}


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

    xy = layout_topic_map(vecs, assign, args.map_neighbors, args.map_max_docs, args.seed)

    topics = []
    for ci in sorted(groups, key=lambda c: -len(groups[c])):
        members = groups[ci]
        terms = cluster_terms(docs, assign, ci)
        exemplars = sorted(members, key=lambda i: -cosine(vecs[i], centres[ci]))[:3]
        placed = [i for i in members if i in xy]
        if placed:
            cx = sum(xy[i][0] for i in placed) / len(placed)
            cy = sum(xy[i][1] for i in placed) / len(placed)
        else:
            cx = cy = None
        topics.append({
            "topic_id": "%s_t%d" % (domain_id, len(topics) + 1),
            "members": members,
            "terms": terms,
            "exemplars": [records[i].get("title", "") for i in exemplars],
            "size": len(members),
            "centroid_xy": (cx, cy),
        })
    return {"domain_id": domain_id, "backend": backend, "k": k,
            "silhouette": score, "topics": topics, "n": n, "xy": xy,
            "map_placed": len(xy), "map_total": n}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--min-docs", type=int, default=12,
                    help="skip clustering a domain with fewer records than this")
    ap.add_argument("--topics", type=int, help="force this many topics per domain")
    ap.add_argument("--max-topics", type=int, help="upper bound when choosing k automatically")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--map-neighbors", type=int, default=8,
                    help="k-NN graph size for the topic map layout: how many "
                         "similar records each record links to")
    ap.add_argument("--map-max-docs", type=int, default=300,
                    help="cap on records laid out per domain (O(n^2) similarity "
                         "+ layout cost); large domains are stratified-sampled "
                         "by cluster so every cluster still appears on the map")
    ap.add_argument("--no-embeddings", action="store_true", help="skip sentence-transformers")
    ap.add_argument("--no-sklearn", action="store_true", help="skip the sklearn backend")
    ap.add_argument("--relabel-only", action="store_true",
                    help="do not re-cluster; just reapply edited topic_labels.csv")
    args = ap.parse_args()

    p = idlib.run_paths(args.run_dir)
    idlib.ensure_dirs(p["topics"])
    assign_path = os.path.join(p["topics"], "publication_topics.csv")
    labels_path = os.path.join(p["topics"], "topic_labels.csv")
    centroids_path = os.path.join(p["topics"], "topic_centroids.csv")

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
    centroid_rows = []
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
                    "map_x": "", "map_y": "",
                })
            continue

        print("Clustering %s (%d records)..." % (domain_id, len(recs)))
        res = run_domain(domain_id, recs, args)
        if res is None:
            skipped.append((domain_id, len(recs)))
            continue
        results.append(res)
        print("  backend=%s  k=%d  silhouette=%.3f  map: %d/%d records placed"
              % (res["backend"], res["k"], res["silhouette"], res["map_placed"], res["map_total"]))

        for t in res["topics"]:
            key = (domain_id, t["topic_id"])
            human = human_labels.get(key, {})
            auto = auto_label(t["terms"])
            label = (human.get("topic_label") or "").strip() or auto
            is_human = bool((human.get("topic_label") or "").strip()) and label != auto
            cx, cy = t["centroid_xy"]
            label_rows.append({
                "domain_id": domain_id, "topic_id": t["topic_id"],
                "topic_label": label, "auto_label": auto,
                "top_terms": ", ".join(t["terms"]), "size": t["size"],
                "exemplar_title": t["exemplars"][0] if t["exemplars"] else "",
                "human_edited": int(is_human),
                "notes": human.get("notes", ""),
            })
            centroid_rows.append({
                "domain_id": domain_id, "topic_id": t["topic_id"],
                "topic_label": label, "top_terms": ", ".join(t["terms"]),
                "size": t["size"], "x": round(cx, 6) if cx is not None else "",
                "y": round(cy, 6) if cy is not None else "",
            })
            for i in t["members"]:
                r = recs[i]
                x, y = res["xy"].get(i, (None, None))
                assignments.append({
                    "uid": r["uid"], "domain_id": domain_id, "topic_id": t["topic_id"],
                    "topic_label": label, "topic_terms": ", ".join(t["terms"]),
                    "topic_size": t["size"], "title": r.get("title", ""),
                    "year": r.get("year", ""),
                    "map_x": round(x, 6) if x is not None else "",
                    "map_y": round(y, 6) if y is not None else "",
                })

    idlib.write_csv(assign_path, assignments,
                    ["uid", "domain_id", "topic_id", "topic_label", "topic_terms",
                     "topic_size", "title", "year", "map_x", "map_y"])
    idlib.write_csv(labels_path, label_rows,
                    ["domain_id", "topic_id", "topic_label", "auto_label", "top_terms",
                     "size", "exemplar_title", "human_edited", "notes"])
    idlib.write_csv(centroids_path, centroid_rows,
                    ["domain_id", "topic_id", "topic_label", "top_terms", "size", "x", "y"])
    write_report(os.path.join(p["topics"], "topics_report.md"), results, skipped, args)

    print("")
    print("Topics written: %d assignments, %d topics across %d domain(s)"
          % (len(assignments), len(label_rows), len(results)))
    if skipped:
        print("Skipped (fewer than --min-docs=%d records): %s"
              % (args.min_docs, ", ".join("%s(%d)" % s for s in skipped)))
    print("")
    print("  -> %s (map_x/map_y for a scatter map)" % assign_path)
    print("  -> %s (cluster label positions for the map)" % centroids_path)
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
        L.append("Backend: `%s` · mean silhouette: %.3f · map: %d/%d records placed"
                 % (res["backend"], res["silhouette"], res["map_placed"], res["map_total"]))
        if res["map_placed"] < res["map_total"]:
            L.append("")
            L.append("> This domain exceeds `--map-max-docs` (%d); the map shows a "
                     "cluster-proportional sample so every cluster is still visible. "
                     "Cluster assignments themselves used all %d records."
                     % (args.map_max_docs, res["map_total"]))
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
    L.append("## The map")
    L.append("")
    L.append("`publication_topics.csv` carries `map_x`/`map_y` per record and")
    L.append("`topic_centroids.csv` carries a label position per cluster -- plot both")
    L.append("as a scatter (records) with cluster-label text overlaid (centroids), never")
    L.append("as a bar chart of cluster sizes. Coordinates come from a k-NN similarity")
    L.append("graph over the domain's own records, laid out with the same deterministic")
    L.append("force-directed layout used for the co-authorship networks -- records with")
    L.append("many strong similarity links pull together, so the map's spatial layout")
    L.append("*is* the clustering, not a decoration on top of it. Coordinates are")
    L.append("domain-local: never compare or overlay two domains' maps on the same axes.")
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
