#!/usr/bin/env python3
"""Generate a synthetic raw/ directory that mirrors the PubMed connector's
response shape, for exercising the pipeline without network access.

Two records (PMIDs 42685738 and 41586636) are REAL, copied verbatim from the
connector so the fixture stays honest about the schema. Every other record is
SYNTHETIC: PMIDs in the 99xxxxxx range and DOIs under the invalid 10.9999/
prefix, chosen so fixture rows can never be mistaken for real publications.

    python3 tests/make_fixture.py --run-dir runs/fixture
"""

import argparse
import json
import os

SG_SGH = "Singapore General Hospital, Singapore; Duke-NUS Medical School, Singapore."
SG_NCID = "National Centre for Infectious Diseases, Singapore; Tan Tock Seng Hospital, Singapore."
SG_NUS = "Saw Swee Hock School of Public Health, National University of Singapore, Singapore."
SG_NTU = "Lee Kong Chian School of Medicine, Nanyang Technological University, Singapore."
UK = "London School of Hygiene & Tropical Medicine, London, UK."
US = "Bloomberg School of Public Health, Johns Hopkins University, Baltimore, MD, USA."
MY = "Department of Medicine, University of Malaya, Kuala Lumpur, Malaysia."


def A(last, fore, initials, affs):
    return {"last_name": last, "fore_name": fore, "initials": initials, "affiliations": affs}


def art(pmid, title, abstract, authors, year, journal="Journal of Fixture Medicine",
        types=None, lang="eng", mesh=None, keywords=None, doi=None, pmc=None):
    rec = {
        "identifiers": {"pmid": pmid, "doi": doi or "10.9999/fixture.%s" % pmid},
        "title": title,
        "abstract": abstract,
        "doi": doi or "10.9999/fixture.%s" % pmid,
        "journal": {"title": journal, "iso_abbreviation": journal[:20]},
        "authors": authors,
        "publication_date": {"year": str(year), "month": "06", "day": "01"},
        "article_types": types or ["Journal Article"],
        "language": lang,
        "citation": {"volume": "1", "issue": "1", "pages": "1-10"},
    }
    if pmc:
        rec["identifiers"]["pmc"] = pmc
    if mesh:
        rec["mesh_terms"] = mesh
    if keywords:
        rec["keywords"] = keywords
    return rec


REAL_DENGUE_WHO = {
    "identifiers": {"pmid": "42685738", "doi": "10.1016/j.lanmic.2026.101451",
                    "pii": "S2666-5247(26)00106-0"},
    "title": "Accelerating the clinical development of treatments for dengue: WHO dengue therapeutics landscape analysis and target product profiles.",
    "abstract": "Dengue, an Aedes mosquito-borne viral infection, is on the rise with climate and demographic change. In 2023, WHO declared dengue its highest grade of emergency. To accelerate development of dengue-specific treatments, WHO conducted a landscape analysis of the dengue therapeutics pipeline and developed target product profiles for treatments for non-severe and severe dengue.",
    "doi": "10.1016/j.lanmic.2026.101451",
    "journal": {"title": "The Lancet. Microbe", "iso_abbreviation": "Lancet Microbe"},
    "authors": [
        A("Chan", "Xin Hui S", "XHS", ["Malaria and Neglected Tropical Diseases Department, WHO, Geneva, Switzerland; Epidemic and Emerging Infections Directorate, UK Health Security Agency, London, UK. Electronic address: xinhui.chan@ukhsa.gov.uk."]),
        A("Durbin", "Anna P", "AP", [US]),
        A("Low", "Jenny G", "JG", ["Singapore General Hospital, Singapore; Duke-NUS Medical School, Singapore."]),
        A("Velayudhan", "Raman", "R", ["Malaria and Neglected Tropical Diseases Department, WHO, Geneva, Switzerland."]),
    ],
    "publication_date": {"year": "2027", "month": "05", "day": "19"},
    "article_types": ["Journal Article", "Review"],
    "language": "eng",
    "citation": {"pages": "101451"},
}

