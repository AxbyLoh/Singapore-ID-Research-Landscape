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
| Dengue transmission record | `primary_subdomain = "Dengue virus"` |
| Gonorrhoea AMR record | `primary_subdomain = "Gonorrhoea"` |
| Influenza vaccine effectiveness | `research_types` includes `Vaccine` |

## `run_pipeline_test.sh`

End-to-end smoke test: builds the fixture, runs every stage, and asserts the
expected counts and invariants. Run it after changing any script, and after
editing `screening-criteria.md` or `domain-taxonomy.md` — a malformed json
block in either is the most common way to break the pipeline.

```bash
bash tests/run_pipeline_test.sh
```

Covers, in addition to the table above: sub-domain and research-type
classification (scoped correctly to `primary_domain` for sub-domains,
multi-label for research types), the domain-scoped author collaboration
network (`network_author_*`, split by `domain` plus an `ALL` aggregate), and
`summary_top_authors.csv` / `summary_subdomain_year.csv` /
`summary_research_type_year.csv` referential integrity.

It writes to `runs/fixture-test/` and cleans up on success.
