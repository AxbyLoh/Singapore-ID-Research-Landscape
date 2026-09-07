# Dataset schema and Tableau recipes

Everything `build_dataset.py` writes to `<run-dir>/dataset/`, what each column
means, and how to build the standard research-landscape views from it.

---

## The counting rule (read this first)

`publications.csv` has exactly one row per publication. Every other table is
**long** — a publication with three countries appears three times in
`publication_countries.csv`, and a publication in two domains appears twice in
`publication_domains.csv`.

So in Tableau, the measure for "how many publications" is always
**`COUNTD([uid])`**, never `SUM(1)` and never `Number of Records`. Using a row
count on a long table silently multiplies collaborative papers, which is the
single easiest way to produce a wrong chart from this dataset.

---

## `publications.csv` — the fact table

One row per publication. Join everything else to it on `uid`.

| Column | Type | Meaning |
|---|---|---|
| `uid` | string | Stable key: `doi:…`, else `pmid:…`, else `title:…` |
| `pmid`, `pmc`, `doi`, `url` | string | Identifiers; blank when absent |
| `title` | string | Article title |
| `journal`, `journal_abbrev` | string | Journal name and ISO abbreviation |
| `year` | string | Publication year — use as a dimension, or cast to date via `pub_date` |
| `pub_date` | date | `YYYY-MM-DD`, padded to the 1st when month/day are missing |
| `language` | string | 3-letter code (`eng`) |
| `article_types` | pipe-list | PubMed publication types |
| `n_authors`, `n_institutions`, `n_countries` | int | Collaboration size measures |
| `primary_domain` | string | Highest-scoring domain id |
| `primary_domain_label` | string | Human-readable domain name |
| `domains` | pipe-list | **All** assigned domains |
| `is_multi_domain` | 0/1 | More than one domain assigned |
| `singapore_led` | 0/1 | First **or** last author is Singapore-affiliated |
| `is_international` | 0/1 | More than one country among affiliations |
| `first_author`, `last_author` | string | `Surname, Forename` |
| `first_author_country`, `last_author_country` | string | Leadership geography |
| `sg_institutions` | pipe-list | Singapore institutions on the paper |
| `countries`, `institutions` | pipe-list | All resolved, deduped |
| `topic_id`, `topic_label`, `topic_terms` | string | Sub-domain from `topic_model.py`; blank until it has run |
| `screening_decision` | string | `include` (all rows here are includes) |
| `screening_decided_by` | string | `mechanical`, `agent` or `user` |
| `screening_rules` | pipe-list | Rule IDs that fired |
| `screening_flags` | pipe-list | `regional_participation`, `industry_regional_office`, `scholar_only` |
| `sources` | pipe-list | `pubmed`, `scholar` |
| `query_ids` | pipe-list | Which searches found it — provenance |
| `needs_manual_metadata` | 0/1 | Scholar-only record with thin metadata |

**Filter you almost always want:** `needs_manual_metadata = 0` for any view
involving authors, institutions or countries. Scholar-only records have no
reliable affiliations and will distort every network and map.

---

## Long tables

### `publication_domains.csv` — publication × domain
`uid`, `domain_id`, `domain_label`, `is_primary`, `domain_score`, `year`, `singapore_led`

Use for domain breakdowns. `is_primary = 1` gives a mutually exclusive view
(each publication once); leaving it unfiltered gives the overlapping view where
a TB/HIV paper counts in both domains. **Say which one a chart uses** — the two
give different totals and the difference is real, not an error.

### `publication_authors.csv` — publication × author
`uid`, `author_key`, `author_name`, `position`, `is_first`, `is_last`,
`institution`, `country`, `sector`, `n_affiliations`, `year`, `primary_domain`

`institution`/`country` here are the author's *first resolved* affiliation. For
authors with several affiliations use the affiliation table instead.

> **`author_key` caveat.** PubMed has no universal author identifier, so
> `author_key` is `surname-firstinitial`. It merges distinct people who share
> both — common with Singapore surnames (`tan-w`, `lim-s`). Author-level
> numbers are indicative, not exact. Where a roster row carries an ORCID,
> prefer it. Never present an author-level ranking as authoritative without
> saying this.

### `publication_author_affiliations.csv` — publication × author × affiliation
Adds `affiliation_raw`, `institution_short`, `iso3`, `region`, `resolved`.
The full-fidelity table: use it to audit resolution quality
(`resolved = 0` rows are what `data/institution_aliases.csv` is still missing).

### `publication_institutions.csv` / `publication_countries.csv`
Deduped per publication, with `n_authors_here`, `is_singapore`, `region`,
`iso3`, `year`, `primary_domain`. These are the tables for institution
rankings and choropleth maps.

