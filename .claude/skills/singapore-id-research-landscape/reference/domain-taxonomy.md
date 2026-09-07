# Domain taxonomy — five key domains

Defines the five domains records are categorised into, and the terms and MeSH
headings that drive automatic assignment. `classify.py` reads the fenced `json`
block inside each domain section at runtime — edit the block to change
classification behaviour, no code change needed.

## Scoring model

For each domain, `classify.py` scores a record over its title, abstract,
keywords and MeSH terms:

- **Title / keyword / MeSH match** — term weight x 2
- **Abstract match** — term weight x 1
- A term matches on whole-word boundaries, case-insensitively. Entries ending in
  `*` match as a prefix (`chikungunya*` matches `chikungunya virus`).
- Each distinct term contributes once per field, so a word repeated ten times in
  an abstract does not dominate.
- Any `blockers` term present in the title cancels the domain for that record.

A domain is assigned when its score >= `threshold`. A record may be assigned to
several domains; all are kept, and the highest-scoring one becomes
`primary_domain`. Records scoring below every threshold go to
`classification/unassigned.jsonl` for a human read.

Term weights, by convention:

| Weight | Meaning | Example |
|---|---|---|
| 3 | Pathognomonic — the term alone identifies the domain | `dengue`, `chlamydia trachomatis` |
| 2 | Strong but context-dependent | `mosquito`, `sputum smear` |
| 1 | Supporting; needs a companion term to reach threshold | `outbreak`, `vaccine` |

---

## 1. Vector-borne diseases

**Scope.** Diseases transmitted by arthropod vectors, plus the vectors
themselves and vector-control research. Includes dengue, Zika, chikungunya,
malaria, Japanese encephalitis, scrub typhus and other rickettsioses,
leptospirosis where rodent/vector ecology is central, and *Wolbachia*/sterile
insect vector-control programmes.

**Not here.** Rodent-borne or waterborne disease with no arthropod vector.
Mosquito biology with no disease framing goes to `other_id`.

```json
{
  "domain_id": "vector_borne",
  "label": "Vector-borne diseases",
  "threshold": 4,
  "terms": {
    "dengue": 3, "denv": 3, "severe dengue": 3, "dengue haemorrhagic": 3,
    "dengue hemorrhagic": 3, "zika": 3, "chikungunya": 3, "chikv": 3,
    "malaria": 3, "plasmodium": 3, "falciparum": 3, "vivax": 3, "knowlesi": 3,
    "japanese encephalitis": 3, "west nile": 3, "yellow fever": 3,
    "scrub typhus": 3, "orientia": 3, "rickettsi*": 3, "leptospir*": 3,
    "aedes": 3, "anopheles": 3, "culex": 3, "wolbachia": 3,
    "chikungunya virus": 3, "arbovir*": 3, "flavivir*": 2,
    "vector-borne": 3, "vector borne": 3, "vector control": 3,
    "sterile insect": 3, "mosquito*": 2, "larvicid*": 2, "insecticide": 2,
    "vector competence": 3, "entomolog*": 2, "gravitrap": 3,
    "tick-borne": 3, "sandfly": 2, "leishmani*": 3, "chagas": 3,
    "filaria*": 3, "dengue serotype": 3, "ns1 antigen": 2,
    "mosquito-borne": 3, "vectorial capacity": 3, "breteau index": 3
  },
  "mesh_terms": {
    "Dengue": 3, "Dengue Virus": 3, "Severe Dengue": 3, "Zika Virus": 3,
    "Zika Virus Infection": 3, "Chikungunya Fever": 3, "Chikungunya virus": 3,
    "Malaria": 3, "Plasmodium": 3, "Plasmodium falciparum": 3,
    "Encephalitis, Japanese": 3, "Scrub Typhus": 3, "Leptospirosis": 3,
    "Aedes": 3, "Anopheles": 3, "Culex": 3, "Mosquito Vectors": 3,
    "Mosquito Control": 3, "Insect Vectors": 3, "Arbovirus Infections": 3,
    "Vector Borne Diseases": 3, "Wolbachia": 3, "Insecticides": 2
  },
  "blockers": []
}
```

---

## 2. Sexually-transmitted infections

