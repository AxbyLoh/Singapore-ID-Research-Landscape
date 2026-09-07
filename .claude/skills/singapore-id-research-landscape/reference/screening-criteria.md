# Screening criteria — Singapore infectious disease research

This file is the single source of truth for what gets into the dataset. It is
meant to be read and edited by humans. Scripts read it at runtime; nothing is
hardcoded elsewhere.

**Version:** 1.0 · **Last amended:** 2026-09-07

---

## How to read this file

Every rule has an ID (`INC-*` to include, `EXC-*` to exclude). Exclusions win
over inclusions unless a rule says otherwise.

Some rules carry a fenced `json` block. Those are **mechanical** — `screen.py`
applies them automatically without judgement. Rules without a block need a
reader (you) to weigh them; that is deliberate, not an omission.

A record survives screening only if it satisfies **all four** gates:

1. **Topic** — it is about an infectious disease (§1)
2. **Geography** — it is Singapore research (§2)
3. **Type** — it is a research output we count (§3)
4. No exclusion in §4 applies

When a record fails no gate cleanly but does not clearly pass either, it is
**uncertain**. Uncertain is a legitimate outcome. Escalate it (full text →
user), do not force it.

---

## §1 Topic gate — is it infectious disease research?

### INC-TOP-01 — Core inclusion
Include if the work's primary subject is a communicable disease or the
pathogens, hosts, vectors, transmission, prevention, diagnosis, treatment,
surveillance, control or policy relating to one.

This covers all five domains in `domain-taxonomy.md`, plus infectious disease
work that falls outside them (tagged `other_id`).

### INC-TOP-02 — Methods and enabling research
Include work whose subject is a method, platform or model **developed for or
applied to** an infectious disease question: diagnostics, vaccines,
antimicrobials, genomic epidemiology, transmission modelling, vector control
technology, infection prevention interventions.

Include health-systems, behavioural, economic and policy research when the
health condition in question is an infectious disease (e.g. vaccine hesitancy,
outbreak preparedness financing, antimicrobial stewardship implementation).

### EXC-TOP-01 — Immunology and microbiology without an infection question
Exclude basic immunology, microbiology, or molecular biology where no specific
infectious disease or pathogen is the object of study — e.g. a paper on generic
T-cell receptor structure, or gut microbiome composition studied purely as
metabolic biology.

Borderline call: if a named human pathogen is central, include. If the organism
is a model system for non-infectious biology, exclude.

### EXC-TOP-02 — Non-communicable disease
Exclude work on non-communicable disease, even where infection is a passing risk
factor. An oncology paper is included only if the infectious agent (e.g. HPV,
HBV, *H. pylori*) is a substantive object of study, not merely a covariate.

---

## §2 Geography gate — is it Singapore research?

At least one of the following must hold.

### INC-GEO-01 — Singapore author affiliation
At least one author lists a Singapore-based institution in their affiliation.
This is the primary and most common route to inclusion.

```json
{
  "rule_id": "INC-GEO-01",
  "applies_to": "affiliation_country",
  "operator": "any_equals",
  "value": "Singapore",
  "outcome": "pass_geography"
}
```

### INC-GEO-02 — Singapore study setting
The study population, sample, outbreak, surveillance system, health system or
policy under study is in Singapore, even if no author is Singapore-affiliated.
This is a judgement call from the title/abstract, not a mechanical match.

### INC-GEO-03 — Regional work led from Singapore
Multi-country studies (SE Asia, Asia-Pacific, global) count when a
Singapore-affiliated author holds a leading role — first, last, corresponding —
or when a Singapore institution is the coordinating centre.

Multi-country studies with a Singapore co-author in a non-leading position are
**included but flagged** `regional_participation`, so they can be filtered out of
"Singapore-led" views in Tableau.

### EXC-GEO-01 — Singapore mentioned only in passing
Exclude when "Singapore" appears only as a citation, a comparator country in a
discussion, a conference venue, or a publisher's address, with no Singapore
author, data or setting.