REAL_TAKEDA_KAP = {
    "identifiers": {"pmid": "41586636", "pmc": "PMC12851392", "doi": "10.1080/21645515.2025.2593730"},
    "title": "Dengue vaccination Knowledge, Attitudes, and Practices among healthcare providers in selected countries from Latin America and Asia Pacific.",
    "abstract": "Healthcare professionals perform an essential role in facilitating dengue vaccine uptake. A cross-sectional survey of 815 HCPs in Argentina, Brazil, Colombia, Indonesia, Malaysia, and Thailand was conducted.",
    "doi": "10.1080/21645515.2025.2593730",
    "journal": {"title": "Human vaccines & immunotherapeutics", "iso_abbreviation": "Hum Vaccin Immunother"},
    "authors": [
        A("Lopez-Medina", "Eduardo", "E", ["Centro de Estudios en Infectologia Pediatrica CEIP, Cali, Colombia."]),
        A("Di Pasquale", "Alberta", "A", ["Regional Medical Affairs, Growth and Emerging Markets, Takeda Pharmaceuticals International AG Singapore Branch, Singapore, Singapore."]),
        A("Green", "Andrew", "A", ["Regional Medical Affairs, Growth and Emerging Markets, Takeda Pharmaceuticals International AG Singapore Branch, Singapore, Singapore."]),
    ],
    "publication_date": {"year": "2026", "month": "01", "day": "26"},
    "keywords": ["Arboviruses", "Dengue", "vaccines"],
    "mesh_terms": ["Humans", "Dengue Vaccines", "Dengue", "Thailand", "Malaysia"],
    "article_types": ["Journal Article"],
    "language": "eng",
    "citation": {"volume": "22", "issue": "1", "pages": "2593730"},
}