---

## Edge and network tables

### `coauthor_institution_edges.csv`, `coauthor_country_edges.csv`
`edge_id`, `pair_id`, `source`, `target`, `domain`, `weight`,
`source_country`, `target_country`, `source_region`, `target_region`,
`is_cross_border`, `involves_singapore`

Undirected pairs, alphabetically ordered, **split by `domain`**. `weight` is the
number of co-publications. Sum `weight` across domains for the overall figure,
or filter to one domain.

### `coauthor_author_edges.csv`
Author pairs with names, institutions and countries. Subject to the
`author_key` caveat above.

### `network_*_nodes.csv` and `network_*_paths.csv`
Pre-laid-out graphs, so Tableau can draw a network without a layout extension.

`network_institution_nodes.csv`: `node_id`, `label`, `country`, `region`,
`sector`, `iso3`, `is_singapore`, `x`, `y`, `degree`, `weighted_degree`,
`n_publications`.

`network_institution_paths.csv`: two rows per edge (`path_order` 1 and 2), each
carrying that endpoint's `x`/`y`, plus `edge_id`, `pair_id`, `domain`,
`weight`, `source`, `target`.

Coordinates come from a deterministic force-directed layout, so the same data
always yields the same picture. The node tables are capped at
`--max-network-nodes` (default 150) by weighted degree; the edge CSVs are
never capped.

**`domain` includes a special value `ALL`** — one path per pair with weights
summed across domains. Always apply a `domain` filter to a network view: with
no filter you draw the per-domain lines *and* the `ALL` lines on top of each
other.

---

## Tableau recipes

### 1. Co-authorship network (institutions)

1. Connect to `network_institution_paths.csv`; add `network_institution_nodes.csv`
   as a second source if you want node marks styled separately.
2. `x` → Columns, `y` → Rows. Set both to **Dimension** and **Continuous** (right-click → Dimension, then Continuous). If you leave them as measures Tableau aggregates them to a single point.
3. Mark type **Line**.
4. `edge_id` → Detail. `path_order` → Path.
5. `weight` → Size. `is_cross_border` or `domain` → Colour.
6. **Filter `domain`** to one value (or `ALL`).
7. For node circles: duplicate `y` on Rows, set the second axis to mark type
   **Circle** with `node_id` on Detail and `n_publications` on Size, then
   dual-axis and synchronise.
8. Hide both axes and the gridlines — the coordinates are arbitrary layout
   space, not data.

### 2. Country collaboration map
`publication_countries.csv`. `country` → Detail, set its geographic role to
Country/Region. `COUNTD([uid])` → Colour for a choropleth. Filter
`is_singapore = 0` to show *partner* countries rather than the near-universal
Singapore.

For collaboration flows, use `coauthor_country_edges.csv` with
`involves_singapore = 1` and draw lines between country centroids.

### 3. Domain trend over time
`publication_domains.csv`. `year` → Columns, `COUNTD([uid])` → Rows,
`domain_label` → Colour. Area chart for share-of-output, line chart for volume.
Decide and state whether `is_primary = 1` is applied.

### 4. Top institutions
`publication_institutions.csv`. `institution` → Rows sorted by
`COUNTD([uid])` descending, `sector` → Colour. Filter `is_singapore = 1` for
the domestic view, `= 0` for the international-partner view.

### 5. Sub-domain treemap
`publications.csv` (after `topic_model.py` and a rebuild).
`primary_domain_label` then `topic_label` → Detail, `COUNTD([uid])` → Size,
`primary_domain_label` → Colour. Filter out
`topic_label = "(too few records to cluster)"`.

### 6. Singapore-led vs participating
`publications.csv`. `singapore_led` → Colour on a `year` × `COUNTD([uid])` bar
chart. Cross-reference `screening_flags` containing `regional_participation`.

---

## Known limitations to state alongside any published view

1. **Author disambiguation** is surname + first initial (see caveat above).
2. **Institution resolution** is alias-based. Anything not in
   `data/institution_aliases.csv` resolves to blank and drops out of the
   institution network — check `unmapped_affiliations.csv` before publishing.
3. **PubMed lists affiliations per author** but historically only for the first
   author on older records, so pre-2014 collaboration networks are sparser than
   reality.
4. **Scholar-only records** carry no affiliations (`needs_manual_metadata = 1`).
5. **Domain overlap** is intentional; totals across domains exceed the
   publication count.
6. **Topic clusters** are unsupervised and only as good as the corpus size —
   check the silhouette score in `topics_report.md` before trusting them.