### EXC-GEO-02 — Corporate regional-office affiliation only
A Singapore address that is only a company's regional/branch office (e.g. a
pharmaceutical firm's "…International AG Singapore Branch"), on a study with no
Singapore data, setting or academic collaborator, does not make it Singapore
research. Exclude, or include flagged `industry_regional_office` if the user
prefers to keep these — see the amendment log before deciding.

---

## §3 Type gate — is it a research output we count?

### INC-TYP-01 — Included publication types
Journal articles, reviews, systematic reviews and meta-analyses, clinical trial
reports, observational studies, brief/short reports, case series, modelling
studies, and preprints when the user has asked for preprints.

### EXC-TYP-01 — Excluded publication types
Exclude editorials, comments, news items, biographies, retracted publications,
corrections/errata, and published conference abstracts.

```json
{
  "rule_id": "EXC-TYP-01",
  "applies_to": "article_types",
  "operator": "any_in",
  "value": ["Editorial", "Comment", "News", "Biography", "Published Erratum",
            "Retraction of Publication", "Retracted Publication",
            "Congress", "Newspaper Article", "Patient Education Handout"],
  "outcome": "exclude"
}
```

Note: `Letter` is deliberately **not** on the mechanical list. Letters to the
editor frequently carry original outbreak or surveillance data in ID journals,
so they are routed to uncertain for a human read rather than auto-excluded.

### EXC-TYP-02 — Case reports
Exclude single-patient case reports by default: they inflate counts without
representing research programmes. Case **series** (n >= 5) are included.

### EXC-TYP-03 — Language
Exclude publications not available in English, since title/abstract screening
cannot be done reliably otherwise. Record them in the exclusion log rather than
dropping them, so the gap is visible.

```json
{
  "rule_id": "EXC-TYP-03",
  "applies_to": "language",
  "operator": "not_equals",
  "value": "eng",
  "outcome": "exclude"
}
```

### EXC-TYP-04 — Publication window
Exclude publications outside the run's date window. The window is set per run
(`build_queries.py --from-year/--to-year`), not fixed here.

```json
{
  "rule_id": "EXC-TYP-04",
  "applies_to": "year",
  "operator": "outside_run_window",
  "outcome": "exclude"
}
```

---

## §4 General exclusions

### EXC-GEN-01 — Duplicates
One record per publication. Preprint + journal version of the same work counts
once, keeping the journal version and retaining the preprint ID as an alias.
Handled mechanically by `ingest.py`.

### EXC-GEN-02 — Non-human, non-public-health veterinary and plant work
Exclude veterinary or agricultural infectious disease research with no human
health or One Health framing. Include it when zoonotic transmission,
antimicrobial resistance flow, or human exposure is part of the study.

### EXC-GEN-03 — No abstract available
A record with no abstract cannot be screened on title and abstract. Route to
uncertain, attempt full text, and only then decide. Never auto-include on a
title alone.

---

## §5 Domain assignment notes

Domain assignment happens after screening and does not gate inclusion. A record
may belong to more than one domain (e.g. TB/HIV co-infection -> Tuberculosis and
STI). An included record that fits no domain is tagged `other_id` and kept.

Assignment terms live in `domain-taxonomy.md`, not here.

---

## Amendment log

Every entry records a decision made by the user that changed the rules above.
Append new entries at the top. Never rewrite history here.

Format:

```
### YYYY-MM-DD — <short title>
- **Prompted by:** <PMID/DOI/title of the record that raised the question>
- **Question asked:** <what was ambiguous>
- **User ruling:** <what the user decided>
- **Change made:** <rule ID added or edited, and what it now says>
```

### 2026-09-07 — Initial version
- **Prompted by:** n/a — first authoring of the criteria.
- **Question asked:** n/a
- **User ruling:** n/a
- **Change made:** Established §1–§5 as the baseline. `EXC-GEO-02`
  (corporate regional-office-only affiliation) and `EXC-TYP-02` (single-patient
  case reports) are the two rules most likely to need a user ruling on first
  use; confirm both with the user on the first run and amend here.
