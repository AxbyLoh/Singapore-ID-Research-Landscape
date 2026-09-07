# Sub-domain taxonomy

Curated, named sub-domains **within** each of the five domains — the labels
that drive the "Sub-domains of X" donut/pie chart. This is deliberately a
maintained taxonomy, not an ML output: the reference dashboard this skill
targets labels its VBD slices by named pathogen (*Dengue virus*, *Malaria*,
*Flavivirus*, *Oropouche Virus*, *Crimean-Congo hemorrhagic fever virus*, …),
and a human-edited list is what keeps that chart's legend meaningful and
stable across runs. `classify.py` reads the fenced `json` blocks below at
runtime; add or edit a block to change classification, no code change needed.

## How this differs from `domain-taxonomy.md` and `topic_model.py`

| | Scope | Method | Output |
|---|---|---|---|
| `domain-taxonomy.md` | All records | Curated terms | The 5 domains |
| **`subdomain-taxonomy.md`** | Records **already in one domain** | Curated terms | Named sub-domain (this file) |
| `topic_model.py` | Records already in one domain | Unsupervised clustering | Discovered clusters, for finding gaps in this file |

Run sub-domain classification for the donut chart. Run `topic_model.py`
separately, afterwards, to sanity-check this taxonomy: read its
`topics_report.md` — a cluster whose exemplar titles all belong to one named
pathogen or theme that has no block below is a taxonomy gap. Add the block,
re-run `classify.py`, and the discovered cluster disappears into a proper
named slice next time.

## Scoring

Identical mechanism to `domain-taxonomy.md` (`idlib.score_taxa`), scoped to
one domain: a record is only scored against its own `primary_domain`'s
sub-domain blocks. Title/keyword/MeSH hits score double; abstract hits score
once; a `blockers` term in the title zeroes that sub-domain. The
highest-scoring block above `threshold` becomes `primary_subdomain` — the
value the donut chart should use, since its slices are meant to be mutually
exclusive and sum to the domain's publication count. All blocks that clear
`threshold` are also kept as a pipe-list, for anyone who wants a multi-label
view instead.

A record whose domain has no matching block, or whose domain has no
sub-domain blocks defined at all, gets `primary_subdomain = "Other/unspecified
<domain label>"`. A domain with many "Other" records is the clearest signal
that this file needs more blocks for that domain.

---

## Vector-borne diseases

The list and (starred) approximate shares below were calibrated against the
reference Tableau dashboard's "Sub-domains of VBD" chart: Dengue virus 55.32%,
Malaria 14.89%, Flavivirus 6.38%, Oropouche Virus 2.13%, Crimean-Congo
hemorrhagic fever virus 2.13%. The remaining share was split across smaller
slices not fully legible in the source screenshot — the blocks below fill
that out with the other vector-borne pathogens this skill already searches
for in `domain-taxonomy.md`. **Recalibrate the exact list against your own
corpus** once a real run completes; treat this as a strong starting point,
not ground truth.

