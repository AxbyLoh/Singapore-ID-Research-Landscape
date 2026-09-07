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
print("ok")
PY
check "taxonomy + criteria parse" "$?" "0"

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
python3 "$SK/scripts/classify.py" --run-dir "$RUN" >/dev/null
check "classify exit code" "$?" "0"
check "classified records" "$(jl_count "$RUN/classification/classified.jsonl")" "14"
python3 - "$RUN" <<'PY'
import json, sys
recs = [json.loads(l) for l in open(sys.argv[1] + "/classification/classified.jsonl")]
by_title = {r["title"][:40]: r for r in recs}
tbhiv = next(r for r in recs if "HIV-tuberculosis" in r["title"])
assert set(tbhiv["domains"]) == {"tb", "sti"}, "TB/HIV domains: %s" % tbhiv["domains"]
vap = next(r for r in recs if "Ventilator-associated" in r["title"])
assert set(vap["domains"]) == {"rti", "amr_hai"}, "VAP domains: %s" % vap["domains"]
hep = next(r for r in recs if "Hepatitis B" in r["title"])
assert hep["domains"] == ["other_id"], "hepatitis should be other_id: %s" % hep["domains"]
assert all(r["primary_domain"] for r in recs), "every record needs a primary_domain"
sg = [r for r in recs if r["singapore_led"]]
assert len(sg) >= 10, "expected most fixture records Singapore-led, got %d" % len(sg)
print("ok")
PY
check "domain assignment invariants" "$?" "0"

echo "== topic model =="
python3 "$SK/scripts/topic_model.py" --run-dir "$RUN" --min-docs 3 >/dev/null 2>&1
check "topic_model exit code" "$?" "0"
if [ -f "$RUN/topics/publication_topics.csv" ]; then pass "topic assignments written"; else fail "no topic assignments"; fi

echo "== build_dataset =="
python3 "$SK/scripts/build_dataset.py" --run-dir "$RUN" >/dev/null
check "build_dataset exit code" "$?" "0"
check "publications.csv rows" "$(csv_rows "$RUN/dataset/publications.csv")" "14"
for f in publications publication_domains publication_authors publication_institutions \
         publication_countries coauthor_institution_edges network_institution_nodes \
         network_institution_paths summary_by_domain_year; do
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
for f in ("publication_domains.csv", "publication_authors.csv",
          "publication_institutions.csv", "publication_countries.csv"):
    for r in rd(f):
        assert r["uid"] in known, "%s references unknown uid %s" % (f, r["uid"])

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

echo
if [ "$FAILED" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  rm -rf "$RUN"
  exit 0
else
  echo "$FAILED CHECK(S) FAILED -- run dir kept at $RUN"
  exit 1
fi
