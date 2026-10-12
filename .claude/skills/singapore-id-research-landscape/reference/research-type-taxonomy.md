# Research-type taxonomy

A cross-cutting classification, orthogonal to domain and sub-domain: **what
kind of research is this**, regardless of which disease it studies. This
drives the "Types of research" bar chart. A publication commonly carries
several types at once (a genomic surveillance paper is both `genomics` and
`surveillance_epidemiology`) — unlike domain/sub-domain, there is no single
"primary" type; the bar chart counts each assigned type once, so totals across
types exceed the publication count. That is expected, not a bug.

`classify.py` reads the fenced `json` blocks below at runtime and scores every
**included** record against all of them (not scoped to a domain). Add, edit or
retune a block to change classification, no code change needed.

The sixteen types below mirror the reference dashboard's "Types of research"
chart. Add a type here if a recurring theme in your corpus does not fit any of
them — check `classification/unassigned_research_type.jsonl` after a run
(records assigned zero types) for candidates.

```json
{"type_id": "basic_research", "label": "Basic research", "threshold": 3,
 "terms": {"mechanism": 1, "in vitro": 2, "cell culture": 2, "animal model": 2,
           "mouse model": 2, "molecular mechanism": 3, "signalling pathway": 2,
           "signaling pathway": 2, "host-pathogen interaction": 3,
           "structural biology": 3, "crystal structure": 3, "gene expression": 2},
 "mesh_terms": {"Host-Pathogen Interactions": 3, "Signal Transduction": 2},
 "blockers": []}
```

```json
{"type_id": "case_study", "label": "Case study", "threshold": 3,
 "terms": {"case report": 3, "case series": 3, "we describe a case": 2,
           "we report a case": 2, "a case of": 2},
 "mesh_terms": {},
 "blockers": []}
```

```json
{"type_id": "clinical_studies", "label": "Clinical studies", "threshold": 3,
 "terms": {"randomised controlled trial": 3, "randomized controlled trial": 3,
           "clinical trial": 3, "cohort study": 2, "case-control study": 2,
           "cross-sectional study": 1, "clinical outcome": 2, "clinical severity": 2,
           "hospitalisation": 1, "hospitalization": 1, "patient outcome": 2},
 "mesh_terms": {"Clinical Trial": 3, "Cohort Studies": 2, "Case-Control Studies": 2,
               "Randomized Controlled Trial": 3},
 "blockers": []}
```

```json
{"type_id": "detection", "label": "Detection", "threshold": 3,
 "terms": {"diagnostic assay": 3, "rapid diagnostic test": 3, "pcr assay": 2,
           "point-of-care test": 3, "sensitivity and specificity": 2,
           "diagnostic accuracy": 3, "biomarker": 2, "detection method": 3,
           "novel assay": 2, "elisa": 2},
 "mesh_terms": {"Diagnostic Tests, Routine": 2, "Sensitivity and Specificity": 2,
               "Point-of-Care Testing": 3},
 "blockers": []}
```

```json
{"type_id": "disease_management", "label": "Disease management", "threshold": 3,
 "terms": {"clinical management": 3, "case management": 3, "care pathway": 2,
           "clinical guideline": 2, "patient management": 2,
           "management protocol": 2, "supportive care": 2},
 "mesh_terms": {"Disease Management": 3},
 "blockers": []}
```

```json
{"type_id": "entomology", "label": "Entomology", "threshold": 3,
 "terms": {"entomolog*": 3, "mosquito*": 2, "aedes": 2, "anopheles": 2,
           "culex": 2, "vector competence": 3, "larval habitat": 3,
           "insecticide resistance": 2, "gravitrap": 3, "vectorial capacity": 3,
           "tick": 2, "sandfly": 2},
 "mesh_terms": {"Mosquito Vectors": 2, "Insect Vectors": 2, "Aedes": 2, "Anopheles": 2},
 "blockers": []}
```

```json
{"type_id": "genomics", "label": "Genomics", "threshold": 3,
 "terms": {"genomic*": 2, "whole genome sequencing": 3, "phylogenetic": 3,
           "phylogenomic": 3, "genome-wide": 3, "sequencing": 1,
           "genotyp*": 2, "sequence analysis": 2, "lineage": 1, "clade": 1,
           "single nucleotide polymorphism": 2, "snp": 1, "resistome": 2},
 "mesh_terms": {"Genome, Viral": 3, "Genome, Bacterial": 3, "Phylogeny": 3,
               "Whole Genome Sequencing": 3, "Genomics": 3},
 "blockers": []}
```

