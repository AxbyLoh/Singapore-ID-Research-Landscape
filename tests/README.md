# Tests

## `make_fixture.py`

Generates a synthetic `raw/` directory matching the PubMed connector's response
shape, so the pipeline can be exercised without network or connector access.

Two records (PMIDs `42685738` and `41586636`) are **real**, copied verbatim from
the connector so the fixture stays honest about the schema. Every other record
is **synthetic**: PMIDs in the `99xxxxxx` range and DOIs under the invalid
`10.9999/` prefix, so a fixture row can never be mistaken for a real
publication. The synthetic authors and institutions are invented; do not quote
them as findings.

The fixture deliberately covers the awkward cases:

| Case | Expected outcome |
|---|---|
| Editorial | mechanical exclude (`EXC-TYP-01`) |
| French-language article | mechanical exclude (`EXC-TYP-03`) |
| 2010 and 2027 publications | mechanical exclude (`EXC-TYP-04`, window) |
| No Singapore link at all | mechanical exclude (`EXC-GEO-01`) |
| Industry regional office only | uncertain (`EXC-GEO-02`) |
| Singapore in text, no SG affiliation | uncertain (`INC-GEO-02` vs `EXC-GEO-01`) |
| Letter | uncertain — never auto-excluded |
| Case report | uncertain (`EXC-TYP-02`) |
| No abstract | uncertain (`EXC-GEN-03`) |
| Hepatitis B (no domain match) | uncertain, then `other_id` |
| Same DOI from two queries | deduplicated, provenance unioned |
| Scholar hit matching a PubMed title | merged, PubMed metadata wins |
| Scholar-only hit | kept, flagged `needs_manual_metadata` |
| TB/HIV co-infection | two domains (`tb`, `sti`) |
| Ventilator-associated pneumonia | two domains (`rti`, `amr_hai`) |
| Influenza vaccine effectiveness | `research_types` includes `Vaccine` |

Sub-domain is derived from MeSH-term frequency, not predefined, so the fixture
doesn't assert specific labels (e.g. "Dengue") for specific records — the
actual assignment depends on which MeSH terms repeat across a domain's other
included records, and is genuinely different at the default
`--subdomain-min-records 3` (most of the tiny fixture's domains have too few
records to produce any vocabulary) versus the `--subdomain-min-records 1`
`run_pipeline_test.sh` uses to exercise the algorithm meaningfully. What the
tests assert instead: every non-"Other/unspecified" `primary_subdomain_mesh`
is a term the record's own `mesh_terms` actually contains; no stoplisted term
(e.g. "Singapore", "Humans") ever appears as a sub-domain; and a hand-edited
`display_label` in `subdomain_vocabulary.csv` survives a re-run of
`classify.py`.

## `run_pipeline_test.sh`

End-to-end smoke test: builds the fixture, runs every stage, and asserts the
expected counts and invariants. Run it after changing any script, and after
editing `screening-criteria.md` or `domain-taxonomy.md` — a malformed json
block in either is the most common way to break the pipeline.

```bash
bash tests/run_pipeline_test.sh
```

Covers, in addition to the table above: the MeSH-frequency sub-domain
derivation (stoplist filtering, per-domain scoping, deterministic ranking,
hand-edited `display_label` persistence across a re-run) and research-type
classification (multi-label), the domain-scoped author collaboration network
(`network_author_*`, split by `domain` plus an `ALL` aggregate),
`summary_top_authors.csv` / `summary_subdomain_year.csv` /
`summary_research_type_year.csv` referential integrity, and the topic
**map** (not a bar chart): every placed record's `map_x`/`map_y` sits inside
`[0,1]`, and — the actual point of a map — every record is checked to be
closer to its own cluster's centroid than to any other cluster's centroid in
the same domain, i.e. the layout genuinely groups similar records rather than
just producing arbitrary coordinates. The map layout is also checked
deterministic across an identical re-run, same as the co-authorship networks.

`topic_model.py` always attempts BERTopic first (unless `--no-bertopic`), so
the test also exercises its fail-clean-and-fall-through path: if BERTopic
isn't installed, or is installed but can't reach huggingface.co for its
embedding model (the common case in a network-restricted sandbox), the run
still succeeds on the next backend down and the map invariants above still
hold, whichever backend actually ran.

It writes to `runs/fixture-test/` and cleans up on success.
