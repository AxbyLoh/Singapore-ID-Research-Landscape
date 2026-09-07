---
name: singapore-id-research-landscape
description: Build and refresh a screened, categorised dataset of infectious disease research publications from Singapore. Searches PubMed/MEDLINE, Google Scholar and the CDA Directory of Experts roster; screens titles/abstracts against maintained inclusion/exclusion criteria; categorises into the five ID domains (vector-borne, STI, TB, respiratory tract infection, AMR/HAI); labels co-authorship, institutions and countries for Tableau network and map visualisations; and runs topic modelling to surface sub-domains. Use for requests about the Singapore ID research landscape, ID bibliometrics or co-authorship/collaboration mapping, screening ID literature, refreshing the expert directory, or building a Tableau-ready publication dataset.
---

# Singapore Infectious Disease Research Landscape

Turns a literature search into a screened, labelled, Tableau-ready dataset of
Singapore infectious disease (ID) research.

Pipeline: **preflight → search → ingest → screen → classify → dataset → topic model.**

The three things a human owns and edits directly:

| File | What it controls |
|---|---|
| `reference/screening-criteria.md` | Inclusion/exclusion rules, and the amendment log |
| `data/directory_of_experts.csv` | The CDA expert roster searched by name |
| `reference/domain-taxonomy.md` | The 5 domains and their term/MeSH definitions |

Never hardcode criteria, expert names, or domain terms into a script or into
your own reasoning. Read them from these files every run, so a human edit
changes behaviour on the next run.

## Ground rules

- **Never invent a publication, author, affiliation, PMID or DOI.** Every row in
  the output must trace to a record actually returned by a search tool. If a
  field is absent, leave it empty — do not infer it.
- **Attribute PubMed.** When you present PubMed-derived results in chat, say the
  data came from PubMed and give DOI links for articles you cite individually.
- **Screening decisions are auditable.** Every include/exclude carries a reason
  and the rule ID that drove it. Never silently drop a record.
- Work happens in a run directory (default `runs/<YYYY-MM-DD>/`); the skill
  folder's `data/` and `reference/` files are inputs, not scratch space.

## Step 0 — Preflight (always run first)

Do not start searching until the environment is confirmed. Run:

```bash
python3 .claude/skills/singapore-id-research-landscape/scripts/preflight.py --run-dir runs/<YYYY-MM-DD>
```

It checks Python, optional packages, the run directory, and whether the
expert roster and criteria files are populated. It **cannot** see your MCP
connectors, so you must check those yourself:

1. **PubMed connector.** Confirm you actually have `PubMed` tools available
   (`search_articles`, `get_article_metadata`, `get_full_text_article`,
   `find_related_articles`, `convert_article_ids`). Do not assume — if they are
   not in your tool list, stop and tell the user to enable the PubMed connector,
   then re-check. Read `reference/setup.md` for the exact instructions to give them.
2. **Web search** for Google Scholar coverage. If unavailable, say so and
   continue with PubMed/MEDLINE only, recording the gap in the run manifest.
3. **Python.** Preflight reports the version and which optional libraries are
   present. Everything works on the standard library alone; `scikit-learn` and
   `sentence-transformers` only improve topic modelling quality.

Report the preflight result to the user in a few lines before proceeding. If a
required piece is missing, stop and ask — do not silently degrade.

## Step 1 — Build the search strategy

Read `reference/search-strategy.md` and `reference/domain-taxonomy.md`, then:

```bash
python3 .../scripts/build_queries.py --run-dir runs/<DATE> --from-year 2015 --to-year <YEAR>
```

This emits `<run-dir>/queries.json` with three query families:

- **`geography`** — Singapore-affiliated ID work, per domain.
- **`experts`** — one author query per person in `data/directory_of_experts.csv`,
  built from their name variants and disambiguated by Singapore affiliation.
- **`scholar`** — plain-text queries for Google Scholar / web search, which has
  no field tags.

Check the expert roster is fresh first. If `data/directory_of_experts.csv` is
empty or the user asks to refresh it, see **Refreshing the expert directory** below.

## Step 2 — Search and capture raw results

You are the search engine here — the scripts do not have network access to
PubMed. For each query in `queries.json`:

1. Call `PubMed:search_articles` with the query, `date_from`/`date_to`, and
   `max_results` (page with `retstart` while `has_more` is true; cap per
   `search-strategy.md`).
2. Call `PubMed:get_article_metadata` on the returned PMIDs in batches of ~50.
3. Write each metadata response verbatim to
   `<run-dir>/raw/pubmed_<query_id>_<n>.json`. Do not edit or summarise it —
   `ingest.py` parses the connector's native shape.

For Google Scholar, use web search restricted to `scholar.google.com` and record
hits as JSON lines in `<run-dir>/raw/scholar_<query_id>.jsonl` with keys
`title`, `authors_raw`, `year`, `venue`, `url`, `snippet`, `source: "scholar"`.
Scholar hits are **leads, not records**: resolve each to a PMID via
`PubMed:search_articles` on its title where possible, and only keep it as a
Scholar-only record when it has no PubMed equivalent (flag it
`needs_manual_metadata`).

MEDLINE is reached through the same PubMed connector; restrict to it with
`AND medline[sb]` when the user asks for MEDLINE-indexed records specifically.

Then normalise and deduplicate:

```bash
python3 .../scripts/ingest.py --run-dir runs/<DATE>
```

Produces `<run-dir>/records.jsonl` (one normalised record per publication,
deduplicated on DOI → PMID → normalised title) and `<run-dir>/ingest_report.md`.

