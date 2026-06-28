"""
Hardcoded medicine database.
Keys must match the reference image filename (without extension).
Example: reference_images/paracetamol.jpg → key "paracetamol"
"""

from typing import TypedDict


class Medicine(TypedDict):
    name: str
    generic_name: str
    category: str
    dosage_form: str
    strength: str
    manufacturer: str
    description: str
    warnings: str


MEDICINES: dict[str, Medicine] = {
    "paracetamol": {
        "name": "Paracetamol",
        "generic_name": "Acetaminophen",
        "category": "Analgesic / Antipyretic",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Used to treat pain and reduce fever.",
        "warnings": "Do not exceed 4g/day. Avoid alcohol.",
    },
    "amoxicillin": {
        "name": "Amoxicillin",
        "generic_name": "Amoxicillin",
        "category": "Antibiotic",
        "dosage_form": "Capsule",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Broad-spectrum penicillin antibiotic.",
        "warnings": "Check for penicillin allergy before use.",
    },
    "ibuprofen": {
        "name": "Ibuprofen",
        "generic_name": "Ibuprofen",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "400 mg",
        "manufacturer": "Generic",
        "description": "Reduces inflammation, pain, and fever.",
        "warnings": "Take with food. Avoid if history of ulcers.",
    },
    "metformin": {
        "name": "Metformin",
        "generic_name": "Metformin HCl",
        "category": "Antidiabetic",
        "dosage_form": "Tablet",
        "strength": "850 mg",
        "manufacturer": "Generic",
        "description": "First-line treatment for type 2 diabetes.",
        "warnings": "Monitor renal function. Avoid with contrast dye.",
    },
    "omeprazole": {
        "name": "Omeprazole",
        "generic_name": "Omeprazole",
        "category": "Proton Pump Inhibitor",
        "dosage_form": "Capsule",
        "strength": "20 mg",
        "manufacturer": "Generic",
        "description": "Reduces stomach acid. Used for GERD and ulcers.",
        "warnings": "Long-term use may reduce magnesium levels.",
    },
    "atorvastatin": {
        "name": "Atorvastatin",
        "generic_name": "Atorvastatin Calcium",
        "category": "Statin / Lipid-lowering",
        "dosage_form": "Tablet",
        "strength": "20 mg",
        "manufacturer": "Generic",
        "description": "Lowers LDL cholesterol and triglycerides.",
        "warnings": "Report muscle pain immediately. Avoid grapefruit.",
    },
    "amlodipine": {
        "name": "Amlodipine",
        "generic_name": "Amlodipine Besylate",
        "category": "Calcium Channel Blocker",
        "dosage_form": "Tablet",
        "strength": "5 mg",
        "manufacturer": "Generic",
        "description": "Treats hypertension and angina.",
        "warnings": "May cause ankle swelling and facial flushing.",
    },
    "azithromycin": {
        "name": "Azithromycin",
        "generic_name": "Azithromycin",
        "category": "Antibiotic (Macrolide)",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Treats respiratory, skin, and ear infections.",
        "warnings": "Risk of cardiac arrhythmia in susceptible patients.",
    },
    "lisinopril": {
        "name": "Lisinopril",
        "generic_name": "Lisinopril",
        "category": "ACE Inhibitor",
        "dosage_form": "Tablet",
        "strength": "10 mg",
        "manufacturer": "Generic",
        "description": "Treats hypertension and heart failure.",
        "warnings": "Avoid in pregnancy. Monitor potassium levels.",
    },
    "cetirizine": {
        "name": "Cetirizine",
        "generic_name": "Cetirizine HCl",
        "category": "Antihistamine",
        "dosage_form": "Tablet",
        "strength": "10 mg",
        "manufacturer": "Generic",
        "description": "Relieves allergy symptoms and urticaria.",
        "warnings": "May cause drowsiness. Avoid driving if affected.",
    },
    "cataflam": {
        "name": "Cataflam",
        "generic_name": "Diclofenac Potassium",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "50 mg",
        "manufacturer": "Novartis",
        "description": "Relieves pain and inflammation. Used for arthritis, dysmenorrhea, and acute injuries.",
        "warnings": "Avoid in peptic ulcer disease. Monitor renal function with long-term use.",

    },
    "levoxin": {
        "name": "Levoxin",
        "generic_name": "Levofloxacin",
        "category": "Antibiotic (Fluoroquinolone)",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Broad-spectrum antibiotic for respiratory, urinary tract, and skin infections.",
        "warnings": "Risk of tendon rupture. Avoid in children and pregnant women.",
    },
    "mebo": {
        "name": "MEBO",
        "generic_name": "Moist Exposed Burn Ointment",
        "category": "Dermatological / Wound Care",
        "dosage_form": "Ointment",
        "strength": "Topical",
        "manufacturer": "Shantou MEBO Pharmaceutical",
        "description": "Treats burns, wounds, and skin ulcers. Promotes moist wound healing.",
        "warnings": "For external use only. Do not apply to deep puncture wounds without medical advice.",
    },
    "coxritor": {
        "name": "Coxritor",
        "generic_name": "Moist Exposed Burn Ointment",
        "category": "Dermatological / Wound Care",
        "dosage_form": "Ointment",
        "strength": "Topical",
        "manufacturer": "Shantou MEBO Pharmaceutical",
        "description": "Treats burns, wounds, and skin ulcers. Promotes moist wound healing.",
        "warnings": "For external use only. Do not apply to deep puncture wounds without medical advice.",
    },
    "brufen": {
        "name": "Brufen",
        "generic_name": "Ibuprofen",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "200 mg",
        "manufacturer": "Shantou MEBO Pharmaceutical",
        "description": "Relieves pain and reduces inflammation.",
        "warnings": "Avoid in peptic ulcer disease. Monitor renal function with long-term use.",
    },
}


def get_medicine(key: str) -> Medicine | None:
    """Look up a medicine by its reference image key."""
    return MEDICINES.get(key.lower())


def list_all() -> list[str]:
    """Return all registered medicine keys."""
    return list(MEDICINES.keys())