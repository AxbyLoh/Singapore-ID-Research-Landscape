---
name: singapore-id-research-landscape
description: Build and refresh a screened, categorised dataset of infectious disease research publications from Singapore. Searches PubMed/MEDLINE, Google Scholar and the CDA Directory of Experts roster; screens titles/abstracts against maintained inclusion/exclusion criteria; categorises into the five ID domains (vector-borne, STI, TB, respiratory tract infection, AMR/HAI) plus data-derived named sub-domains within each (the corpus's own most frequent MeSH terms per domain, e.g. Dengue, Malaria) and cross-cutting research types (Genomics, Surveillance, Clinical studies, ...); labels co-authorship, institutions and countries for Tableau network, donut and bar-chart visualisations; and runs topic modelling as a QA check on sub-domain coverage. Use for requests about the Singapore ID research landscape, ID bibliometrics or co-authorship/collaboration mapping, screening ID literature, refreshing the expert directory, or building a Tableau-ready publication dataset.
---

# Singapore Infectious Disease Research Landscape

Turns a literature search into a screened, labelled, Tableau-ready dataset of
Singapore infectious disease (ID) research.

Pipeline: **preflight → search → ingest → screen → classify → dataset → topic model.**

The files a human owns and edits directly:

| File | What it controls |
|---|---|
| `reference/screening-criteria.md` | Inclusion/exclusion rules, and the amendment log |
| `data/directory_of_experts.csv` | The CDA expert roster searched by name |
| `reference/domain-taxonomy.md` | The 5 domains and their term/MeSH definitions |
| `data/mesh_stoplist.csv` | Generic/demographic MeSH terms excluded when deriving sub-domains |
| `reference/research-type-taxonomy.md` | Cross-cutting research-type tags (bar chart) |

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

## Step 4 — Classify domains, sub-domains, research types and affiliations

```bash
python3 .../scripts/classify.py --run-dir runs/<DATE>
# tune sub-domain granularity for small or exploratory corpora:
python3 .../scripts/classify.py --run-dir runs/<DATE> --subdomain-top-k 12 --subdomain-min-records 3
```

Assigns each included record to:

- one or more of the **5 domains**, from `reference/domain-taxonomy.md`;
- a **sub-domain within its primary domain, derived from the corpus's own
  MeSH-term frequency** — not a predefined list. For each domain, `classify.py`
  counts how often each MeSH heading appears across that domain's own included
  records (excluding generic/demographic noise via `data/mesh_stoplist.csv`),
  keeps the headings that appear on at least `--subdomain-min-records` records
  (default 3), takes the top `--subdomain-top-k` (default 12) by frequency, and
  assigns each record's `primary_subdomain` to its own highest-ranked matching
  heading. The chosen vocabulary is written to
  `<run-dir>/classification/subdomain_vocabulary.csv` for this run — it is a
  genuine output of this corpus, not something read from a file you'd edit in
  advance;
- zero or more **research types** (Genomics, Clinical studies, Surveillance
  and epidemiology, …), from `reference/research-type-taxonomy.md` — a
  cross-cutting, multi-label tag orthogonal to domain;

and parses every author affiliation string into institution and country using
`data/institution_aliases.csv`.

Things that need your judgement afterwards:

- `<run-dir>/classification/unassigned.jsonl` — records no domain claimed.
  Read title/abstract/MeSH and either assign a domain, mark `other_id`, or add
  the missing term to `domain-taxonomy.md` (preferred, if it generalises).
- `<run-dir>/classification/subdomain_vocabulary.csv` — the sub-domains this
  run actually found, one row per `(domain, mesh_term)`, with `frequency` and
  `rank`. **You can rename how a chart-ready sub-domain displays** by editing
  its `display_label` column (e.g. "Tuberculosis, Multidrug-Resistant" →
  "Multidrug-resistant TB") — re-running `classify.py` preserves any label you
  changed, for any term that still qualifies. You cannot add a sub-domain that
  isn't in the data; if you expect one and it's missing, the underlying MeSH
  term isn't common enough in this corpus yet — lower `--subdomain-min-records`
  or gather more records.
- `<run-dir>/classification/unassigned_subdomain.jsonl` — records with no
  sub-domain match. This means either their domain had too few records to
  clear the threshold, or this record's own MeSH terms simply aren't common in
  its domain — not a taxonomy gap to fill in by hand. If a whole domain comes
  back mostly unspecified, lower `--subdomain-min-records` and re-run.
- `<run-dir>/classification/unassigned_research_type.jsonl` — records matching
  no research type. A recurring theme here is a genuine gap in
  `research-type-taxonomy.md` — add the term and re-run.
- `<run-dir>/classification/unmapped_affiliations.csv` — affiliation strings
  whose institution or country could not be resolved, ordered by frequency.
  Add real mappings to `data/institution_aliases.csv`. Resolve the frequent ones
  before building the dataset; an unmapped institution is a missing node in the
  network viz.

Re-run `classify.py` after editing any of these files.

## Step 5 — Build the Tableau-ready dataset

```bash
python3 .../scripts/build_dataset.py --run-dir runs/<DATE>
```

Writes `<run-dir>/dataset/` — the publication fact table plus the long author,
institution, country and co-authorship edge tables, and pre-laid-out network
tables Tableau can draw directly. `reference/dataset-schema.md` documents every
column and gives the field/mark setup for each chart type. Read it before
advising the user on the Tableau side.

## Step 6 — Topic model, as a second opinion on sub-domain coverage

```bash
python3 .../scripts/topic_model.py --run-dir runs/<DATE> --min-docs 12
```

This is **not** what feeds the sub-domain donut chart — `primary_subdomain`
from Step 4 does that, derived directly from the corpus's own MeSH-term
frequency. Topic modelling instead clusters records **within each domain** by
unsupervised semantic similarity over free text (title/abstract/keywords), a
different signal from MeSH headings, and — this is the point of the step —
lays them out as a **2D map, not a bar chart of cluster sizes**: records
pulled together by many strong similarity links sit close together, records
without such links drift apart, so the spatial layout itself *is* the
clustering, not decoration on top of a count.

Four backends, best first, whichever is actually usable: **BERTopic**
(sentence-transformers + HDBSCAN + c-TF-IDF — opt-in and heavy, several GB,
`pip install bertopic` yourself, never auto-installed; needs network access
to huggingface.co at run time to download its embedding model, so it fails
cleanly and falls through in a network-restricted sandbox) → plain
`sentence-transformers` embeddings (same network caveat) → scikit-learn
TF-IDF+SVD (local, no network) → pure-standard-library TF-IDF (always works).
The run reports which one actually ran, and why a higher tier fell through if
one did. Pass `--no-bertopic` to skip straight past tier 1 even when
installed.

Use it as a cross-check on Step 4: if a visually tight cluster on the map all
landed in "Other/unspecified" or scored low, that's a sign either the theme's
MeSH indexing is sparse/inconsistent in this corpus, or
`--subdomain-min-records`/`--subdomain-top-k` are too strict — not something
to fix by hand-adding a taxonomy entry, since there is no taxonomy file to add
one to.

Read `<run-dir>/topics/topics_report.md` alongside
`<run-dir>/classification/subdomain_vocabulary.csv` for this comparison. The
map coordinates themselves are in `<run-dir>/topics/publication_topics.csv`
(`map_x`/`map_y` per record) and `<run-dir>/topics/topic_centroids.csv`
(one label position per cluster) — plot both together as a scatter with
label text at the centroids (Recipe 10), never as a bar chart.

If you still want readable cluster labels for the map and the supplementary
`topic_id`/`topic_label` fields, write them into
`<run-dir>/topics/topic_labels.csv` and re-apply:

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
`--from-html`, or gives you a CSV export of the directory (a manual copy is
common when live fetching is blocked) for `--from-csv path.csv` — it maps
common header spellings (Full Title & Name, Academic Title, Expert Name,
Institution/Organization, Research Domains) automatically; add an entry to
`CSV_COLUMN_ALIASES` in the script if a real export uses different headers.
Adding rows to the CSV by hand is the last resort. **Never fabricate roster
entries** — an invented expert silently poisons every downstream search and
network. The script never overwrites existing rows it did not fetch; it merges
on `profile_url` and preserves manual edits and the `notes` column.

## Adding a new domain or research type; tuning sub-domains

Domain and research-type taxonomies are read at runtime, so adding a block is
a data edit, never a code change:

- **New domain** — add a section to `reference/domain-taxonomy.md` (terms with
  weights, MeSH terms, exclusions), following the existing shape. Its
  sub-domains need no separate edit — `classify.py` will derive them from that
  domain's own records' MeSH frequency on the next run, once it has enough
  included records to clear `--subdomain-min-records`.
- **New research type** — add a `json` block to
  `reference/research-type-taxonomy.md`. Triggered by a recurring theme in
  `unassigned_research_type.jsonl`.

Sub-domains have **no taxonomy file to edit** — they come from the data. If a
sub-domain seems wrong, too coarse, too sparse, or missing, the levers are:

- **Rename how it displays** — edit `display_label` in this run's
  `classification/subdomain_vocabulary.csv` and re-run `classify.py`.
- **Get more/fewer sub-domains per domain** — adjust `--subdomain-top-k`.
- **Include less-common MeSH terms** — lower `--subdomain-min-records`
  (useful for a small or exploratory corpus; the production default is 3).
- **Stop a generic MeSH heading from crowding out real sub-domains** — add it
  to `data/mesh_stoplist.csv`. Only do this for headings that don't name a
  pathogen or theme (demographics, study design, bare geography) — never to
  suppress a real finding you'd rather not see.

After any edit, re-run `classify.py` then `build_dataset.py`.
