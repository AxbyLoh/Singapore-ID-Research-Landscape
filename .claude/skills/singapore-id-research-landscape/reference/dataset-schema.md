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
| `primary_subdomain` | string | Sub-domain within `primary_domain` (e.g. "Dengue"): the record's own highest-ranked MeSH term among this run's top MeSH terms for that domain — **derived from the corpus, not a predefined list** (see below); mutually exclusive per domain, this is the donut chart's field |
| `primary_subdomain_mesh` | string | The raw MeSH heading behind `primary_subdomain`, before any display-label rename |
| `subdomains` | pipe-list | All qualifying MeSH terms the record carries, best-ranked first (raw headings) |
| `subdomain_labels` | pipe-list | Same list, with any hand-edited display labels applied |
| `research_types` | pipe-list | Cross-cutting "kind of research" tags (Genomics, Surveillance and epidemiology, …), from `reference/research-type-taxonomy.md` — multi-label, no primary |
| `n_research_types` | int | `len(research_types)` |
| `topic_id`, `topic_label`, `topic_terms` | string | **Unsupervised** cluster from `topic_model.py`, blank until it has run. A second opinion alongside `primary_subdomain`, from a different signal (free text, not MeSH) — see "Three classification axes" below |
| `topic_map_x`, `topic_map_y` | float | Position on the domain-local **topic map** — a 2D layout where semantically similar records sit close together (see "Topic map" below). Blank for records in a domain too small to cluster |
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

## Three classification axes

The dataset carries three independent classifications. Keep them straight —
they answer different questions and drive different charts:

| Axis | Question | Field | Cardinality | Source |
|---|---|---|---|---|
| **Domain** | Which of the 5 ID areas? | `primary_domain` / `domains` | Multi-label (TB/HIV → both) | `reference/domain-taxonomy.md`, curated |
| **Sub-domain** | Which named pathogen/theme within that domain? | `primary_subdomain` / `subdomains` | One primary, mutually exclusive per domain | **derived from this run's own MeSH-term frequency** — see below |
| **Research type** | What kind of research — method, not disease? | `research_types` | Multi-label, no primary | `reference/research-type-taxonomy.md`, curated |

Domain and research type are **curated term lists**, deliberately, so those
chart legends stay stable and meaningful run over run. **Sub-domain is
different: it is computed from the data, not predefined.** `classify.py`
counts how often each MeSH heading appears across a domain's own included
records (after excluding generic/demographic noise via
`data/mesh_stoplist.csv`), keeps the headings common enough to clear
`--subdomain-min-records`, takes the top `--subdomain-top-k` by frequency, and
assigns each record to its own best-ranked match. The chosen vocabulary for a
run is written to `classification/subdomain_vocabulary.csv` — read that file
to see exactly which MeSH terms this run's donut chart is built from, and
whether the corpus is big enough for the result to be meaningful. You can
rename how a chosen term displays (edit `display_label` there and re-run
`classify.py`), but you cannot make a term appear that isn't actually common
in the corpus, and that is the point.

`topic_model.py`'s unsupervised clusters (`topic_id`/`topic_label`,
`topic_map_x`/`topic_map_y`) are a fourth, *supplementary* field, built from a
different signal (free-text similarity, not MeSH headings). Use its report as
a second opinion — a theme it finds that MeSH indexing missed is a sign of
sparse/inconsistent MeSH tagging in that corner of the corpus, not something
to hand-add to a taxonomy file, since sub-domain has none. Don't build the
sub-domain donut chart from `topic_label` — it drifts between runs and its
cluster count changes with corpus size, exactly what a stable donut chart
needs to avoid.

## Topic map

`topic_model.py` also lays its clusters out as a **2D map**: each record gets
`topic_map_x`/`topic_map_y`, and each cluster gets a centroid position in
`topic_map_centroids.csv`. This is deliberately a scatter/cluster landscape,
not a bar chart of cluster sizes — the coordinates come from a k-NN
similarity graph over the domain's own records, laid out with the same
deterministic force-directed method used for the co-authorship networks
(`idlib.force_layout`), so records with many strong similarity links pull
together and records without them drift apart. **The spatial layout is the
finding** — a bar chart of "cluster 1 has 12 records, cluster 2 has 8" throws
away exactly the information a topic map exists to show: which topics sit
near each other and which are far apart. Plot it as Recipe 10 below, never as
a treemap or bar chart.

