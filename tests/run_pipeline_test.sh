#!/usr/bin/env bash
# End-to-end smoke test for the singapore-id-research-landscape skill.
# Runs every pipeline stage against the fixture and asserts key invariants.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SK="$ROOT/.claude/skills/singapore-id-research-landscape"
RUN="$ROOT/runs/fixture-test"
FAILED=0

pass() { printf '  [ok]   %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; FAILED=$((FAILED+1)); }

check() { # check <description> <actual> <expected>
  if [ "$2" = "$3" ]; then pass "$1 ($2)"; else fail "$1: got '$2', expected '$3'"; fi
}

jl_count() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }
csv_rows() { [ -f "$1" ] && python3 -c "import csv,sys;print(sum(1 for _ in csv.DictReader(open(sys.argv[1]))))" "$1" || echo 0; }

echo "== setup =="
rm -rf "$RUN"
python3 "$ROOT/tests/make_fixture.py" --run-dir "$RUN" >/dev/null || { echo "fixture failed"; exit 1; }
pass "fixture built"

echo "== preflight =="
python3 "$SK/scripts/preflight.py" --run-dir "$RUN" >/dev/null 2>&1
check "preflight exit code" "$?" "0"

echo "== reference files parse =="
python3 - "$SK" <<'PY'
import sys, os
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import idlib
d = idlib.load_taxonomy(); r = idlib.load_mechanical_rules()
assert len(d) == 5, "expected 5 domains, got %d" % len(d)
assert {x["domain_id"] for x in d} == {"vector_borne","sti","tb","rti","amr_hai"}
assert len(r) >= 4, "expected >=4 mechanical rules"
stoplist = idlib.load_mesh_stoplist()
assert len(stoplist) >= 30, "expected a substantial MeSH stoplist, got %d" % len(stoplist)
assert "humans" in stoplist and "singapore" in stoplist, "stoplist missing expected generic terms"
assert "dengue" not in stoplist, "stoplist must not contain disease-specific content"
types = idlib.load_research_type_taxonomy()
assert len(types) == 16, "expected 16 research types, got %d" % len(types)
print("ok")
PY
check "taxonomy + criteria + mesh-stoplist + research-type parse" "$?" "0"

echo "== build_queries =="
python3 "$SK/scripts/build_queries.py" --run-dir "$RUN" --from-year 2015 --to-year 2026 >/dev/null
check "build_queries exit code" "$?" "0"
NQ=$(python3 -c "import json;print(len(json.load(open('$RUN/queries.json'))['queries']))")
if [ "$NQ" -ge 9 ]; then pass "queries generated ($NQ)"; else fail "too few queries: $NQ"; fi

echo "== ingest =="
python3 "$SK/scripts/ingest.py" --run-dir "$RUN" >/dev/null
check "ingest exit code" "$?" "0"
check "unique records after dedupe" "$(jl_count "$RUN/records.jsonl")" "23"

echo "== screen (mechanical only) =="
python3 "$SK/scripts/screen.py" --run-dir "$RUN" --from-year 2015 --to-year 2026 >/dev/null
check "auto-included"  "$(jl_count "$RUN/screening/included.jsonl")"  "11"
check "auto-excluded"  "$(jl_count "$RUN/screening/excluded.jsonl")"  "5"
check "uncertain"      "$(jl_count "$RUN/screening/uncertain.jsonl")" "7"

echo "== screen (with decisions) =="
cat > "$RUN/screening/decisions.jsonl" <<'DEC'
{"uid":"doi:10.1080/21645515.2025.2593730","decision":"exclude","rule_id":"EXC-GEO-02","reason":"industry branch office only","decided_by":"user"}
{"uid":"doi:10.9999/fixture.99000055","decision":"include","rule_id":"INC-TOP-01","reason":"hepatitis B serosurvey is ID research","decided_by":"agent"}
{"uid":"doi:10.9999/fixture.99000052","decision":"include","rule_id":"INC-TOP-01","reason":"full text shows a case series","decided_by":"agent","evidence":"full_text"}
{"uid":"doi:10.9999/fixture.99000057","decision":"exclude","rule_id":"EXC-TYP-02","reason":"single-patient case report","decided_by":"agent"}
{"uid":"doi:10.9999/fixture.99000054","decision":"include","rule_id":"INC-TYP-01","reason":"letter with original data","decided_by":"agent"}
{"uid":"doi:10.9999/fixture.99000053","decision":"exclude","rule_id":"EXC-GEO-01","reason":"Singapore is only a comparator","decided_by":"user"}
DEC
python3 "$SK/scripts/screen.py" --run-dir "$RUN" --from-year 2015 --to-year 2026 >/dev/null
check "included after decisions"  "$(jl_count "$RUN/screening/included.jsonl")"  "14"
check "uncertain after decisions" "$(jl_count "$RUN/screening/uncertain.jsonl")" "1"

