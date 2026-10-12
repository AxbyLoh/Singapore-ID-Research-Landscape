# Setup — what the user must configure before the skill can run

Run this check at the start of every session that uses the skill (SKILL.md
step 0). Report the result in a few lines; if something required is missing,
stop and give the user the instructions below rather than degrading silently.

## 1. PubMed connector (required)

The skill retrieves publications through the **PubMed MCP connector**, not
through the network. Confirm you actually have these tools available before
searching — check your own tool list, do not assume:

| Tool | Used for |
|---|---|
| `search_articles` | Every query in `queries.json` |
| `get_article_metadata` | Titles, abstracts, authors, affiliations, MeSH |
| `get_full_text_article` | Escalating an uncertain screening decision |
| `find_related_articles` | Snowballing from a known key paper |
| `convert_article_ids` | PMID → PMCID before requesting full text |

**If they are not available**, tell the user:

> The PubMed connector isn't enabled for this session. In Claude, open
> **Settings → Connectors**, add or enable **PubMed**, then start a new session
> (or reconnect) so the tools load. Once it's on, ask me to re-run the
> preflight check.

Do not substitute web scraping of pubmed.ncbi.nlm.nih.gov for the connector.

### Attribution obligation

The PubMed connector requires attribution. Whenever you present results derived
from it, say the data came from PubMed, and give DOI links for any article you
cite individually. This holds even if asked to skip it.

## 2. Web search (optional but recommended)

Google Scholar has no API, so Scholar coverage relies on web search restricted
to `scholar.google.com`. If web search is unavailable, continue with
PubMed/MEDLINE and record the gap in the run report — do not silently drop the
Scholar family and present the result as complete.

## 3. Python (required)

Python 3.8 or newer. Every script in `scripts/` runs on the **standard library
alone** — no install step is needed for the pipeline to work end to end.

Optional accelerators, only for `topic_model.py`, best first:

```bash
pip install bertopic                # heaviest, best: HDBSCAN + c-TF-IDF (several GB --
                                     # pulls in torch, transformers, umap-learn, hdbscan;
                                     # also needs network access to huggingface.co at run
                                     # time to download its embedding model)
pip install sentence-transformers   # embedding topic backend (same huggingface.co need)
pip install scikit-learn            # TF-IDF + SVD topic backend, local, no network
```

`preflight.py` reports which are *installed*. That is not the same as
*usable*: BERTopic and plain `sentence-transformers` both need to reach
`huggingface.co` at run time to download their embedding model, which some
sandboxed environments block by organisation policy (distinct from whether
the package itself installed successfully). When that happens
`topic_model.py` fails that tier cleanly, logs the real reason, and falls
through — with nothing installed at all, topic modelling falls back to a
pure-standard-library TF-IDF, which works and is deterministic but is lexical
rather than semantic — near-synonyms ("antibiotic resistance" vs
"antimicrobial resistance") land in different clusters more often.

## 4. Network access — only for the expert directory

The only script that needs the internet is `fetch_experts.py`, which reads
`https://www.cda.gov.sg/professionals/research/directory-of-experts/`. Many
sandboxed environments block it. When that happens the script writes nothing
and exits non-zero; offer the user the documented alternatives: save the pages
as HTML and use `--from-html`, import a CSV export of the directory with
`--from-csv` (the most reliable offline path if the user can obtain one — it
merges the same way a live fetch would, preserving hand edits), or edit the
CSV by hand as a last resort.

Never work around a blocked fetch by inventing roster entries.

## 5. Data files the user owns

| File | Purpose | Ships as |
|---|---|---|
| `data/directory_of_experts.csv` | The CDA roster searched by name | Header only — must be populated |
| `data/institution_aliases.csv` | Affiliation → institution/sector/country | Seeded with major SG and partner institutions |
| `data/country_aliases.csv` | Affiliation → country/ISO3/region | Seeded with ~125 countries |
| `reference/screening-criteria.md` | Inclusion/exclusion rules | Version 1.0 baseline |
| `reference/domain-taxonomy.md` | The five domains and their terms | ~235 terms, ~100 MeSH headings |

`data/directory_of_experts.EXAMPLE.csv` shows the roster format with two
clearly-marked fictional rows. It is documentation, never an input — the
pipeline reads only `directory_of_experts.csv`.

## 6. First-run questions worth asking

Two criteria rules are most likely to need a ruling before the first real run.
Ask once, then record the answer in the criteria amendment log:

1. **`EXC-GEO-02`** — should a paper whose only Singapore link is a company's
   regional/branch office count as Singapore research?
2. **`EXC-TYP-02`** — should single-patient case reports be excluded?

Also confirm the **date window** (default 2015 to the current year) and whether
preprints are wanted.