**Scope.** HIV (including prevention, treatment, care cascade and
epidemiology), syphilis, gonorrhoea, chlamydia, genital herpes, HPV where the
infection or its prevention is the object of study, mpox where sexual
transmission is the framing, and sexual-health services research addressing STI.

**Not here.** Hepatitis B and C default to `other_id` unless the paper frames
transmission as sexual; add them here if the user rules otherwise (record it in
the criteria amendment log).

**Overlap.** HIV/TB co-infection belongs to both this domain and Tuberculosis;
both assignments are kept.

```json
{
  "domain_id": "sti",
  "label": "Sexually-transmitted infections",
  "threshold": 4,
  "terms": {
    "hiv": 3, "hiv-1": 3, "hiv-2": 3, "aids": 2,
    "antiretroviral": 3, "art initiation": 2, "pre-exposure prophylaxis": 3,
    "prep": 2, "post-exposure prophylaxis": 2, "viral suppression": 2,
    "cd4": 2, "people living with hiv": 3, "plhiv": 3,
    "syphilis": 3, "treponema": 3, "gonorrh*": 3, "neisseria gonorrhoeae": 3,
    "chlamydia": 3, "chlamydia trachomatis": 3, "trichomonas": 3,
    "genital herpes": 3, "herpes simplex virus type 2": 3, "hsv-2": 3,
    "human papillomavirus": 3, "hpv": 3, "genital wart": 3,
    "mycoplasma genitalium": 3, "lymphogranuloma": 3, "chancroid": 3,
    "sexually transmitted": 3, "sexually-transmitted": 3, "sti": 2, "std": 2,
    "men who have sex with men": 3, "msm": 2, "sex worker": 3,
    "condom": 2, "sexual health": 2, "sexual risk behavio*": 3,
    "partner notification": 2, "mpox": 2, "monkeypox": 2
  },
  "mesh_terms": {
    "HIV Infections": 3, "HIV": 3, "HIV-1": 3,
    "Acquired Immunodeficiency Syndrome": 3, "Anti-HIV Agents": 3,
    "Antiretroviral Therapy, Highly Active": 3, "Pre-Exposure Prophylaxis": 3,
    "Sexually Transmitted Diseases": 3,
    "Sexually Transmitted Diseases, Bacterial": 3,
    "Sexually Transmitted Diseases, Viral": 3,
    "Syphilis": 3, "Treponema pallidum": 3, "Gonorrhea": 3,
    "Neisseria gonorrhoeae": 3, "Chlamydia Infections": 3,
    "Chlamydia trachomatis": 3, "Papillomavirus Infections": 3,
    "Herpes Genitalis": 3, "Homosexuality, Male": 2, "Sex Workers": 2,
    "Unsafe Sex": 2, "Mpox (monkeypox)": 2
  },
  "blockers": []
}
```

---

## 3. Tuberculosis

**Scope.** All *Mycobacterium tuberculosis* research: active and latent TB,
drug-resistant TB, diagnostics, treatment regimens, contact tracing, TB
screening programmes, and TB in migrant and other risk populations.

**Not here.** Non-tuberculous mycobacteria (NTM) and leprosy default to
`other_id`. Move them here only on a user ruling.

**Overlap.** MDR/XDR-TB scores in both Tuberculosis and AMR/HAI; both are kept,
and Tuberculosis is normally the primary domain because its score is higher.