```json
{"domain_id": "vector_borne", "subdomain_id": "dengue", "label": "Dengue virus",
 "threshold": 3,
 "terms": {"dengue": 3, "denv": 3, "dengue virus": 3, "dengue serotype": 3,
           "severe dengue": 2, "dengue haemorrhagic": 2, "dengue hemorrhagic": 2,
           "dengue vaccine": 2, "ns1 antigen": 2},
 "mesh_terms": {"Dengue": 3, "Dengue Virus": 3, "Severe Dengue": 3, "Dengue Vaccines": 2},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "malaria", "label": "Malaria",
 "threshold": 3,
 "terms": {"malaria": 3, "plasmodium": 3, "falciparum": 3, "vivax": 3,
           "knowlesi": 3, "plasmodium knowlesi": 3, "antimalarial": 2},
 "mesh_terms": {"Malaria": 3, "Plasmodium": 3, "Plasmodium falciparum": 3,
               "Plasmodium vivax": 3, "Antimalarials": 2},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "flavivirus_other", "label": "Flavivirus",
 "threshold": 3,
 "terms": {"flavivirus": 3, "japanese encephalitis": 3, "west nile": 3,
           "yellow fever": 3, "zika": 3, "zika virus": 3, "tick-borne encephalitis": 2},
 "mesh_terms": {"Flavivirus": 3, "Flavivirus Infections": 3,
               "Encephalitis, Japanese": 3, "West Nile Fever": 3,
               "Yellow Fever": 3, "Zika Virus Infection": 3},
 "blockers": ["dengue"],
 "notes": "Non-dengue flaviviruses grouped as one slice, matching the reference chart. Split zika/JE/yellow fever into their own blocks if your corpus is large enough to warrant it."}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "chikungunya", "label": "Chikungunya virus",
 "threshold": 3,
 "terms": {"chikungunya": 3, "chikv": 3, "chikungunya virus": 3},
 "mesh_terms": {"Chikungunya Fever": 3, "Chikungunya virus": 3},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "oropouche", "label": "Oropouche Virus",
 "threshold": 3,
 "terms": {"oropouche": 3, "oropouche virus": 3},
 "mesh_terms": {},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "cchf", "label": "Crimean-Congo hemorrhagic fever virus",
 "threshold": 3,
 "terms": {"crimean-congo": 3, "crimean congo": 3, "cchf": 3,
           "crimean-congo hemorrhagic fever": 3, "crimean-congo haemorrhagic fever": 3},
 "mesh_terms": {"Hemorrhagic Fever Virus, Crimean-Congo": 3,
               "Hemorrhagic Fever, Crimean": 3},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "rickettsial", "label": "Rickettsial disease",
 "threshold": 3,
 "terms": {"scrub typhus": 3, "orientia": 3, "rickettsi*": 3, "typhus": 2,
           "spotted fever": 3},
 "mesh_terms": {"Scrub Typhus": 3, "Rickettsia Infections": 3, "Typhus, Epidemic Louse-Borne": 2},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "leptospirosis", "label": "Leptospirosis",
 "threshold": 3,
 "terms": {"leptospir*": 3, "leptospirosis": 3},
 "mesh_terms": {"Leptospirosis": 3, "Leptospira": 3},
 "blockers": []}
```

```json
{"domain_id": "vector_borne", "subdomain_id": "vector_control", "label": "Vector control and entomology",
 "threshold": 3,
 "terms": {"vector control": 3, "wolbachia": 3, "sterile insect": 3,
           "aedes": 2, "anopheles": 2, "culex": 2, "mosquito*": 1,
           "larvicid*": 2, "insecticide": 2, "vector competence": 2,
           "gravitrap": 3, "entomolog*": 2, "vectorial capacity": 2,
           "breteau index": 2, "insecticide resistance": 3},
 "mesh_terms": {"Mosquito Control": 3, "Mosquito Vectors": 2, "Insect Vectors": 2,
               "Wolbachia": 3, "Insecticides": 2, "Insecticide Resistance": 3},
 "blockers": ["dengue", "malaria", "chikungunya", "zika"],
 "notes": "Vector biology/control papers not primarily framed around one pathogen. Blocked from stealing dengue/malaria/chikungunya-titled papers, which belong in their own pathogen slice even when they discuss vector control."}
```

---

## Sexually-transmitted infections

```json
{"domain_id": "sti", "subdomain_id": "hiv", "label": "HIV",
 "threshold": 3,
 "terms": {"hiv": 3, "hiv-1": 3, "hiv-2": 3, "aids": 2, "antiretroviral": 3,
           "pre-exposure prophylaxis": 3, "prep": 1, "viral suppression": 2,
           "cd4": 2, "people living with hiv": 3, "plhiv": 3},
 "mesh_terms": {"HIV Infections": 3, "HIV": 3, "HIV-1": 3,
               "Acquired Immunodeficiency Syndrome": 3, "Anti-HIV Agents": 2,
               "Pre-Exposure Prophylaxis": 3},
 "blockers": []}
```

