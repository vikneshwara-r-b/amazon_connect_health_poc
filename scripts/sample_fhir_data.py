"""Sample FHIR R4 resources for the 3 demo patients already referenced in
backend/demo_cache/patients_default.json and backend/config.py's
DEMO_CACHE_PATIENT_A/B/C mapping.

Clinical content here is written to match the narratives already cached in
backend/demo_cache/patient_insights_*.json (each patient's pre-visit summary
JSON lists the exact conditions/medications/results it expects to see), so
that live HealthLake data and the cached demo-mode insights tell a consistent
clinical story for the same 3 patients. Codes are illustrative demo data, not
verified against a terminology server -- good enough for the Patient Insights
feature to have real material to summarize, not a source of medical truth.

One-off data-loading utility, not part of the CDK app or the backend service.
"""

PATIENTS = [
    {
        # Elena Rodriguez -- matches backend/demo_cache/patient_insights_0725e407.json
        "id": "0725e4075c0a604253ba23c24746cc8dea085e10cc6e9a51c309619a1d65137a",
        "given": "Elena",
        "family": "Rodriguez",
        "gender": "female",
        "birthDate": "1962-07-15",
        "conditions": [
            {
                "code": "239873007",
                "display": "Bilateral primary osteoarthritis of knee",
                "onset": "2019-04-10",
            },
            {
                "code": "414916001",
                "display": "Morbid obesity due to excess calories",
                "onset": "2019-04-10",
            },
            {
                "code": "78275009",
                "display": "Obstructive sleep apnea",
                "onset": "2024-09-20",
            },
            {
                "code": "55822004",
                "display": "Hyperlipidemia, unspecified",
                "onset": "2025-07-18",
            },
            {
                "code": "59621000",
                "display": "Essential hypertension",
                "onset": "2025-11-01",
            },
            {
                "code": "48440000",
                "display": "Arthropathic psoriasis, unspecified",
                "onset": "2022-06-01",
            },
            {
                "code": "198436008",
                "display": "Asymptomatic menopausal state",
                "onset": "2021-01-01",
            },
        ],
        "observations": [
            {"category": "vital-signs", "code": "8480-6", "display": "Systolic blood pressure",
             "date": "2025-11-01", "value": 145, "unit": "mmHg", "ucum": "mm[Hg]"},
            {"category": "vital-signs", "code": "29463-7", "display": "Body weight",
             "date": "2025-11-01", "value": 299.8, "unit": "lbs", "ucum": "[lb_av]"},
            {"category": "vital-signs", "code": "8480-6", "display": "Systolic blood pressure",
             "date": "2024-07-20", "value": 139, "unit": "mmHg", "ucum": "mm[Hg]"},
            {"category": "vital-signs", "code": "29463-7", "display": "Body weight",
             "date": "2024-07-20", "value": 297, "unit": "lbs", "ucum": "[lb_av]"},
            {"category": "vital-signs", "code": "8480-6", "display": "Systolic blood pressure",
             "date": "2024-01-13", "value": 151, "unit": "mmHg", "ucum": "mm[Hg]"},
            {"category": "laboratory", "code": "718-7", "display": "Hemoglobin",
             "date": "2025-07-19", "value": 15.4, "unit": "g/dL", "ucum": "g/dL"},
            {"category": "laboratory", "code": "4544-3", "display": "Hematocrit",
             "date": "2025-07-19", "value": 47.4, "unit": "%", "ucum": "%"},
            {"category": "laboratory", "code": "2345-7", "display": "Glucose",
             "date": "2025-07-19", "value": 120, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "2160-0", "display": "Creatinine",
             "date": "2025-07-19", "value": 0.84, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "62238-1", "display": "Estimated GFR",
             "date": "2025-07-19", "value": 82, "unit": "mL/min/1.73m2", "ucum": "mL/min/{1.73_m2}"},
            {"category": "laboratory", "code": "1742-6", "display": "ALT",
             "date": "2025-07-19", "value": 25, "unit": "U/L", "ucum": "U/L"},
            {"category": "laboratory", "code": "1920-8", "display": "AST",
             "date": "2025-07-19", "value": 20, "unit": "U/L", "ucum": "U/L"},
            {"category": "laboratory", "code": "2075-0", "display": "Chloride",
             "date": "2025-07-19", "value": 112, "unit": "mmol/L", "ucum": "mmol/L"},
            {"category": "laboratory", "code": "2028-9", "display": "CO2 total",
             "date": "2025-07-19", "value": 19, "unit": "mmol/L", "ucum": "mmol/L"},
            {"category": "laboratory", "code": "2093-3", "display": "Total Cholesterol",
             "date": "2024-10-11", "value": 174, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "13457-7", "display": "LDL Cholesterol (calculated)",
             "date": "2024-10-11", "value": 90, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "2085-9", "display": "HDL Cholesterol",
             "date": "2024-10-11", "value": 53, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "2571-8", "display": "Triglycerides",
             "date": "2024-10-11", "value": 185, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "3016-3", "display": "TSH",
             "date": "2024-10-11", "value": 1.373, "unit": "uIU/mL", "ucum": "u[IU]/mL"},
            {"category": "laboratory", "code": "62292-8", "display": "Vitamin D, 25-hydroxy total",
             "date": "2024-10-11", "value": 33.3, "unit": "ng/mL", "ucum": "ng/mL"},
        ],
        "encounters": [
            {"date": "2025-11-01", "reason": "Urgent care visit for right lower eyelid swelling"},
            {"date": "2025-01-14", "reason": "Polysomnography with CPAP titration"},
            {"date": "2024-09-20", "reason": "Initial diagnostic sleep study"},
        ],
        "medications": [
            {"code": "310965", "display": "Erythromycin 5 MG/GM Ophthalmic Ointment",
             "authored": "2025-11-01"},
            {"code": "259255", "display": "Atorvastatin 10 MG Oral Tablet",
             "authored": "2025-07-18"},
            {"code": "1719286", "display": "Clobetasol Propionate 0.05% Topical Cream",
             "authored": "2022-06-01"},
            {"code": "310385", "display": "Fluoxetine 40 MG Oral Capsule",
             "authored": "2021-01-01"},
            {"code": "895664", "display": "Fluticasone Propionate 50 MCG/ACTUAT Nasal Spray",
             "authored": "2021-01-01"},
            {"code": "857006", "display": "Hydrocodone-Acetaminophen 7.5-325 MG Oral Tablet",
             "authored": "2025-11-01"},
            {"code": "402873", "display": "Omeprazole 40 MG Oral Capsule",
             "authored": "2025-07-18"},
        ],
    },
    {
        # Diego Ramirez -- matches backend/demo_cache/patient_insights_46383dd7.json
        "id": "46383dd73c1d282831d3e7c9101d4901497c32345d4e2fcc657c2eaf9d03830d",
        "given": "Diego",
        "family": "Ramirez",
        "gender": "male",
        "birthDate": "1985-11-22",
        "conditions": [
            {"code": "58150001", "display": "Periapical abscess without sinus",
             "onset": "2023-10-27"},
            {"code": "58150001", "display": "Periapical abscess without sinus (post-extraction)",
             "onset": "2023-11-01"},
            {"code": "263381003", "display": "Fracture of tooth, traumatic",
             "onset": "2023-10-27"},
            {"code": "80967001", "display": "Dental caries, unspecified",
             "onset": "2023-10-27"},
            {"code": "80967001", "display": "Dental caries, unspecified (follow-up)",
             "onset": "2023-11-01"},
            {"code": "281666001", "display": "Exposure to other specified factors",
             "onset": "2023-10-27"},
        ],
        "observations": [
            {"category": "vital-signs", "code": "8480-6", "display": "Systolic blood pressure",
             "date": "2023-11-01", "value": 115, "unit": "mmHg", "ucum": "mm[Hg]"},
            {"category": "vital-signs", "code": "8462-4", "display": "Diastolic blood pressure",
             "date": "2023-11-01", "value": 85, "unit": "mmHg", "ucum": "mm[Hg]"},
            {"category": "vital-signs", "code": "8867-4", "display": "Heart rate",
             "date": "2023-11-01", "value": 80, "unit": "bpm", "ucum": "/min"},
            {"category": "vital-signs", "code": "9279-1", "display": "Respiratory rate",
             "date": "2023-11-01", "value": 17, "unit": "breaths/min", "ucum": "/min"},
            {"category": "vital-signs", "code": "8310-5", "display": "Body temperature",
             "date": "2023-11-01", "value": 36, "unit": "Cel", "ucum": "Cel"},
            {"category": "vital-signs", "code": "59408-5", "display": "Oxygen saturation",
             "date": "2023-11-01", "value": 99, "unit": "%", "ucum": "%"},
            {"category": "vital-signs", "code": "29463-7", "display": "Body weight",
             "date": "2023-11-01", "value": 72.6, "unit": "kg", "ucum": "kg"},
            {"category": "vital-signs", "code": "8302-2", "display": "Body height",
             "date": "2023-11-01", "value": 180.3, "unit": "cm", "ucum": "cm"},
        ],
        "encounters": [
            {"date": "2023-11-01", "reason": "Oral and maxillofacial surgery follow-up"},
        ],
        "medications": [
            {"code": "308191", "display": "Amoxicillin-Clavulanate 875-125 MG Oral Tablet",
             "authored": "2023-10-27"},
            {"code": "197595", "display": "Chlorhexidine Gluconate 0.12% Oromucosal Solution",
             "authored": "2023-10-27"},
        ],
    },
    {
        # Marcia Oliveria -- matches backend/demo_cache/patient_insights_69834515.json
        "id": "698345153023e19306b525ad8a6c7eca0cfc22dfff2a21b51945d5175d6d18f2",
        "given": "Márcia",
        "family": "Oliveria",
        "gender": "female",
        "birthDate": "1963-03-08",
        "conditions": [
            {"code": "36328005", "display": "Idiopathic gout, right wrist", "onset": "2025-10-21"},
            {"code": "279039007", "display": "Pain in right wrist", "onset": "2025-11-13"},
            {"code": "125668008", "display": "Contusion of right upper arm", "onset": "2025-05-26"},
        ],
        "observations": [
            {"category": "laboratory", "code": "3084-1", "display": "Uric acid",
             "date": "2025-10-21", "value": 9.6, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "4537-7", "display": "Erythrocyte sedimentation rate",
             "date": "2025-10-21", "value": 30, "unit": "mm/h", "ucum": "mm/h"},
            {"category": "laboratory", "code": "1988-5", "display": "C-reactive protein",
             "date": "2025-10-21", "value": 0.34, "unit": "mg/dL", "ucum": "mg/dL"},
            {"category": "laboratory", "code": "718-7", "display": "Hemoglobin",
             "date": "2025-10-21", "value": 13.1, "unit": "g/dL", "ucum": "g/dL"},
            {"category": "laboratory", "code": "6690-2", "display": "White blood cell count",
             "date": "2025-10-21", "value": 9.0, "unit": "10*3/uL", "ucum": "10*3/uL"},
            {"category": "laboratory", "code": "14535-3", "display": "Rheumatoid factor",
             "date": "2025-10-22", "value": 10, "unit": "IU/mL", "ucum": "[IU]/mL"},
            {"category": "laboratory", "code": "5045-8", "display": "ANA by immunofluorescence",
             "date": "2025-10-24", "value": 0, "unit": "negative", "ucum": "1"},
            {"category": "laboratory", "code": "56964-8", "display": "CCP antibodies IgG/IgA",
             "date": "2025-10-24", "value": 6, "unit": "U", "ucum": "U"},
        ],
        "encounters": [
            {"date": "2025-10-06", "reason": "Right wrist pain and swelling evaluation"},
            {"date": "2025-05-26", "reason": "Right upper arm contusion after a fall"},
            {"date": "2025-10-24", "reason": "Right wrist pain follow-up evaluation"},
        ],
        "medications": [
            {"code": "2417057", "display": "Colchicine 0.6 MG Oral Tablet", "authored": "2025-10-21"},
            {"code": "861634", "display": "Atorvastatin 80 MG Oral Tablet", "authored": "2024-01-01"},
            {"code": "857169", "display": "Carvedilol 12.5 MG Oral Tablet", "authored": "2024-01-01"},
            {"code": "309362", "display": "Clopidogrel 75 MG Oral Tablet", "authored": "2024-01-01"},
            {"code": "997223", "display": "Lisinopril-Hydrochlorothiazide 20-25 MG Oral Tablet",
             "authored": "2024-01-01"},
            {"code": "1551291", "display": "Dulaglutide (Trulicity) 1.5 MG/0.5 ML Subcutaneous Injection",
             "authored": "2024-01-01"},
            {"code": "243670", "display": "Aspirin 81 MG Oral Tablet", "authored": "2024-01-01"},
            {"code": "351772", "display": "Latanoprost 0.005% Ophthalmic Solution", "authored": "2024-01-01"},
            {"code": "857232", "display": "Dorzolamide-Timolol 2-0.5% Ophthalmic Solution",
             "authored": "2024-01-01"},
            {"code": "349199", "display": "Brimonidine 0.2% Ophthalmic Solution", "authored": "2024-01-01"},
        ],
    },
]


