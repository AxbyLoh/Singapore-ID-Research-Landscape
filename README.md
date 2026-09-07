# Singapore ID Research Landscape

A Claude Skill that builds a screened, categorised, Tableau-ready dataset of
infectious disease research publications from Singapore.

The skill lives in
[`.claude/skills/singapore-id-research-landscape/`](.claude/skills/singapore-id-research-landscape/)
and is picked up automatically by Claude Code when working in this repository.

## What it does

```
preflight → search → ingest → screen → classify → dataset → topic model
```

1. **Preflight** — confirms the PubMed connector and Python are available, and
   that the maintained data files are populated.
2. **Search** — PubMed/MEDLINE queries per domain, one query per expert on the
   CDA Directory of Experts roster, and Google Scholar leads via web search.
3. **Ingest** — normalises the connector's output and deduplicates on
   DOI → PMID → normalised title, keeping full query provenance.
4. **Screen** — applies the mechanical inclusion/exclusion rules, then hands
   everything genuinely ambiguous to the agent, which escalates to full text
   and then to the user, and **amends the criteria file** based on the answer.
5. **Classify** — assigns the five domains (multi-domain allowed) and resolves
   every author affiliation to an institution, country, region and sector.
6. **Dataset** — emits the publication fact table plus long author, institution,
   country and co-authorship edge tables, with pre-computed network coordinates
   so Tableau can draw the collaboration graph directly.
7. **Topic model** — clusters sub-domains within each domain by semantic
   similarity.

## The five domains

| Domain | Covers |
|---|---|
| Vector-borne diseases | Dengue, Zika, chikungunya, malaria, vectors, vector control |
| Sexually-transmitted infections | HIV, syphilis, gonorrhoea, chlamydia, HPV, sexual health services |
| Tuberculosis | Active/latent TB, drug-resistant TB, diagnostics, screening programmes |
| Respiratory-tract infections | Influenza, COVID-19, RSV, pneumonia, pertussis |
| AMR and healthcare-associated infections | Resistance, stewardship, HAI, IPC |

Anything included but outside these five is kept and tagged `other_id`.

## What humans maintain

These three files drive behaviour and are meant to be edited. No script
hardcodes their contents; editing one changes the next run.

| File | Controls |
|---|---|
| [`reference/screening-criteria.md`](.claude/skills/singapore-id-research-landscape/reference/screening-criteria.md) | Inclusion/exclusion rules, plus the amendment log |
| [`data/directory_of_experts.csv`](.claude/skills/singapore-id-research-landscape/data/directory_of_experts.csv) | The CDA expert roster searched by name |
| [`reference/domain-taxonomy.md`](.claude/skills/singapore-id-research-landscape/reference/domain-taxonomy.md) | Domain definitions, terms and MeSH mappings |

Two alias tables tune affiliation resolution:
[`institution_aliases.csv`](.claude/skills/singapore-id-research-landscape/data/institution_aliases.csv)
and
[`country_aliases.csv`](.claude/skills/singapore-id-research-landscape/data/country_aliases.csv).

## Getting started

Ask Claude to build the landscape and it will run the skill. Or drive the
scripts directly:

```bash
SK=.claude/skills/singapore-id-research-landscape
RUN=runs/$(date +%F)

python3 $SK/scripts/preflight.py     --run-dir $RUN
python3 $SK/scripts/build_queries.py --run-dir $RUN --from-year 2015 --to-year 2026
# ... the agent runs the queries and saves results to $RUN/raw/ ...
python3 $SK/scripts/ingest.py        --run-dir $RUN
python3 $SK/scripts/screen.py        --run-dir $RUN
# ... the agent resolves $RUN/screening/uncertain.jsonl ...
python3 $SK/scripts/classify.py      --run-dir $RUN
python3 $SK/scripts/topic_model.py   --run-dir $RUN
python3 $SK/scripts/build_dataset.py --run-dir $RUN
```

Search itself runs through the PubMed MCP connector, so the retrieval steps
need Claude (or another MCP client) in the loop — the scripts have no network
access of their own. See
[`reference/setup.md`](.claude/skills/singapore-id-research-landscape/reference/setup.md).

## The expert directory

`data/directory_of_experts.csv` ships with **headers only**. Populate it:

```bash
python3 $SK/scripts/fetch_experts.py --out $SK/data/directory_of_experts.csv
```

The scraper merges on `profile_url`, preserves hand-edited columns
(`pubmed_author_query`, `orcid`, `domains`, `notes`, `active`), keeps rows the
fetch did not return, and writes nothing at all if the site is unreachable.
`data/directory_of_experts.EXAMPLE.csv` shows the format with two clearly
fictional rows.

## Requirements

Python 3.8+, standard library only. `scikit-learn` and `sentence-transformers`
are optional and improve topic modelling quality; without them a deterministic
pure-Python TF-IDF backend is used.

## Tests

```bash
bash tests/run_pipeline_test.sh
```

Runs the whole pipeline against a fixture and asserts screening outcomes,
domain assignment, dataset referential integrity and layout determinism. Run it
after editing any script, and after editing the criteria or taxonomy files — a
malformed JSON block in either is the most common way to break a run.

## Caveats

Author identity is surname + first initial (PubMed has no universal author ID),
institution resolution is alias-based, and topic clusters are unsupervised.
[`reference/dataset-schema.md`](.claude/skills/singapore-id-research-landscape/reference/dataset-schema.md)
lists the limitations that belong alongside any published visualisation.

Publication data comes from PubMed; cite it accordingly.
