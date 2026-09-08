# Search strategy

Three query families, run in this order. `build_queries.py` generates them from
this file plus `domain-taxonomy.md` and `directory_of_experts.csv`; the fenced
`json` blocks below are read at runtime and are the place to tune recall.

| Family | Source | What it catches | What it misses |
|---|---|---|---|
| `geography` | PubMed/MEDLINE | The bulk of Singapore ID output | Work by SG authors who listed an overseas address |
| `experts` | PubMed/MEDLINE | Named CDA directory researchers, including overseas-affiliated output | Anyone not on the roster |
| `scholar` | Google Scholar / web | Non-MEDLINE journals, local journals, reports, theses | Anything not indexed by Scholar |

Run all three. They overlap heavily by design — `ingest.py` deduplicates, and
the overlap is the recall check. If Scholar returns a lot that PubMed did not,
the PubMed hedges below need widening.

## Recall over precision

Screening removes false positives cheaply; a publication never retrieved is
invisible forever. Prefer a broad search and a strict screen. When you must
choose, widen.

## The Singapore filter

Applied to every `geography` query.

```json
{
  "block_id": "singapore_filter",
  "clauses": [
    "Singapore[Affiliation]",
    "Singapore[Title/Abstract]",
    "\"Singapore\"[MeSH Terms]"
  ],
  "join": "OR",
  "notes": "Affiliation catches SG-authored work; Title/Abstract and MeSH catch SG-setting work published by overseas teams (criteria INC-GEO-02)."
}
```

`Singapore[Affiliation]` alone is the highest-precision clause. The other two
raise recall and are the reason `EXC-GEO-01` (Singapore mentioned only in
passing) exists in the criteria.

## The infectious disease hedge

Used for the catch-all `geography` query that finds ID work outside the five
domains — the `other_id` bucket. Domain queries use `domain-taxonomy.md` terms
instead.

```json
{
  "block_id": "id_hedge",
  "clauses": [
    "\"Communicable Diseases\"[MeSH Terms]",
    "\"Infection\"[MeSH Terms]",
    "\"Infections\"[MeSH Terms]",
    "\"Virus Diseases\"[MeSH Terms]",
    "\"Bacterial Infections\"[MeSH Terms]",
    "\"Parasitic Diseases\"[MeSH Terms]",
    "\"Mycoses\"[MeSH Terms]",
    "\"Epidemics\"[MeSH Terms]",
    "\"Disease Outbreaks\"[MeSH Terms]",
    "\"Communicable Disease Control\"[MeSH Terms]",
    "\"Vaccines\"[MeSH Terms]",
    "\"Anti-Infective Agents\"[MeSH Terms]",
    "infectious disease*[Title/Abstract]",
    "communicable disease*[Title/Abstract]",
    "outbreak*[Title/Abstract]",
    "epidemic*[Title/Abstract]",
    "pathogen*[Title/Abstract]",
    "infection*[Title/Abstract]",
    "vaccin*[Title/Abstract]",
    "antimicrobial*[Title/Abstract]",
    "surveillance[Title/Abstract]"
  ],
  "join": "OR"
}
```

## Query construction

For each domain, `build_queries.py` takes the taxonomy terms of weight
`term_weight_floor` and above, plus all that domain's MeSH terms, ORs them, and
ANDs the Singapore filter:

```
( <domain terms OR'd> ) AND ( <singapore_filter OR'd> )
```

Date limits are **not** put in the query string — pass them as the connector's
`date_from` / `date_to` arguments so `EXC-TYP-04` and the query stay in sync.

```json
{
  "block_id": "build_options",
  "term_weight_floor": 3,
  "max_terms_per_query": 15,
  "max_results_per_query": 400,
  "page_size": 100,
  "medline_only_suffix": " AND medline[sb]",
  "notes": "Weight-3 terms only: weight-1 terms like 'outbreak' or 'mask' are context words that explode the result set when used for retrieval. They still count during classification. max_terms_per_query=15 keeps every generated query at or under ~17 boolean operators (n terms -> n-1 ORs, +2 ORs and +1 AND for the Singapore filter): the PubMed MCP connector used by this skill enforces a hard cap of 20 operators per query, tighter than PubMed's own native limit -- confirmed empirically (a 47-operator query was rejected with INVALID_QUERY/'too many boolean operators'). Raise this only if you have confirmed your connector accepts more."
}
```

`max_terms_per_query` chunks an over-long domain into several queries
(`geo_<domain>_1`, `_2`, …); results are pooled at ingest. The same cap also
chunks the `id_hedge` block below (already 21 clauses on its own, over the
connector limit unchunked).

## Expert queries

One query per roster row, from `name_variants` (or `pubmed_author_query` when
the row supplies an explicit override, which always wins):

```
( "Wong HM"[Author] OR "Wong H"[Author] ) AND ( Singapore[Affiliation] OR ... )
```

The affiliation clause disambiguates common surnames. It also means an expert's
overseas-affiliated papers are missed — so for high-value or highly mobile
researchers, set `pubmed_author_query` on their row to a hand-tuned query
(an ORCID-based or institution-listing query) and drop the affiliation
constraint there.

**Verify before trusting.** Singapore surnames are heavily shared. Spot-check
each expert's first page of hits against their profile's research areas; when a
query is clearly pulling another person's work, narrow it via
`pubmed_author_query` and note it in the roster's `notes` column.

## Google Scholar

Scholar has no field tags and no API. Use web search restricted to
`scholar.google.com`, with plain-language queries:

```
Singapore dengue transmission epidemiology
Singapore antimicrobial resistance hospital surveillance
<expert full name> Singapore infectious disease
```

Treat Scholar hits as **leads**: resolve each to a PubMed record by searching
its title, and keep it as a Scholar-only record (flagged
`needs_manual_metadata`) only when PubMed genuinely has no equivalent. Scholar
metadata is too thin and too inconsistent for the affiliation and co-authorship
tables, so a Scholar-only record contributes to counts but is excluded from
network views until someone completes its metadata.

## MEDLINE

MEDLINE is a subset of PubMed, reached through the same connector. Append
`medline[sb]` when the user asks specifically for MEDLINE-indexed records.
Doing so drops ahead-of-print and PMC-only records, so it lowers recall —
use it only on request.

## Paging

`search_articles` returns `has_more`. Page with `retstart` in steps of
`page_size` until `has_more` is false or `max_results_per_query` is reached.
If a query hits the cap, say so in the run report — a capped query means the
dataset is incomplete, and the query should be split by year instead.

## Refreshing an existing dataset

For an update run, set `date_from` to the day after the previous run's
`date_to` and use `datetype: "edat"` rather than `pdat`. Entry date catches
records added to PubMed late, which publication date silently misses.