Coordinates are domain-local: a map is built independently per domain, so
`topic_map_x = 0.5` in `vector_borne` has no relationship to
`topic_map_x = 0.5` in `sti`. Always filter to one `primary_domain` before
plotting, exactly like the co-authorship networks' `domain` filter.

A domain whose record count exceeds `--map-max-docs` (default 300) gets a
cluster-proportional sample rather than every record, so the map stays
readable and every cluster still appears — check `topics_report.md` for
whether a domain was sampled.

---

## Long tables

### `publication_domains.csv` — publication × domain
`uid`, `domain_id`, `domain_label`, `is_primary`, `domain_score`, `year`, `singapore_led`

Use for domain breakdowns. `is_primary = 1` gives a mutually exclusive view
(each publication once); leaving it unfiltered gives the overlapping view where
a TB/HIV paper counts in both domains. **Say which one a chart uses** — the two
give different totals and the difference is real, not an error.

### `publication_subdomains.csv` — publication × sub-domain
`uid`, `domain_id`, `subdomain_id`, `subdomain_label`, `is_primary`,
`vocabulary_rank`, `year`

Scoped to the publication's `primary_domain` only — a paper's sub-domain is
always read within its main domain. `subdomain_id` is the raw MeSH heading;
`subdomain_label` is the same term with any hand-edited display label applied.
`vocabulary_rank` is that term's frequency rank within the domain for this run
(1 = most common) — blank for the `"other"` fallback row a record gets when
none of its MeSH terms cleared the domain's threshold. `is_primary = 1` is the
row that matches `publications.csv`'s `primary_subdomain`; this is the table
behind the "Sub-domains of X" donut chart (filter `domain_id` to one value and
`is_primary = 1`, then `COUNTD([uid])` by `subdomain_label`).

The full vocabulary for a run — every MeSH term that qualified per domain,
with its frequency and share of that domain — is in
`classification/subdomain_vocabulary.csv` (not part of `dataset/`, since it is
an audit/tuning file rather than a chart data source).

### `publication_research_types.csv` — publication × research type
`uid`, `type_id`, `type_label`, `type_score`, `year`, `primary_domain`

Multi-label, no `is_primary` — a publication legitimately carries several
research types. `COUNTD([uid])` by `type_label` sums above the total
publication count; that is expected and matches the reference "Types of
research" chart, which is a plain count per type, not a share of 100%.

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
Author pairs, **split by `domain`** (plus `ALL`, like the institution/country
edges), with `edge_id`, `pair_id`, `weight`, names, institutions, countries.
Subject to the `author_key` caveat above.

### `summary_top_authors.csv`
`domain_id`, `domain_label`, `author_key`, `author_name`, `institution`,
`country`, `n_publications`, `rank_in_domain`

One row per (domain, author), pre-ranked. `domain_id = "ALL"` gives the
cross-domain ranking. This is exactly the reference dashboard's "top 10
authors" list: filter `domain_id` to one value, sort by `rank_in_domain`, take
the top N. A parameter action on `author_key`, driven by a click on this
table, is how the reference "select an author to view their collaborations"
interaction is built (see Recipe 7).

### `network_*_nodes.csv` and `network_*_paths.csv`
Pre-laid-out graphs, so Tableau can draw a network without a layout extension.
Three families: `network_institution_*`, `network_country_*`, `network_author_*`.

`network_institution_nodes.csv` (and the author/country equivalents):
`node_id`, `label`, `country`, `region`, `sector`, `iso3`, `is_singapore`, `x`,
`y`, `degree`, `weighted_degree`, `n_publications`.

For the **author** network, `node_id` is `author_key`, `label` is the display
name, and `n_publications` is the author's total across *all* domains (the
same figure as `summary_top_authors.csv`'s `domain_id = "ALL"` row) — the
layout and node sizing stay stable as you switch the domain filter; only the
edges drawn (and the top-N ranking table) change.

`network_institution_paths.csv` (and the author/country equivalents): two rows
per edge (`path_order` 1 and 2), each carrying that endpoint's `x`/`y`, plus
`edge_id`, `pair_id`, `domain`, `weight`, `source`, `target`.

Coordinates come from a deterministic force-directed layout, so the same data
always yields the same picture. Institution/country node tables are capped at
`--max-network-nodes` (default 150), the author node table at
`--max-author-network-nodes` (default 250), both by weighted degree; the edge
CSVs are never capped.