echo "== classify =="
# --subdomain-min-records 1: the fixture's domains have only 2-4 records each,
# so the production default (3) would leave almost everything unspecified.
python3 "$SK/scripts/classify.py" --run-dir "$RUN" --subdomain-top-k 12 --subdomain-min-records 1 >/dev/null
check "classify exit code" "$?" "0"
check "classified records" "$(jl_count "$RUN/classification/classified.jsonl")" "14"
python3 - "$RUN" <<'PY'
import csv, json, sys
run = sys.argv[1]
recs = [json.loads(l) for l in open(run + "/classification/classified.jsonl")]
tbhiv = next(r for r in recs if "HIV-tuberculosis" in r["title"])
assert set(tbhiv["domains"]) == {"tb", "sti"}, "TB/HIV domains: %s" % tbhiv["domains"]
vap = next(r for r in recs if "Ventilator-associated" in r["title"])
assert set(vap["domains"]) == {"rti", "amr_hai"}, "VAP domains: %s" % vap["domains"]
hep = next(r for r in recs if "Hepatitis B" in r["title"])
assert hep["domains"] == ["other_id"], "hepatitis should be other_id: %s" % hep["domains"]
assert all(r["primary_domain"] for r in recs), "every record needs a primary_domain"
sg = [r for r in recs if r["singapore_led"]]
assert len(sg) >= 10, "expected most fixture records Singapore-led, got %d" % len(sg)

# Sub-domain is derived from the corpus's own MeSH terms, not a predefined list,
# so we check the ALGORITHM's invariants rather than hardcoding disease names.
STOP = {"singapore", "humans", "cross infection", "vaccines"}
for r in recs:
    assert "primary_subdomain" in r and r["primary_subdomain"], \
        "every record needs a non-empty primary_subdomain: %s" % r["uid"]
    own_mesh_lower = {(m or "").strip().lower() for m in (r.get("mesh_terms") or [])}
    if r["primary_subdomain"] != "Other/unspecified":
        # the chosen term must be one the record itself actually carries
        assert (r.get("primary_subdomain_mesh") or "").lower() in own_mesh_lower, \
            "primary_subdomain_mesh %r not among %s's own mesh_terms" % (
                r.get("primary_subdomain_mesh"), r["uid"])
    for t in r.get("subdomains") or []:
        assert t.lower() not in STOP, "stoplisted term %r leaked into subdomains" % t

vocab = list(csv.DictReader(open(run + "/classification/subdomain_vocabulary.csv")))
for row in vocab:
    assert row["mesh_term"].lower() not in STOP, \
        "stoplisted term %r leaked into subdomain_vocabulary.csv" % row["mesh_term"]
    assert int(row["frequency"]) >= 1

influenza = next(r for r in recs if "Influenza vaccine effectiveness" in r["title"])
assert "Vaccine" in influenza["research_type_labels"], "influenza research types: %s" % influenza["research_type_labels"]
assert all("research_type_labels" in r for r in recs), "every record needs a research_type_labels list"
print("ok")
PY
check "domain/subdomain/research-type assignment invariants" "$?" "0"

echo "== subdomain relabel persists across re-run =="
RELABEL_TARGET=$(python3 - "$RUN" <<'PY'
import csv, sys
path = sys.argv[1] + "/classification/subdomain_vocabulary.csv"
rows = list(csv.DictReader(open(path)))
fn = list(rows[0].keys())
target = rows[0]["mesh_term"]
for r in rows:
    if r["mesh_term"] == target:
        r["display_label"] = "TEST-RELABELED-%s" % target
w = csv.DictWriter(open(path, "w", newline=""), fieldnames=fn)
w.writeheader(); w.writerows(rows)
print(target)
PY
)
python3 "$SK/scripts/classify.py" --run-dir "$RUN" --subdomain-top-k 12 --subdomain-min-records 1 >/dev/null
python3 - "$RUN" "$RELABEL_TARGET" <<'PY'
import csv, sys
run, target = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(run + "/classification/subdomain_vocabulary.csv")))
row = next(r for r in rows if r["mesh_term"] == target)
assert row["display_label"] == "TEST-RELABELED-%s" % target, \
    "hand-edited display_label was not preserved across re-run: %r" % row["display_label"]