```json
{"domain_id": "sti", "subdomain_id": "syphilis", "label": "Syphilis",
 "threshold": 3,
 "terms": {"syphilis": 3, "treponema": 3, "treponema pallidum": 3},
 "mesh_terms": {"Syphilis": 3, "Treponema pallidum": 3},
 "blockers": []}
```

```json
{"domain_id": "sti", "subdomain_id": "gonorrhoea", "label": "Gonorrhoea",
 "threshold": 3,
 "terms": {"gonorrh*": 3, "neisseria gonorrhoeae": 3},
 "mesh_terms": {"Gonorrhea": 3, "Neisseria gonorrhoeae": 3},
 "blockers": []}
```

```json
{"domain_id": "sti", "subdomain_id": "chlamydia", "label": "Chlamydia",
 "threshold": 3,
 "terms": {"chlamydia": 3, "chlamydia trachomatis": 3, "lymphogranuloma": 2},
 "mesh_terms": {"Chlamydia Infections": 3, "Chlamydia trachomatis": 3},
 "blockers": []}
```

```json
{"domain_id": "sti", "subdomain_id": "hpv", "label": "Human papillomavirus (HPV)",
 "threshold": 3,
 "terms": {"human papillomavirus": 3, "hpv": 3, "genital wart": 3, "hpv vaccine": 2},
 "mesh_terms": {"Papillomavirus Infections": 3, "Human papillomavirus viruses": 3},
 "blockers": []}
```

```json
{"domain_id": "sti", "subdomain_id": "other_sti_pathogens", "label": "Other STI pathogens",
 "threshold": 3,
 "terms": {"genital herpes": 3, "herpes simplex virus type 2": 3, "hsv-2": 3,
           "mycoplasma genitalium": 3, "trichomonas": 3, "trichomoniasis": 3,
           "chancroid": 3, "mpox": 2, "monkeypox": 2},
 "mesh_terms": {"Herpes Genitalis": 3},
 "blockers": ["hiv", "syphilis", "gonorrh", "chlamydia", "hpv"]}
```

```json
{"domain_id": "sti", "subdomain_id": "sexual_health_services", "label": "Sexual health services and behaviour",
 "threshold": 3,
 "terms": {"sexual health": 3, "sexual risk behavio*": 3, "condom": 2,
           "partner notification": 3, "sexually transmitted": 1, "sti clinic": 3,
           "men who have sex with men": 2, "sex worker": 3},
 "mesh_terms": {"Sex Workers": 2, "Unsafe Sex": 2, "Homosexuality, Male": 1},
 "blockers": []}
```

---

## Tuberculosis

```json
{"domain_id": "tb", "subdomain_id": "drug_susceptible_tb", "label": "Drug-susceptible TB — clinical",
 "threshold": 3,
 "terms": {"active tuberculosis": 3, "pulmonary tuberculosis": 3,
           "extrapulmonary tuberculosis": 3, "tb treatment": 2,
           "directly observed therapy": 3, "dots": 1, "isoniazid": 2,
           "rifampic*": 2, "ethambutol": 2, "pyrazinamide": 2},
 "mesh_terms": {"Tuberculosis, Pulmonary": 3, "Tuberculosis, Lymph Node": 2,
               "Tuberculosis, Miliary": 2},
 "blockers": ["mdr", "xdr", "latent"]}
```

```json
{"domain_id": "tb", "subdomain_id": "drug_resistant_tb", "label": "Drug-resistant TB",
 "threshold": 3,
 "terms": {"multidrug-resistant tuberculosis": 3, "mdr-tb": 3, "xdr-tb": 3,
           "rifampicin resistance": 3, "bedaquiline": 3, "delamanid": 3,
           "extensively drug-resistant": 3},
 "mesh_terms": {"Tuberculosis, Multidrug-Resistant": 3,
               "Extensively Drug-Resistant Tuberculosis": 3},
 "blockers": []}
```