FIXTURES = {
    # query_id -> [articles]
    "geo_vector_borne": [
        REAL_DENGUE_WHO,
        REAL_TAKEDA_KAP,
        art("99000001",
            "Spatiotemporal clustering of dengue transmission in Singapore, 2015-2024.",
            "We analysed 120,000 notified dengue cases in Singapore using Aedes aegypti Gravitrap surveillance data to identify transmission clusters and evaluate vector control interventions.",
            [A("Tan", "Wei Ming", "WM", [SG_NUS]), A("Lim", "Siew Hoon", "SH", ["Environmental Health Institute, National Environment Agency, Singapore."]),
             A("Chen", "Li", "L", [SG_NTU])],
            2024, mesh=["Dengue", "Aedes", "Mosquito Control", "Singapore"],
            keywords=["dengue", "vector control"], pmc="PMC9000001"),
        art("99000002",
            "Wolbachia-mediated suppression of Aedes aegypti populations in a high-rise urban setting.",
            "A cluster-randomised release of Wolbachia-infected male Aedes aegypti was conducted across residential blocks. Vector competence and Breteau index were assessed over 24 months.",
            [A("Ng", "Li Fang", "LF", ["Environmental Health Institute, National Environment Agency, Singapore."]),
             A("Rahman", "Nurul", "N", [SG_NUS])],
            2023, mesh=["Aedes", "Wolbachia", "Mosquito Control"]),
    ],
    "geo_tb": [
        art("99000010",
            "Latent tuberculosis infection screening among migrant workers in Singapore: a cohort study.",
            "Interferon-gamma release assay screening was offered to 8,400 migrant workers. We report LTBI prevalence, isoniazid preventive therapy uptake and completion rates in the Singapore programme.",
            [A("Kumar", "Rajesh", "R", [SG_NCID]), A("Tan", "Boon Huat", "BH", [SG_NCID]),
             A("Wong", "Mei Yee", "MY", [SG_NUS])],
            2022, mesh=["Latent Tuberculosis", "Tuberculin Test", "Singapore"],
            keywords=["tuberculosis", "migrant health"], pmc="PMC9000010"),
        art("99000011",
            "Treatment outcomes of HIV-tuberculosis co-infection at a Singapore referral centre.",
            "Among 210 people living with HIV diagnosed with active tuberculosis, we assessed antiretroviral therapy timing, rifampicin-based regimens and 12-month mortality.",
            [A("Lee", "Chee Keong", "CK", [SG_NCID]), A("Fernandez", "Maria", "M", [SG_SGH])],
            2021, mesh=["Tuberculosis", "HIV Infections", "Coinfection"]),
    ],
    "geo_amr_hai": [
        art("99000020",
            "Carbapenem-resistant Enterobacterales bloodstream infections across Singapore public hospitals.",
            "A prospective surveillance study of carbapenemase-producing organisms and healthcare-associated bloodstream infection across seven acute-care hospitals, with antimicrobial stewardship implications.",
            [A("Chua", "Hui Ling", "HL", [SG_NCID]), A("Ibrahim", "Ahmad", "A", [SG_SGH]),
             A("Goh", "Kai Wen", "KW", ["Changi General Hospital, Singapore."])],
            2023, mesh=["Carbapenem-Resistant Enterobacteriaceae", "Cross Infection",
                        "Antimicrobial Stewardship"], pmc="PMC9000020"),
        art("99000021",
            "Hand hygiene compliance and MRSA acquisition in intensive care: a Singapore-UK comparison.",
            "We compared hand hygiene compliance, contact precautions and methicillin-resistant Staphylococcus aureus acquisition rates between intensive care units in Singapore and the United Kingdom.",
            [A("Smith", "Jane", "J", [UK]), A("Tan", "Hock Seng", "HS", [SG_NCID])],
            2020, mesh=["Hand Hygiene", "Methicillin-Resistant Staphylococcus aureus",
                        "Cross Infection"]),
    ],
    "geo_rti": [
        art("99000030",
            "SARS-CoV-2 transmission in migrant worker dormitories in Singapore.",
            "Genomic epidemiology of COVID-19 outbreaks in dormitory settings, combining SARS-CoV-2 whole genome sequencing with contact tracing data from the Singapore national response.",
            [A("Ong", "Wei Sheng", "WS", [SG_NCID]), A("Lim", "Jia Hui", "JH", [SG_NUS]),
             A("Prasad", "Anita", "A", [SG_NTU])],
            2021, mesh=["COVID-19", "SARS-CoV-2", "Disease Outbreaks", "Singapore"],
            pmc="PMC9000030"),
        art("99000031",
            "Ventilator-associated pneumonia caused by multidrug-resistant Acinetobacter baumannii.",
            "A retrospective cohort of ventilator-associated pneumonia in a Singapore tertiary intensive care unit, examining multidrug-resistant Acinetobacter baumannii and colistin resistance.",
            [A("Teo", "Yong Kang", "YK", [SG_SGH]), A("Ang", "Bee Choo", "BC", [SG_SGH])],
            2022, mesh=["Pneumonia, Ventilator-Associated", "Acinetobacter baumannii",
                        "Drug Resistance, Multiple, Bacterial"]),
        art("99000032",
            "Influenza vaccine effectiveness among older adults in Singapore polyclinics.",
            "Test-negative design study of influenza vaccine effectiveness across primary care polyclinics in Singapore over three seasons.",
            [A("Chong", "Mei Fang", "MF", [SG_NUS])],
            2019, mesh=["Influenza, Human", "Influenza Vaccines"]),
    ],
    "geo_sti": [
        art("99000040",
            "HIV pre-exposure prophylaxis uptake among men who have sex with men in Singapore.",
            "A community-based survey assessing awareness, uptake and adherence to pre-exposure prophylaxis among men who have sex with men, and barriers within Singapore sexual health services.",
            [A("Ho", "Kok Wai", "KW", ["National Skin Centre, Singapore."]),
             A("Lau", "Yi Ling", "YL", [SG_NUS])],
            2023, mesh=["HIV Infections", "Pre-Exposure Prophylaxis", "Homosexuality, Male"],
            pmc="PMC9000040"),
        art("99000041",
            "Neisseria gonorrhoeae antimicrobial susceptibility trends at a Singapore STI clinic.",
            "Ten-year surveillance of Neisseria gonorrhoeae isolates, reporting ceftriaxone and azithromycin minimum inhibitory concentration trends and implications for treatment guidelines.",
            [A("Ho", "Kok Wai", "KW", ["National Skin Centre, Singapore."]),
             A("Zainal", "Farid", "F", [SG_NCID])],
            2024, mesh=["Gonorrhea", "Neisseria gonorrhoeae", "Drug Resistance, Bacterial"]),
    ],
    "geo_all_id": [
        # duplicate of 99000010 arriving from another query, DOI-identical
        art("99000010",
            "Latent tuberculosis infection screening among migrant workers in Singapore: a cohort study.",
            "Interferon-gamma release assay screening was offered to 8,400 migrant workers. We report LTBI prevalence, isoniazid preventive therapy uptake and completion rates in the Singapore programme.",
            [A("Kumar", "Rajesh", "R", [SG_NCID]), A("Tan", "Boon Huat", "BH", [SG_NCID]),
             A("Wong", "Mei Yee", "MY", [SG_NUS])],
            2022, mesh=["Latent Tuberculosis", "Tuberculin Test", "Singapore"]),
        # editorial -> mechanical exclude
        art("99000050", "Singapore must invest more in outbreak preparedness.",
            "An editorial arguing for sustained investment in infectious disease preparedness.",
            [A("Lim", "Peter", "P", [SG_NUS])], 2023, types=["Editorial"]),
        # non-English -> mechanical exclude
        art("99000051", "Surveillance de la dengue a Singapour.",
            "Etude de la surveillance de la dengue.",
            [A("Dubois", "Marc", "M", ["Institut Pasteur, Paris, France."]), A("Tan", "Ah Seng", "AS", [SG_NUS])],
            2022, lang="fre"),
        # no abstract -> uncertain
        art("99000052", "Melioidosis in Singapore: a 20-year review.", "",
            [A("Sim", "Wee Kiat", "WK", [SG_NCID])], 2023),
        # Singapore only in abstract, no SG affiliation -> uncertain (INC-GEO-02)
        art("99000053",
            "Comparative effectiveness of typhoid conjugate vaccine in three Asian cities.",
            "We modelled typhoid conjugate vaccine impact using surveillance data from Dhaka, Kathmandu and Singapore, drawing on national notification systems.",
            [A("Rahman", "Aminul", "A", ["icddr,b, Dhaka, Bangladesh."]), A("Shrestha", "Bina", "B", ["Patan Academy of Health Sciences, Kathmandu, Nepal."])],
            2022, mesh=["Typhoid Fever", "Typhoid-Paratyphoid Vaccines"]),
        # Letter with data -> uncertain, NOT auto-excluded
        art("99000054",
            "Early detection of mpox clade Ib in a returning traveller, Singapore.",
            "We report laboratory-confirmed mpox in a returning traveller, with contact tracing outcomes and genomic characterisation.",
            [A("Yeo", "Chin Chuan", "CC", [SG_NCID])], 2024, types=["Letter"],
            mesh=["Mpox (monkeypox)"]),
        # hepatitis -> included but unassigned to the five domains
        art("99000055",
            "Hepatitis B surface antigen seroprevalence after two decades of universal infant vaccination in Singapore.",
            "A serosurvey of hepatitis B surface antigen and anti-HBs among Singapore residents, evaluating long-term universal infant vaccination programme impact.",
            [A("Chan", "Boon Leong", "BL", [SG_NUS])], 2023,
            mesh=["Hepatitis B", "Hepatitis B Vaccines"]),
        # entirely non-Singapore -> geography fail
        art("99000056",
            "Malaria vector control in the Peruvian Amazon.",
            "Anopheles darlingi larval habitat mapping and insecticide-treated net coverage in riverine communities of the Peruvian Amazon.",
            [A("Garcia", "Luis", "L", ["Universidad Peruana Cayetano Heredia, Lima, Peru."])],
            2023, mesh=["Malaria", "Anopheles"]),
        # single-patient case report -> uncertain per EXC-TYP-02
        art("99000057",
            "A case of disseminated Mycobacterium abscessus infection following cosmetic surgery.",
            "We describe a single patient who developed disseminated Mycobacterium abscessus infection. This case report highlights diagnostic challenges.",
            [A("Toh", "Wei Liang", "WL", [SG_SGH])], 2023, types=["Case Reports"]),
        # out of window (2027) handled via REAL_DENGUE_WHO; also a 2010 record
        art("99000058",
            "Chikungunya outbreak investigation in Singapore, 2008.",
            "Retrospective analysis of the 2008 chikungunya outbreak, including Aedes albopictus vector surveillance and case notification data.",
            [A("Koh", "Ser Mei", "SM", [SG_NUS])], 2010, mesh=["Chikungunya Fever"]),
    ],
}