```json
{
  "domain_id": "tb",
  "label": "Tuberculosis",
  "threshold": 4,
  "terms": {
    "tuberculosis": 3, "tuberculous": 3, "mycobacterium tuberculosis": 3,
    "m. tuberculosis": 3, "mtb": 2, "tb": 2,
    "latent tuberculosis": 3, "ltbi": 3, "active tuberculosis": 3,
    "pulmonary tuberculosis": 3, "extrapulmonary tuberculosis": 3,
    "multidrug-resistant tuberculosis": 3, "mdr-tb": 3, "xdr-tb": 3,
    "rifampic*": 3, "rifampin": 3, "isoniazid": 3, "pyrazinamide": 3,
    "ethambutol": 3, "bedaquiline": 3, "delamanid": 3,
    "directly observed therapy": 3, "dots": 2,
    "sputum smear": 3, "sputum culture": 3, "acid-fast": 3,
    "interferon-gamma release assay": 3, "igra": 3,
    "tuberculin": 3, "mantoux": 3, "quantiferon": 3, "genexpert": 3,
    "xpert mtb": 3, "bcg": 2, "tb preventive therapy": 3,
    "tb contact": 2, "tb screening": 3, "tb notification": 3
  },
  "mesh_terms": {
    "Tuberculosis": 3, "Tuberculosis, Pulmonary": 3,
    "Mycobacterium tuberculosis": 3, "Latent Tuberculosis": 3,
    "Tuberculosis, Multidrug-Resistant": 3,
    "Tuberculosis, Miliary": 3, "Tuberculosis, Lymph Node": 3,
    "Antitubercular Agents": 3, "Isoniazid": 3, "Rifampin": 3,
    "Tuberculin Test": 3, "Interferon-gamma Release Tests": 3,
    "BCG Vaccine": 2, "Extensively Drug-Resistant Tuberculosis": 3
  },
  "blockers": []
}
```

---

## 4. Respiratory-tract infections

**Scope.** Infections of the upper and lower respiratory tract: influenza,
COVID-19/SARS-CoV-2, RSV, other coronaviruses, rhinovirus, parainfluenza, human
metapneumovirus, pertussis, community- and hospital-acquired pneumonia,
bronchiolitis, otitis media, pharyngitis, and pandemic/epidemic respiratory
preparedness.

**Not here.** Tuberculosis, even though it is a respiratory infection — it has
its own domain. Non-infectious respiratory disease (asthma, COPD) unless the
paper studies an infectious exacerbation.

**Overlap.** Ventilator-associated pneumonia scores in both this domain and
AMR/HAI, correctly; both are kept.

```json
{
  "domain_id": "rti",
  "label": "Respiratory-tract infections",
  "threshold": 4,
  "terms": {
    "influenza": 3, "h1n1": 3, "h3n2": 3, "h5n1": 3, "h7n9": 3,
    "avian influenza": 3, "pandemic influenza": 3, "influenza-like illness": 3,
    "covid-19": 3, "covid": 3, "sars-cov-2": 3, "sars-cov": 3, "sars": 2,
    "mers": 3, "mers-cov": 3, "coronavirus": 3, "long covid": 3,
    "respiratory syncytial virus": 3, "rsv": 3, "bronchiolitis": 3,
    "human metapneumovirus": 3, "parainfluenza": 3, "rhinovirus": 3,
    "adenovirus": 2, "enterovirus": 2,
    "pneumonia": 3, "community-acquired pneumonia": 3,
    "hospital-acquired pneumonia": 3, "ventilator-associated pneumonia": 3,
    "pneumococc*": 3, "streptococcus pneumoniae": 3,
    "haemophilus influenzae": 3, "legionell*": 3, "mycoplasma pneumoniae": 3,
    "pertussis": 3, "bordetella": 3, "diphtheria": 3,
    "acute respiratory infection": 3, "respiratory tract infection": 3,
    "upper respiratory": 3, "lower respiratory": 3,
    "pharyngitis": 3, "otitis media": 3, "sinusitis": 2, "croup": 3,
    "respiratory virus": 3, "influenza vaccin*": 3, "covid-19 vaccin*": 3,
    "mask": 1, "aerosol transmission": 2, "droplet transmission": 2
  },
  "mesh_terms": {
    "Influenza, Human": 3, "Influenza A Virus, H1N1 Subtype": 3,
    "Influenza Vaccines": 3, "COVID-19": 3, "SARS-CoV-2": 3,
    "COVID-19 Vaccines": 3, "Coronavirus Infections": 3,
    "Severe Acute Respiratory Syndrome": 3,
    "Respiratory Syncytial Virus Infections": 3,
    "Respiratory Syncytial Virus, Human": 3, "Bronchiolitis": 3,
    "Respiratory Tract Infections": 3, "Pneumonia": 3,
    "Pneumonia, Bacterial": 3, "Pneumonia, Viral": 3,
    "Pneumonia, Ventilator-Associated": 3,
    "Streptococcus pneumoniae": 3, "Pneumococcal Vaccines": 3,
    "Whooping Cough": 3, "Otitis Media": 3, "Pharyngitis": 3,
    "Common Cold": 2, "Metapneumovirus": 3, "Legionellosis": 3
  },
  "blockers": ["tuberculosis"]
}
```