## Step 3 — Screen on title and abstract

Read `reference/screening-criteria.md` in full before screening. Then run the
deterministic pre-screen, which applies only the mechanical rules (language,
year, article type, obvious geography):

```bash
python3 .../scripts/screen.py --run-dir runs/<DATE>
```

It partitions records into `auto_include`, `auto_exclude` and **`uncertain`**,
writing `<run-dir>/screening/*.jsonl`. Records it cannot decide mechanically are
left for you — that is the point.

For each record in `uncertain.jsonl`, judge it against the criteria file. Then:

- **Confident include/exclude** → append your decision to
  `<run-dir>/screening/decisions.jsonl` as
  `{"uid", "decision", "rule_id", "reason", "decided_by": "agent"}`.
- **Not confident → get more evidence first.** If the record has a PMC ID, call
  `PubMed:get_full_text_article` and re-judge on the methods and setting, not
  just the abstract. Record `"evidence": "full_text"`.
- **Still not confident → ask the user.** Batch the open questions (up to 4 at a
  time) with `AskUserQuestion`. Give the title, journal, year, the Singapore
  link, and exactly what is ambiguous. Never guess to avoid asking.

**Then close the loop — this is required, not optional.** After the user answers,
amend `reference/screening-criteria.md`:

1. Add or refine the rule in the relevant criteria section so the same case
   decides itself next time.
2. Append an entry to the **Amendment log** at the bottom of that file: date,
   the record that prompted it, the user's ruling, and the rule ID added.
3. Re-run `screen.py`. It reapplies the updated file to every record, so an
   amendment retroactively fixes earlier look-alikes.

Never edit the criteria file to match a decision you made alone — only a user
ruling, or an explicit request, justifies an amendment.

## Step 4 — Classify domains and parse affiliations

```bash
python3 .../scripts/classify.py --run-dir runs/<DATE>
```

Assigns each included record to one or more of the five domains using the
weighted terms and MeSH mappings in `reference/domain-taxonomy.md`, and parses
every author affiliation string into institution and country using
`data/institution_aliases.csv`.

Two things need your judgement afterwards:

- `<run-dir>/classification/unassigned.jsonl` — records no domain claimed.
  Read title/abstract/MeSH and either assign a domain, mark `other_id`, or add
  the missing term to `domain-taxonomy.md` (preferred, if it generalises).
- `<run-dir>/classification/unmapped_affiliations.csv` — affiliation strings
  whose institution or country could not be resolved, ordered by frequency.
  Add real mappings to `data/institution_aliases.csv`. Resolve the frequent ones
  before building the dataset; an unmapped institution is a missing node in the
  network viz.

Re-run `classify.py` after editing either file.

## Step 5 — Build the Tableau-ready dataset

```bash
python3 .../scripts/build_dataset.py --run-dir runs/<DATE>
```

Writes `<run-dir>/dataset/` — the publication fact table plus the long author,
institution, country and co-authorship edge tables, and pre-laid-out network
tables Tableau can draw directly. `reference/dataset-schema.md` documents every
column and gives the field/mark setup for each chart type. Read it before
advising the user on the Tableau side.

## Step 6 — Topic model the sub-domains

```bash
python3 .../scripts/topic_model.py --run-dir runs/<DATE> --min-docs 12
```

Clusters records **within each domain** by semantic similarity of title +
abstract + keywords, so sub-domains are domain-specific. It uses
`sentence-transformers` embeddings if installed, else TF-IDF + SVD, else a
pure-standard-library TF-IDF; the method used is recorded in the output.

Cluster labels come out as top distinguishing terms. Improve them: read
`<run-dir>/topics/topics_report.md` for each cluster's terms and exemplar
titles, write a readable sub-domain name into the `topic_label` column of
`<run-dir>/topics/topic_labels.csv`, then:

```bash
python3 .../scripts/topic_model.py --run-dir runs/<DATE> --relabel-only
python3 .../scripts/build_dataset.py --run-dir runs/<DATE>
```

`--relabel-only` reapplies the edited labels without re-clustering, so topic
ids stay stable; a full re-run also preserves your labels. Machine terms alone
make a poor legend — check the silhouette score in the report before trusting
any cluster.

## Step 7 — Report

Summarise for the user: counts at each pipeline stage, screening decisions
(including what you asked about and how the criteria changed), domain
distribution, top institutions/countries, the sub-domains found, and any known
gaps. `<run-dir>/manifest.json` records the run's parameters and file inventory
for reproducibility.

Offer — do not assume — to publish the summary as an artifact if the user wants
something shareable.

## Refreshing the expert directory

`data/directory_of_experts.csv` is a plain CSV kept separate so it can be
updated without touching the skill. To refresh from the CDA site:

```bash
python3 .../scripts/fetch_experts.py --out .../data/directory_of_experts.csv
```

It walks the paginated listing and each expert's profile page. If the site is
unreachable from your environment (blocked egress is common), say so plainly and
offer the alternatives: the user pastes the page HTML into a file for
`--from-html`, or adds rows to the CSV by hand. **Never fabricate roster
entries** — an invented expert silently poisons every downstream search and
network. The script never overwrites existing rows it did not fetch; it merges
on `profile_url` and preserves manual edits and the `notes` column.

## Adding a new domain

Add a section to `reference/domain-taxonomy.md` following the existing shape
(terms with weights, MeSH terms, exclusions). Every script reads the taxonomy at
runtime, so no code change is needed.