**`domain` includes a special value `ALL`** — one path per pair with weights
summed across domains. Always apply a `domain` filter to a network view: with
no filter you draw the per-domain lines *and* the `ALL` lines on top of each
other.

---

## Tableau recipes

### 1. Author collaboration network with a top-N selector

This is the reference dashboard's flagship view: a domain-scoped author
network, nodes coloured/sized by publication count on a green→yellow→red
scale, with a ranked author list that filters the network on selection.

**The network:**
1. Connect to `network_author_paths.csv`.
2. `x` → Columns, `y` → Rows, both set to **Dimension** and **Continuous**
   (right-click each pill → Dimension, then Continuous — leaving them as
   aggregated Measures collapses the whole graph to one point).
3. Mark type **Line**. `edge_id` → Detail, `path_order` → Path.
4. `weight` → Size.
5. **Filter `domain`** to one value, e.g. `vector_borne` (never leave it open —
   see the `ALL` note above).
6. For node circles: duplicate `y` on Rows, set the second pane's mark type to
   **Circle**, put `node_id` on Detail and `n_publications` on both **Size**
   and **Colour**, then combine the two axes (right-click the second y-axis →
   Dual Axis) and Synchronize Axis.
7. On the circle mark's Colour shelf, edit the color legend to a 3-stop
   **stepped/sequential** palette matching the reference — green at the low
   end, yellow at the midpoint, red at the high end — with the legend's
   min/max set to your data's actual `n_publications` range (the reference
   dashboard runs 1 to 51; yours will differ by corpus size). Tableau's
   built-in "Orange-Blue Diverging" won't match; build a custom 3-color
   sequential palette instead (Edit Colors → enter hex stops).
8. Hide both axes and gridlines — the coordinates are layout space, not data.

**The top-N author list and select/deselect interaction:**
1. New sheet on `summary_top_authors.csv`: filter `domain_id` to the same
   domain as the network, filter `rank_in_domain <= 10`, sort ascending. Put
   `author_name` and `n_publications` as columns — this is the sidebar table.
2. Add a **dashboard**, place both sheets on it.
3. Add a **Filter action**: source sheet = the top-authors table, target
   sheet = the network (both node and edge pane), field `author_key` →
   matching `source`/`target` on the network's underlying data (a calculated
   field `[source] = [Selected Author] OR [target] = [Selected Author]` driving
   an edge-level filter is the usual way to highlight just that author's
   collaborations). Set "Clear selection" behaviour to **Show all values** —
   that reproduces "deselect the author to return to the original view."

### 2. Sub-domain donut chart

The reference "Sub-domains of X" chart. Its slices are `primary_subdomain`
values — MeSH terms this run's own corpus actually uses most, per domain, not
a fixed legend, so **the slice names can change between runs** as the corpus
grows. That is expected; check `classification/subdomain_vocabulary.csv` if a
slice looks unfamiliar. Use `summary_subdomain_year.csv` (pre-aggregated) or
`publication_subdomains.csv` with `is_primary = 1`.

1. Filter `domain_id` to one domain.
2. Mark type **Pie**.
3. `subdomain_label` → Colour and Label. `SUM([publications])` (from the
   summary table) or `COUNTD([uid])` (from the long table) → Angle.
4. Add a **Year filter** (Recipe 5) to the same dashboard so the donut updates
   per year, matching the reference layout.
5. Convert to a donut by layering a second pie mark of a fixed size at 0%
   transparency in the centre, or use a "Pie chart donut" template — purely
   cosmetic, no data implication.
6. If a slice's MeSH heading reads awkwardly for a chart legend (e.g.
   "Tuberculosis, Multidrug-Resistant"), rename it: edit `display_label` in
   `classification/subdomain_vocabulary.csv` and re-run `classify.py` then
   `build_dataset.py` — don't rename it by hand in Tableau, or the rename is
   lost on the next data refresh.

### 3. "Types of research" bar chart

`summary_research_type_year.csv` or `publication_research_types.csv`.

1. `type_label` → Rows, sorted by `SUM([publications])` / `COUNTD([uid])`
   descending. Horizontal bar (swap axes).
2. Filter by `year` (Recipe 5) to match the reference's per-year view.
3. Do **not** filter to `primary_domain` unless you want research types within
   one domain only — the reference chart appears to be corpus-wide; state
   which scope you used.

### 4. Country collaboration map
`publication_countries.csv`. `country` → Detail, set its geographic role to
Country/Region. `COUNTD([uid])` → Colour for a choropleth. Filter
`is_singapore = 0` to show *partner* countries rather than the near-universal
Singapore.