---

## 5. Antimicrobial resistance and other healthcare-associated infections

**Scope.** Antimicrobial resistance in any organism, antimicrobial stewardship,
antibiotic prescribing and consumption, and healthcare-associated infection:
CLABSI, CAUTI, surgical site infection, *C. difficile*, MRSA, VRE, CRE, CRAB,
ESBL producers, *Candida auris*, hospital outbreak investigation, infection
prevention and control, and hand hygiene.

**Not here.** Antimicrobial pharmacology with no resistance or stewardship
framing. Community-acquired infection with no resistance angle.

**Overlap.** MDR-TB overlaps Tuberculosis; VAP overlaps Respiratory. Kept in both.

```json
{
  "domain_id": "amr_hai",
  "label": "AMR and healthcare-associated infections",
  "threshold": 4,
  "terms": {
    "antimicrobial resistance": 3, "antibiotic resistance": 3,
    "antibiotic-resistant": 3, "antimicrobial-resistant": 3,
    "multidrug-resistant": 3, "multi-drug resistant": 3, "mdro": 3,
    "extensively drug-resistant": 3, "pan-drug resistant": 3,
    "carbapenem-resistant": 3, "carbapenemase": 3, "cre": 2, "crab": 2,
    "extended-spectrum beta-lactamase": 3, "esbl": 3,
    "methicillin-resistant": 3, "mrsa": 3, "vancomycin-resistant": 3,
    "vre": 2, "colistin resistance": 3, "mcr-1": 3,
    "antimicrobial stewardship": 3, "antibiotic stewardship": 3,
    "antibiotic prescribing": 3, "antibiotic consumption": 3,
    "antibiogram": 3, "minimum inhibitory concentration": 2,
    "resistance gene": 3, "resistome": 3, "plasmid-mediated resistance": 3,
    "healthcare-associated infection": 3, "hospital-acquired infection": 3,
    "nosocomial": 3, "device-associated infection": 3,
    "central line-associated": 3, "clabsi": 3, "bloodstream infection": 2,
    "catheter-associated urinary": 3, "cauti": 3,
    "surgical site infection": 3, "ssi": 2,
    "clostridioides difficile": 3, "clostridium difficile": 3,
    "c. difficile": 3, "candida auris": 3,
    "acinetobacter baumannii": 3, "pseudomonas aeruginosa": 2,
    "klebsiella pneumoniae": 2, "enterococcus faecium": 2,
    "infection prevention": 3, "infection control": 3, "hand hygiene": 3,
    "environmental cleaning": 2, "hospital outbreak": 3,
    "contact precautions": 3, "decolonisation": 2, "decolonization": 2
  },
  "mesh_terms": {
    "Drug Resistance, Bacterial": 3, "Drug Resistance, Microbial": 3,
    "Drug Resistance, Multiple, Bacterial": 3,
    "Anti-Bacterial Agents": 2, "Antimicrobial Stewardship": 3,
    "Methicillin-Resistant Staphylococcus aureus": 3,
    "Vancomycin-Resistant Enterococci": 3,
    "Carbapenem-Resistant Enterobacteriaceae": 3, "beta-Lactamases": 3,
    "Cross Infection": 3, "Infection Control": 3, "Hand Hygiene": 3,
    "Catheter-Related Infections": 3, "Surgical Wound Infection": 3,
    "Clostridioides difficile": 3, "Clostridium Infections": 3,
    "Candida auris": 3, "Acinetobacter baumannii": 3,
    "Klebsiella pneumoniae": 2, "Disease Outbreaks": 1
  },
  "blockers": []
}
```

---

## Fallback: `other_id`

An included record matching no domain is tagged `other_id` and kept in the
dataset. Review `classification/unassigned.jsonl` each run: a recurring theme
there (hepatitis, dengue-adjacent arboviruses, enteric disease, vaccine-
preventable childhood disease) is a signal either to add terms above or to
propose a sixth domain to the user.