```json
{"type_id": "immunology", "label": "Immunology", "threshold": 3,
 "terms": {"immune response": 3, "antibody response": 3, "t-cell response": 3,
           "seroconversion": 2, "immunogenicity": 3, "cytokine": 2,
           "cellular immunity": 3, "humoral immunity": 3, "neutralising antibody": 3,
           "neutralizing antibody": 3, "immune correlate": 3},
 "mesh_terms": {"Antibodies, Viral": 2, "Immunity, Cellular": 3,
               "Immunity, Humoral": 3, "Antibody Formation": 2},
 "blockers": []}
```

```json
{"type_id": "infection_prevention_control", "label": "Infection prevention and control", "threshold": 3,
 "terms": {"infection prevention": 3, "infection control": 3, "hand hygiene": 3,
           "contact precautions": 3, "environmental cleaning": 2,
           "personal protective equipment": 2, "isolation precautions": 3},
 "mesh_terms": {"Infection Control": 3, "Hand Hygiene": 3},
 "blockers": []}
```

```json
{"type_id": "modelling", "label": "Modelling", "threshold": 3,
 "terms": {"mathematical model": 3, "transmission model": 3, "simulation": 2,
           "compartmental model": 3, "agent-based model": 3, "sir model": 3,
           "seir model": 3, "reproduction number": 3, "r0": 1,
           "forecasting model": 3, "predictive model": 2, "spatiotemporal model": 3},
 "mesh_terms": {"Models, Theoretical": 2, "Basic Reproduction Number": 3,
               "Epidemiological Models": 3},
 "blockers": []}
```

```json
{"type_id": "outbreak_management", "label": "Outbreak management", "threshold": 3,
 "terms": {"outbreak investigation": 3, "outbreak response": 3,
           "cluster investigation": 3, "contact tracing": 3,
           "outbreak control": 3, "index case": 2},
 "mesh_terms": {"Disease Outbreaks": 2, "Contact Tracing": 3},
 "blockers": []}
```

```json
{"type_id": "surveillance_epidemiology", "label": "Surveillance and epidemiology", "threshold": 3,
 "terms": {"surveillance": 3, "epidemiolog*": 2, "incidence": 1, "prevalence": 1,
           "notification data": 2, "seroprevalence": 2, "sentinel surveillance": 3,
           "case notification": 2, "descriptive epidemiology": 3, "trend analysis": 1},
 "mesh_terms": {"Epidemiological Monitoring": 3, "Population Surveillance": 3,
               "Sentinel Surveillance": 3, "Incidence": 1, "Prevalence": 1},
 "blockers": []}
```

```json
{"type_id": "transmission", "label": "Transmission", "threshold": 3,
 "terms": {"transmission dynamics": 3, "transmission route": 3,
           "human-to-human transmission": 3, "vector-borne transmission": 2,
           "airborne transmission": 3, "droplet transmission": 3,
           "aerosol transmission": 3, "secondary attack rate": 3,
           "chain of transmission": 3},
 "mesh_terms": {"Disease Transmission, Infectious": 3},
 "blockers": []}
```

```json
{"type_id": "treatment", "label": "Treatment", "threshold": 3,
 "terms": {"treatment outcome": 2, "antiviral therapy": 3, "antibiotic therapy": 2,
           "drug regimen": 3, "therapeutic efficacy": 3, "dosing regimen": 3,
           "adverse drug reaction": 2, "treatment guideline": 2, "chemotherapy": 1},
 "mesh_terms": {"Treatment Outcome": 2, "Drug Therapy": 2, "Antiviral Agents": 2,
               "Anti-Bacterial Agents": 1},
 "blockers": []}
```

```json
{"type_id": "vaccine", "label": "Vaccine", "threshold": 3,
 "terms": {"vaccine efficacy": 3, "vaccine effectiveness": 3, "vaccination": 2,
           "immunisation programme": 3, "immunization program": 3,
           "vaccine hesitancy": 3, "vaccine uptake": 3, "booster dose": 2,
           "vaccine trial": 3, "live attenuated vaccine": 3, "mrna vaccine": 3},
 "mesh_terms": {"Vaccines": 2, "Vaccination": 2, "Vaccine Efficacy": 3,
               "Immunization Programs": 3},
 "blockers": []}
```

```json
{"type_id": "virology", "label": "Virology", "threshold": 3,
 "terms": {"viral replication": 3, "viral load": 2, "virus isolation": 3,
           "viral evolution": 3, "viral fitness": 3, "receptor binding": 3,
           "viral entry": 3, "cell tropism": 3, "plaque assay": 3},
 "mesh_terms": {"Virus Replication": 3, "Viral Load": 2, "Virus Internalization Process": 3},
 "blockers": []}
```