print("ok")
PY
check "hand-edited subdomain label survives re-run" "$?" "0"

echo "== topic model =="
python3 "$SK/scripts/topic_model.py" --run-dir "$RUN" --min-docs 3 >/dev/null 2>&1
check "topic_model exit code" "$?" "0"
if [ -f "$RUN/topics/publication_topics.csv" ]; then pass "topic assignments written"; else fail "no topic assignments"; fi
if [ -f "$RUN/topics/topic_centroids.csv" ]; then pass "topic centroids written"; else fail "no topic centroids"; fi

python3 - "$RUN" <<'PY'
import csv, math, sys
run = sys.argv[1]
rows = list(csv.DictReader(open(run + "/topics/publication_topics.csv")))
placed = [r for r in rows if r["map_x"] and r["map_y"]]
assert placed, "expected at least one record with map coordinates"
for r in placed:
    x, y = float(r["map_x"]), float(r["map_y"])
    assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0, "map coordinate out of [0,1] range: %r" % r

# clustered records should be spatially close: pick a cluster with >=2 placed
# members and check they're each closer to their own centroid than to a
# different cluster's centroid in the same domain (the actual point of a map).
centroids = {(r["domain_id"], r["topic_id"]): (float(r["x"]), float(r["y"]))
             for r in csv.DictReader(open(run + "/topics/topic_centroids.csv")) if r["x"]}
by_topic = {}
for r in placed:
    by_topic.setdefault((r["domain_id"], r["topic_id"]), []).append(r)
checked = 0
for (dom, tid), members in by_topic.items():
    other_centroids = [xy for (d2, t2), xy in centroids.items() if d2 == dom and t2 != tid]
    if not other_centroids or (dom, tid) not in centroids:
        continue
    own = centroids[(dom, tid)]
    for r in members:
        x, y = float(r["map_x"]), float(r["map_y"])
        d_own = math.hypot(x - own[0], y - own[1])
        d_other_min = min(math.hypot(x - ox, y - oy) for ox, oy in other_centroids)
        assert d_own <= d_other_min + 1e-9, (
            "record %s sits closer to another cluster's centroid than its own "
            "(own=%.3f, nearest other=%.3f) -- map is not clustering" % (r["uid"], d_own, d_other_min))
        checked += 1
assert checked > 0, "no multi-cluster domain available to check spatial separation"
print("ok (%d records checked for own-cluster proximity)" % checked)
PY
check "topic map spatially separates clusters" "$?" "0"

echo "== build_dataset =="
python3 "$SK/scripts/build_dataset.py" --run-dir "$RUN" >/dev/null
check "build_dataset exit code" "$?" "0"
check "publications.csv rows" "$(csv_rows "$RUN/dataset/publications.csv")" "14"
for f in publications publication_domains publication_subdomains publication_research_types \
         publication_authors publication_institutions publication_countries \
         coauthor_institution_edges coauthor_author_edges network_institution_nodes \
         network_institution_paths network_author_nodes network_author_paths \
         summary_top_authors summary_by_domain_year summary_subdomain_year \
         summary_research_type_year topic_map_centroids; do
  if [ -s "$RUN/dataset/$f.csv" ]; then pass "$f.csv present"; else fail "$f.csv missing/empty"; fi
done

echo "== dataset invariants =="
python3 - "$RUN" <<'PY'
import csv, collections, sys
d = sys.argv[1] + "/dataset/"
rd = lambda f: list(csv.DictReader(open(d + f)))

pubs = rd("publications.csv")
uids = [p["uid"] for p in pubs]
assert len(uids) == len(set(uids)), "publications.csv has duplicate uids"

known = set(uids)
for f in ("publication_domains.csv", "publication_subdomains.csv",
          "publication_research_types.csv", "publication_authors.csv",
          "publication_institutions.csv", "publication_countries.csv"):
    for r in rd(f):
        assert r["uid"] in known, "%s references unknown uid %s" % (f, r["uid"])

subdom = rd("publication_subdomains.csv")
prim_sd = [r for r in subdom if r["is_primary"] == "1"]
assert len(prim_sd) == len(pubs), \
    "exactly one primary subdomain row per publication, got %d for %d pubs" % (len(prim_sd), len(pubs))

edges = rd("coauthor_institution_edges.csv")
ids = [e["edge_id"] for e in edges]
assert len(ids) == len(set(ids)), "duplicate edge_id in coauthor_institution_edges.csv"
for e in edges:
    assert e["source"] < e["target"], "edge not alphabetically ordered: %s" % e["edge_id"]
    assert int(e["weight"]) >= 1