def patient_resource(p: dict) -> dict:
    return {
        "resourceType": "Patient",
        "id": p["id"],
        "name": [{"use": "official", "given": [p["given"]], "family": p["family"]}],
        "gender": p["gender"],
        "birthDate": p["birthDate"],
    }


def condition_resources(p: dict) -> list[dict]:
    return [
        {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }
                ]
            },
            "verificationStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": "confirmed",
                    }
                ]
            },
            "code": {
                "coding": [
                    {"system": "http://snomed.info/sct", "code": c["code"], "display": c["display"]}
                ],
                "text": c["display"],
            },
            "subject": {"reference": f"Patient/{p['id']}"},
            "onsetDateTime": c["onset"],
        }
        for c in p["conditions"]
    ]


def observation_resources(p: dict) -> list[dict]:
    return [
        {
            "resourceType": "Observation",
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": o["category"],
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": o["code"], "display": o["display"]}
                ],
                "text": o["display"],
            },
            "subject": {"reference": f"Patient/{p['id']}"},
            "effectiveDateTime": o["date"],
            "valueQuantity": {
                "value": o["value"],
                "unit": o["unit"],
                "system": "http://unitsofmeasure.org",
                "code": o["ucum"],
            },
        }
        for o in p["observations"]
    ]


def encounter_resources(p: dict) -> list[dict]:
    return [
        {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            },
            "type": [
                {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "185349003",
                            "display": "Encounter for check up",
                        }
                    ],
                    "text": e["reason"],
                }
            ],
            "subject": {"reference": f"Patient/{p['id']}"},
            "period": {"start": f"{e['date']}T09:00:00Z", "end": f"{e['date']}T09:30:00Z"},
        }
        for e in p["encounters"]
    ]


def medication_request_resources(p: dict) -> list[dict]:
    return [
        {
            "resourceType": "MedicationRequest",
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": m["code"],
                        "display": m["display"],
                    }
                ],
                "text": m["display"],
            },
            "subject": {"reference": f"Patient/{p['id']}"},
            "authoredOn": m["authored"],
        }
        for m in p["medications"]
    ]