SEARCH_TOTALS = {
    "geo_vector_borne": 1445, "geo_tb": 949, "geo_amr_hai": 1120,
    "geo_rti": 2310, "geo_sti": 640, "geo_all_id": 8800,
}

SCHOLAR = [
    {"title": "Dengue control programme evaluation in Singapore: a policy review",
     "authors_raw": "A Tan, B Lim", "year": "2021",
     "venue": "Singapore Journal of Public Health Practice",
     "url": "https://example.org/fixture/scholar1", "source": "scholar",
     "snippet": "A review of Singapore's national dengue control programme, covering vector surveillance and community engagement."},
    # a Scholar hit that duplicates a PubMed record by title
    {"title": "Spatiotemporal clustering of dengue transmission in Singapore, 2015-2024",
     "authors_raw": "WM Tan, SH Lim, L Chen", "year": "2024", "venue": "J Fixture Med",
     "url": "https://example.org/fixture/scholar2", "source": "scholar",
     "snippet": "We analysed notified dengue cases in Singapore."},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="runs/fixture")
    args = ap.parse_args()
    raw = os.path.join(args.run_dir, "raw")
    os.makedirs(raw, exist_ok=True)

    n = 0
    for qid, articles in FIXTURES.items():
        with open(os.path.join(raw, "pubmed_%s_1.json" % qid), "w", encoding="utf-8") as fh:
            json.dump({"articles": articles, "count": len(articles)}, fh, indent=2)
        n += len(articles)
        with open(os.path.join(raw, "pubmed_%s_0.json" % qid), "w", encoding="utf-8") as fh:
            json.dump({"pmids": [a["identifiers"]["pmid"] for a in articles],
                       "total_count": SEARCH_TOTALS.get(qid, len(articles)),
                       "returned_count": len(articles), "has_more": True}, fh, indent=2)

    with open(os.path.join(raw, "scholar_sch_vector_borne.jsonl"), "w", encoding="utf-8") as fh:
        for hit in SCHOLAR:
            fh.write(json.dumps(hit) + "\n")

    print("Fixture written to %s" % raw)
    print("  %d PubMed article records across %d queries" % (n, len(FIXTURES)))
    print("  %d Scholar leads" % len(SCHOLAR))
    print("  2 records are real (PMID 42685738, 41586636); the rest are synthetic")


if __name__ == "__main__":
    main()