For collaboration flows, use `coauthor_country_edges.csv` with
`involves_singapore = 1` and draw lines between country centroids.

### 5. Year filter as single-select buttons

The reference dashboard uses a row of year buttons (2015…2025), not a range
slider. In Tableau: put `year` on a filter shelf, right-click the filter card
→ **Single Value (List)**, then in "Customize" set it to display as buttons
rather than a dropdown. Apply the same filter (or a linked one via a filter
action) across every sheet on the dashboard so one click updates the donut,
the bar chart and any trend view together.

### 6. Domain trend over time
`publication_domains.csv`. `year` → Columns, `COUNTD([uid])` → Rows,
`domain_label` → Colour. Area chart for share-of-output, line chart for volume.
Decide and state whether `is_primary = 1` is applied.

### 7. Top institutions
`publication_institutions.csv`. `institution` → Rows sorted by
`COUNTD([uid])` descending, `sector` → Colour. Filter `is_singapore = 1` for
the domestic view, `= 0` for the international-partner view.

### 8. Institution/country collaboration network
Same construction as Recipe 1, but on `network_institution_paths.csv` /
`network_country_paths.csv`. Colour by `is_cross_border` or `domain` rather
than a publication-count gradient — these two networks answer "who
collaborates with whom," not "who is most prolific," so a categorical colour
reads better than the author network's sequential one.

### 9. Singapore-led vs participating
`publications.csv`. `singapore_led` → Colour on a `year` × `COUNTD([uid])` bar
chart. Cross-reference `screening_flags` containing `regional_participation`.

### 10. Topic map (discovered clusters, supplementary to the donut)

A scatter/cluster landscape, **not** a bar chart or treemap of cluster sizes
— the whole point is showing which topics sit near each other. Use this as a
second opinion alongside `classification/subdomain_vocabulary.csv`, not as
the published sub-domain chart — see "Topic map" and "Three classification
axes" above.

1. Connect to `publications.csv` (after `topic_model.py` and a rebuild).
   Filter `topic_label != "(too few records to cluster)"` and
   **`primary_domain` to one domain** — coordinates from different domains
   are not comparable.
2. `topic_map_x` → Columns, `topic_map_y` → Rows, both **Dimension** and
   **Continuous** (right-click each pill → Dimension, then Continuous — left
   as aggregated Measures they collapse to one point, same pitfall as the
   co-authorship network recipes).
3. Mark type **Circle**. `topic_label` → Colour. `uid`/`title` → Detail and
   Tooltip, so hovering a point shows which publication it is.
4. Add `dataset/topic_map_centroids.csv` as a second data source. Blend or
   union it in in on `domain_id`/`topic_id`, or just add it as a second sheet
   layer on the dashboard positioned over the first: `x`/`y` → Columns/Rows
   (Continuous), mark type **Text**, `topic_label` → Label and Text. This
   places a readable cluster name at each cluster's centre, the way the
   reference-style topic map should read.
5. Hide both axes and gridlines on both layers — the coordinates are
   similarity-graph layout space, not data with real units, exactly like the
   co-authorship network views.
6. If a domain was stratified-sampled (`--map-max-docs`), say so on the
   chart — it shows a representative subset, not every record in that domain.

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
7. **Sub-domains depend on MeSH indexing.** A publication's sub-domain comes
   entirely from its `mesh_terms`, and NLM's MeSH indexing typically lags
   publication by weeks to months — a recent or ahead-of-print PubMed record
   can have few or no MeSH terms yet, and will land in "Other/unspecified"
   until it's re-fetched after indexing catches up. This is a real, expected
   gap, not a bug; a run soon after publication will show more
   "Other/unspecified" than the same corpus fetched later.
8. **Sub-domain granularity is corpus-size-dependent.** A small domain (or an
   early/exploratory run) may not clear `--subdomain-min-records` for
   anything, leaving that whole domain's donut chart as "Other/unspecified."
   Check `classification/subdomain_vocabulary.csv` — an empty or very short
   vocabulary for a domain means lower `--subdomain-min-records` for that run,
   not that the domain genuinely lacks sub-domains.
9. **Research-type coverage is only as good as the curated list.** Many
   publications with `research_types` empty means
   `reference/research-type-taxonomy.md` needs more terms for your corpus —
   check `classification/unassigned_research_type.jsonl` before publishing
   that chart.