```json
{"domain_id": "tb", "subdomain_id": "latent_tb", "label": "Latent TB infection",
 "threshold": 3,
 "terms": {"latent tuberculosis": 3, "ltbi": 3, "tuberculin": 3, "mantoux": 3,
           "interferon-gamma release assay": 3, "igra": 3, "quantiferon": 3,
           "tb preventive therapy": 3},
 "mesh_terms": {"Latent Tuberculosis": 3, "Tuberculin Test": 3,
               "Interferon-gamma Release Tests": 3},
 "blockers": []}
```

```json
{"domain_id": "tb", "subdomain_id": "tb_diagnostics", "label": "TB diagnostics",
 "threshold": 3,
 "terms": {"sputum smear": 3, "sputum culture": 3, "acid-fast": 3,
           "genexpert": 3, "xpert mtb": 3, "molecular diagnostic": 1},
 "mesh_terms": {},
 "blockers": []}
```

```json
{"domain_id": "tb", "subdomain_id": "tb_screening", "label": "TB screening and case-finding",
 "threshold": 3,
 "terms": {"tb screening": 3, "tb notification": 3, "tb contact": 3,
           "active case finding": 3, "migrant worker tuberculosis": 2, "bcg": 1},
 "mesh_terms": {"Mass Screening": 1, "BCG Vaccine": 1},
 "blockers": []}
```

```json
{"domain_id": "tb", "subdomain_id": "tb_hiv_coinfection", "label": "TB/HIV co-infection",
 "threshold": 4,
 "terms": {"hiv": 2, "tuberculosis": 2, "hiv-tuberculosis": 4, "tb-hiv": 4,
           "coinfection": 2, "co-infection": 2},
 "mesh_terms": {"Coinfection": 2},
 "blockers": []}
```

---

## Respiratory-tract infections

```json
{"domain_id": "rti", "subdomain_id": "influenza", "label": "Influenza",
 "threshold": 3,
 "terms": {"influenza": 3, "h1n1": 3, "h3n2": 3, "h5n1": 3, "h7n9": 3,
           "avian influenza": 3, "influenza-like illness": 3, "influenza vaccin*": 2},
 "mesh_terms": {"Influenza, Human": 3, "Influenza Vaccines": 2,
               "Influenza A Virus, H1N1 Subtype": 3},
 "blockers": []}
```

```json
{"domain_id": "rti", "subdomain_id": "covid19", "label": "COVID-19 / SARS-CoV-2",
 "threshold": 3,
 "terms": {"covid-19": 3, "covid": 3, "sars-cov-2": 3, "sars-cov": 2,
           "long covid": 3, "covid-19 vaccin*": 2},
 "mesh_terms": {"COVID-19": 3, "SARS-CoV-2": 3, "COVID-19 Vaccines": 2},
 "blockers": []}
```

```json
{"domain_id": "rti", "subdomain_id": "rsv_other_viral", "label": "RSV and other respiratory viruses",
 "threshold": 3,
 "terms": {"respiratory syncytial virus": 3, "rsv": 3, "bronchiolitis": 2,
           "human metapneumovirus": 3, "parainfluenza": 3, "rhinovirus": 3,
           "adenovirus": 2, "enterovirus": 2},
 "mesh_terms": {"Respiratory Syncytial Virus Infections": 3,
               "Respiratory Syncytial Virus, Human": 3, "Bronchiolitis": 2,
               "Metapneumovirus": 3},
 "blockers": []}
```

```json
{"domain_id": "rti", "subdomain_id": "bacterial_pneumonia", "label": "Bacterial pneumonia and pneumococcal disease",
 "threshold": 3,
 "terms": {"pneumonia": 2, "community-acquired pneumonia": 3,
           "pneumococc*": 3, "streptococcus pneumoniae": 3,
           "haemophilus influenzae": 3, "legionell*": 3, "mycoplasma pneumoniae": 3},
 "mesh_terms": {"Pneumonia, Bacterial": 3, "Streptococcus pneumoniae": 3,
               "Pneumococcal Vaccines": 2, "Legionellosis": 3},
 "blockers": ["ventilator-associated"]}
```