paths = rd("network_institution_paths.csv")
per = collections.Counter(p["edge_id"] for p in paths)
assert per and max(per.values()) == 2, "every path edge must have exactly 2 rows"
assert min(per.values()) == 2, "an edge is missing an endpoint row"
assert "ALL" in {p["domain"] for p in paths}, "missing the ALL aggregate layer"
nodes = {n["node_id"] for n in rd("network_institution_nodes.csv")}
for p in paths:
    assert p["node_id"] in nodes, "path references node %s not in node table" % p["node_id"]
    assert 0.0 <= float(p["x"]) <= 1.0 and 0.0 <= float(p["y"]) <= 1.0, "coords out of range"

dom = rd("publication_domains.csv")
prim = [r for r in dom if r["is_primary"] == "1"]
assert len(prim) == len(pubs), "exactly one primary domain row per publication"

# author network: same shape checks as institution, plus edges split by domain
anodes = {n["node_id"] for n in rd("network_author_nodes.csv")}
apaths = rd("network_author_paths.csv")
aper = collections.Counter(p["edge_id"] for p in apaths)
assert aper and max(aper.values()) == 2 and min(aper.values()) == 2, \
    "every author path edge must have exactly 2 rows"
assert "ALL" in {p["domain"] for p in apaths}, "author network missing the ALL aggregate layer"
for p in apaths:
    assert p["node_id"] in anodes, "author path references unknown node %s" % p["node_id"]
    assert 0.0 <= float(p["x"]) <= 1.0 and 0.0 <= float(p["y"]) <= 1.0

aedges = rd("coauthor_author_edges.csv")
aeids = [e["edge_id"] for e in aedges]
assert len(aeids) == len(set(aeids)), "duplicate edge_id in coauthor_author_edges.csv"
assert {e["domain"] for e in aedges} <= (
    {"vector_borne","sti","tb","rti","amr_hai","other_id"}), "unexpected author edge domain"

# summary_top_authors: ALL-domain n_publications must equal node table's n_publications
top = rd("summary_top_authors.csv")
top_all = {r["author_key"]: int(r["n_publications"]) for r in top if r["domain_id"] == "ALL"}
node_pubs = {n["node_id"]: int(n["n_publications"]) for n in rd("network_author_nodes.csv")}
mismatches = [k for k, v in node_pubs.items() if top_all.get(k) != v]
assert not mismatches, "author node n_publications disagrees with summary_top_authors ALL: %s" % mismatches
assert any(r["domain_id"] == "vector_borne" for r in top), "expected a vector_borne row in top authors"

subsum = rd("summary_subdomain_year.csv")
assert any(r["domain_id"] == "vector_borne" for r in subsum), \
    "expected at least one vector_borne row in summary_subdomain_year.csv"
assert any(r["subdomain_label"].startswith("TEST-RELABELED-") for r in subsum), \
    "the hand-edited display label should have propagated into summary_subdomain_year.csv"
subdom_ranked = [r for r in subdom if r["is_primary"] == "1" and r["vocabulary_rank"]]
assert subdom_ranked, "expected at least one primary subdomain row with a vocabulary_rank"
assert all(int(r["vocabulary_rank"]) >= 1 for r in subdom_ranked)

typesum = rd("summary_research_type_year.csv")
assert any(r["type_label"] == "Vaccine" for r in typesum), \
    "expected a Vaccine row in summary_research_type_year.csv"
print("ok")
PY
check "dataset referential integrity" "$?" "0"

echo "== determinism =="
cp "$RUN/dataset/network_institution_nodes.csv" "$RUN/nodes_first.csv"
python3 "$SK/scripts/build_dataset.py" --run-dir "$RUN" >/dev/null
if diff -q "$RUN/nodes_first.csv" "$RUN/dataset/network_institution_nodes.csv" >/dev/null; then
  pass "network layout is deterministic"
else
  fail "network layout changed between identical runs"
fi

cp "$RUN/topics/publication_topics.csv" "$RUN/topics_first.csv"
python3 "$SK/scripts/topic_model.py" --run-dir "$RUN" --min-docs 3 >/dev/null 2>&1
if diff -q "$RUN/topics_first.csv" "$RUN/topics/publication_topics.csv" >/dev/null; then
  pass "topic map layout is deterministic"
else
  fail "topic map coordinates changed between identical runs"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  rm -rf "$RUN"
  exit 0
else
  echo "$FAILED CHECK(S) FAILED -- run dir kept at $RUN"
  exit 1
fi