```json
{"domain_id": "rti", "subdomain_id": "pertussis_other_bacterial", "label": "Pertussis and other vaccine-preventable bacterial RTI",
 "threshold": 3,
 "terms": {"pertussis": 3, "bordetella": 3, "whooping cough": 3, "diphtheria": 3},
 "mesh_terms": {"Whooping Cough": 3},
 "blockers": []}
```

```json
{"domain_id": "rti", "subdomain_id": "urti_other", "label": "Upper respiratory tract infection",
 "threshold": 3,
 "terms": {"pharyngitis": 3, "otitis media": 3, "sinusitis": 2, "croup": 3,
           "upper respiratory": 3, "common cold": 2},
 "mesh_terms": {"Otitis Media": 3, "Pharyngitis": 3, "Common Cold": 2},
 "blockers": []}
```

---

## AMR and healthcare-associated infections

```json
{"domain_id": "amr_hai", "subdomain_id": "amr_stewardship", "label": "Antimicrobial stewardship",
 "threshold": 3,
 "terms": {"antimicrobial stewardship": 3, "antibiotic stewardship": 3,
           "antibiotic prescribing": 3, "antibiotic consumption": 3,
           "antibiogram": 2},
 "mesh_terms": {"Antimicrobial Stewardship": 3},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "gram_negative_resistance", "label": "Gram-negative resistance (CRE / ESBL / CRAB)",
 "threshold": 3,
 "terms": {"carbapenem-resistant": 3, "carbapenemase": 3, "cre": 2, "crab": 2,
           "extended-spectrum beta-lactamase": 3, "esbl": 3,
           "acinetobacter baumannii": 3, "pseudomonas aeruginosa": 2,
           "klebsiella pneumoniae": 2, "colistin resistance": 3, "mcr-1": 3},
 "mesh_terms": {"Carbapenem-Resistant Enterobacteriaceae": 3, "beta-Lactamases": 2,
               "Acinetobacter baumannii": 3, "Klebsiella pneumoniae": 2},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "gram_positive_resistance", "label": "Gram-positive resistance (MRSA / VRE)",
 "threshold": 3,
 "terms": {"methicillin-resistant": 3, "mrsa": 3, "vancomycin-resistant": 3,
           "vre": 2, "enterococcus faecium": 2},
 "mesh_terms": {"Methicillin-Resistant Staphylococcus aureus": 3,
               "Vancomycin-Resistant Enterococci": 3},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "c_difficile", "label": "Clostridioides difficile",
 "threshold": 3,
 "terms": {"clostridioides difficile": 3, "clostridium difficile": 3, "c. difficile": 3},
 "mesh_terms": {"Clostridioides difficile": 3, "Clostridium Infections": 2},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "device_associated_hai", "label": "Device- and procedure-associated HAI",
 "threshold": 3,
 "terms": {"central line-associated": 3, "clabsi": 3,
           "catheter-associated urinary": 3, "cauti": 3,
           "surgical site infection": 3, "ssi": 1,
           "ventilator-associated pneumonia": 3, "bloodstream infection": 2},
 "mesh_terms": {"Catheter-Related Infections": 3, "Surgical Wound Infection": 3,
               "Pneumonia, Ventilator-Associated": 3},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "ipc_practice", "label": "Infection prevention and control practice",
 "threshold": 3,
 "terms": {"infection prevention": 3, "infection control": 3, "hand hygiene": 3,
           "environmental cleaning": 2, "hospital outbreak": 2,
           "contact precautions": 3, "decolonisation": 2, "decolonization": 2},
 "mesh_terms": {"Infection Control": 3, "Hand Hygiene": 3, "Cross Infection": 1},
 "blockers": []}
```

```json
{"domain_id": "amr_hai", "subdomain_id": "candida_auris", "label": "Candida auris and antifungal resistance",
 "threshold": 3,
 "terms": {"candida auris": 3, "antifungal resistance": 3},
 "mesh_terms": {"Candida auris": 3},
 "blockers": []}
```
