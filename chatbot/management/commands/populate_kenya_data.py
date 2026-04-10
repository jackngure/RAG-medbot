"""
Management command: populate_kenya_data
=======================================
Populates the database with Kenya-specific medical data:
  - Common tropical and non-communicable diseases
  - Symptom objects with local alternative names
  - First-aid procedures contextualised for Kenyan healthcare settings
  - Emergency keywords with appropriate severity levels

Usage
-----
    python manage.py populate_kenya_data            # interactive confirmation
    python manage.py populate_kenya_data --force    # skip confirmation prompt

Design decisions
----------------
* All data is wrapped in a single transaction so a mid-run failure leaves the
  database unchanged (full rollback).
* Deletion order respects M2M constraints: through-table rows are cleared before
  the parent Disease rows are removed, preventing orphan records.
* common_symptoms on each Disease is derived automatically from the linked
  Symptom objects (name + alternative_names), so the RAGRetriever's substring
  matching never drifts from the M2M links.
* Post-save cache invalidation signals are registered at the bottom of the
  module so they fire whenever Disease or FirstAidProcedure records change
  outside this command as well.
* Emergency phone numbers use Kenya's official numbers (999 / 112 / 0722 999 999).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from chatbot.models import Disease, EmergencyKeyword, FirstAidProcedure, Symptom

logger = logging.getLogger(__name__)

KENYA_EMERGENCY = "999 / 112"


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------

@dataclass
class SymptomSpec:
    key: str
    name: str
    alternative_names: str


@dataclass
class DiseaseSpec:
    key: str
    name: str
    description: str
    symptom_keys: List[str]


@dataclass
class FirstAidSpec:
    disease_key: str
    title: str
    steps: str
    warning_notes: str
    when_to_seek_help: str


@dataclass
class EmergencySpec:
    keyword: str
    severity: str
    response_message: str
    is_typo_variant: bool = False   # marks intentional spelling variants


# ---------------------------------------------------------------------------
# Symptom catalogue
# ---------------------------------------------------------------------------

SYMPTOM_CATALOGUE: List[SymptomSpec] = [
    SymptomSpec("fever",                    "fever",                    "high temperature, hot body, sweating, chills, feeling hot even when cold"),
    SymptomSpec("headache",                 "headache",                 "head pain, migraine, throbbing head, pressure in head"),
    SymptomSpec("cough",                    "cough",                    "coughing, dry cough, wet cough, chest cough, barking cough"),
    SymptomSpec("diarrhea",                 "diarrhea",                 "diarrhoea, loose stools, running stomach, watery stool, frequent bathroom, stomach running"),
    SymptomSpec("vomiting",                 "vomiting",                 "throwing up, nausea, sick stomach, can't keep food down"),
    SymptomSpec("fatigue",                  "fatigue",                  "tiredness, weakness, exhaustion, lethargy, no energy, body weak"),
    SymptomSpec("chest_pain",               "chest pain",               "chest discomfort, heart pain, tight chest, squeezing in chest"),
    SymptomSpec("difficulty_breathing",     "difficulty breathing",     "shortness of breath, breathlessness, can't breathe, breathing fast, wheezing"),
    SymptomSpec("joint_pain",               "joint pain",               "joint ache, arthritis, pain in joints, knees hurt, back pain"),
    SymptomSpec("muscle_pain",              "muscle pain",              "myalgia, body aches, sore muscles, whole body pain"),
    SymptomSpec("rash",                     "rash",                     "skin rash, red spots, itching, hives, skin bumps, scratching"),
    SymptomSpec("abdominal_pain",           "abdominal pain",           "stomach ache, belly pain, cramping, tummy hurts, stomach problems"),
    SymptomSpec("dehydration",              "dehydration",              "dry mouth, sunken eyes, reduced urine, thirsty, no tears, dark urine"),
    SymptomSpec("confusion",                "confusion",                "disoriented, altered mental state, delirium, not acting normal, confused mind"),
    SymptomSpec("burning_urination",        "burning urination",        "pain when passing urine, painful urination, burning sensation, urine burns"),
    SymptomSpec("frequent_urination",       "frequent urination",       "passing urine often, many times bathroom, can't hold urine"),
    SymptomSpec("blood_urine",              "blood in urine",           "red urine, bloody urine, pink urine, blood when passing urine"),
    SymptomSpec("lower_back_pain",          "lower back pain",          "backache, pain in lower back, kidney pain, spine hurts"),
    SymptomSpec("runny_nose",               "runny nose",               "running nose, nasal discharge, blocked nose, flu"),
    SymptomSpec("sneezing",                 "sneezing",                 "sneezing constantly, allergy sneezing"),
    SymptomSpec("sore_throat",              "sore throat",              "painful throat, throat pain, difficulty swallowing, swollen throat"),
    SymptomSpec("yellow_discharge",         "yellow discharge",         "pus from wound, infected wound, yellow fluid, wound oozing"),
    SymptomSpec("swelling",                 "swelling",                 "swollen body part, edema, puffy, inflamed"),
    SymptomSpec("redness",                  "redness",                  "red skin, inflamed skin, hot skin"),
    SymptomSpec("wound",                    "wound",                    "cut, injury, sore, ulcer, broken skin, open wound"),
    SymptomSpec("high_bp_symptoms",         "high blood pressure symptoms", "severe headache, blurred vision, nose bleeding, pounding heart, dizziness"),
    SymptomSpec("high_sugar_symptoms",      "high blood sugar symptoms","excessive thirst, frequent urination, hunger, weight loss, blurred vision, slow healing"),
    SymptomSpec("numbness",                 "numbness",                 "tingling, pins and needles, loss of feeling, dead feeling"),
    SymptomSpec("dizziness",                "dizziness",                "feeling faint, lightheaded, spinning sensation, vertigo, off balance"),
]


# ---------------------------------------------------------------------------
# Disease catalogue
# ---------------------------------------------------------------------------

DISEASE_CATALOGUE: List[DiseaseSpec] = [
    DiseaseSpec(
        key="malaria",
        name="Malaria",
        description=(
            "Disease spread by mosquitoes. Common during rainy season. "
            "Causes fever, chills, and body weakness. If not treated, can cause "
            "severe illness especially in children and pregnant women."
        ),
        symptom_keys=["fever", "headache", "fatigue", "muscle_pain", "vomiting"],
    ),
    DiseaseSpec(
        key="pneumonia",
        name="Pneumonia",
        description=(
            "Infection in the lungs that fills them with fluid. Common when weather "
            "is cold or rainy. Dangerous for children under 5 and elderly. Makes "
            "breathing difficult."
        ),
        symptom_keys=["cough", "difficulty_breathing", "chest_pain", "fever", "fatigue"],
    ),
    DiseaseSpec(
        key="typhoid",
        name="Typhoid",
        description=(
            "Bacterial infection from eating food or drinking water contaminated with "
            "faeces. Common where there is poor sanitation. Causes long fever that "
            "does not go away."
        ),
        symptom_keys=["fever", "headache", "fatigue", "diarrhea", "abdominal_pain", "vomiting"],
    ),
    DiseaseSpec(
        key="cholera",
        name="Cholera",
        description=(
            "Severe diarrhoeal disease from contaminated water. Causes rapid water loss "
            "from the body. Can kill within hours if not treated. Common after floods."
        ),
        symptom_keys=["diarrhea", "vomiting", "dehydration", "abdominal_pain", "fatigue"],
    ),
    DiseaseSpec(
        key="dengue",
        name="Dengue",
        description=(
            "Viral infection spread by daytime mosquitoes. Also called 'break-bone fever' "
            "because of severe pain. Dangerous because it can cause bleeding."
        ),
        symptom_keys=["fever", "headache", "joint_pain", "muscle_pain", "rash", "vomiting"],
    ),
    DiseaseSpec(
        key="meningitis",
        name="Meningitis",
        description=(
            "Inflammation of the covering of the brain and spinal cord. Medical emergency. "
            "Can cause death or brain damage within hours."
        ),
        symptom_keys=["fever", "headache", "confusion", "vomiting", "muscle_pain"],
    ),
    DiseaseSpec(
        key="acute_diarrhea",
        name="Acute Diarrhea",
        description=(
            "Loose, watery stools several times a day. Usually from contaminated food or "
            "water or dirty hands. Main danger is water loss. Common in children under 5."
        ),
        symptom_keys=["diarrhea", "abdominal_pain", "vomiting", "dehydration", "fatigue"],
    ),
    DiseaseSpec(
        key="uti",
        name="Urinary Tract Infection",
        description=(
            "Infection in the urine pipes or bladder. More common in women. Caused by "
            "holding urine too long or poor hygiene."
        ),
        symptom_keys=["burning_urination", "frequent_urination", "lower_back_pain",
                      "abdominal_pain", "blood_urine", "fever"],
    ),
    DiseaseSpec(
        key="upper_respiratory_infection",
        name="Upper Respiratory Infection",
        description=(
            "Infection of the nose, throat, and breathing pipes. Spreads through coughing "
            "and sneezing. Common during cold weather."
        ),
        symptom_keys=["runny_nose", "sneezing", "sore_throat", "cough", "fever",
                      "headache", "fatigue"],
    ),
    DiseaseSpec(
        key="skin_infection",
        name="Skin Infection",
        description=(
            "Infection of skin or wounds. Caused by dirt entering cuts or poor wound care."
        ),
        symptom_keys=["redness", "swelling", "yellow_discharge", "muscle_pain", "fever", "wound"],
    ),
    DiseaseSpec(
        key="hypertension",
        name="High Blood Pressure",
        description=(
            "Silent disease where blood pushes too hard against blood vessel walls. Often "
            "no symptoms until dangerous. Common in adults over 40, especially with stress "
            "and salty food."
        ),
        symptom_keys=["headache", "dizziness", "chest_pain", "difficulty_breathing",
                      "confusion", "high_bp_symptoms"],
    ),
    DiseaseSpec(
        key="diabetes",
        name="Diabetes",
        description=(
            "Disease where the body cannot control sugar in the blood. Can cause blindness, "
            "kidney failure, and wounds that will not heal."
        ),
        symptom_keys=["fatigue", "high_sugar_symptoms", "headache", "numbness",
                      "frequent_urination", "dehydration", "wound"],
    ),
]


# ---------------------------------------------------------------------------
# First-aid catalogue
# ---------------------------------------------------------------------------

FIRST_AID_CATALOGUE: List[FirstAidSpec] = [
    FirstAidSpec(
        disease_key="malaria",
        title="Malaria – First Aid",
        steps=(
            "1. REST: Lie down and rest. Malaria makes you weak.\n\n"
            "2. FEVER CONTROL: Take paracetamol if available. Sponge the body with room-temperature water if very hot.\n\n"
            "3. FLUIDS: Drink plenty of clean water, porridge, soup, or oral rehydration salts (ORS).\n\n"
            "4. MOSQUITO NET: Sleep under a treated mosquito net to prevent further bites.\n\n"
            "5. SEEK TESTING: Go to the nearest health facility for a malaria rapid diagnostic test (RDT)."
        ),
        warning_notes="Do not take anti-malarial drugs without a confirmed positive test.",
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} or go to hospital immediately if:\n"
            "- Fever lasts more than 3 days\n"
            "- Person is unconscious or very drowsy\n"
            "- Child under 5 years with fever\n"
            "- Pregnant woman with fever"
        ),
    ),
    FirstAidSpec(
        disease_key="pneumonia",
        title="Pneumonia – First Aid",
        steps=(
            "1. SITTING POSITION: Help the person sit upright. Do not let them lie flat.\n\n"
            "2. LOOSE CLOTHING: Remove tight clothes from chest and neck.\n\n"
            "3. FRESH AIR: Open windows to allow fresh air.\n\n"
            "4. FLUIDS: Give small, frequent sips of water, tea, or soup.\n\n"
            "5. FEVER CONTROL: Give paracetamol if fever is present.\n\n"
            "6. HOSPITAL: Go to the nearest hospital immediately."
        ),
        warning_notes="Pneumonia can be fatal if not treated promptly, especially in young children and the elderly.",
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} or go to hospital immediately if:\n"
            "- Difficulty breathing or breathing very fast\n"
            "- Chest pain when breathing\n"
            "- Child too weak to drink or breastfeed\n"
            "- Lips or fingernails turn blue"
        ),
    ),
    FirstAidSpec(
        disease_key="typhoid",
        title="Typhoid – First Aid",
        steps=(
            "1. REST: Stay in bed. Typhoid makes the body very weak.\n\n"
            "2. SOFT FOODS: Eat soft foods such as porridge, soup, or mashed potatoes. Avoid oily food.\n\n"
            "3. FLUIDS: Drink plenty of clean water, fresh juice, or ORS.\n\n"
            "4. FEVER CONTROL: Take paracetamol for fever and body aches.\n\n"
            "5. HYGIENE: Wash hands with soap after using the bathroom. Use separate utensils.\n\n"
            "6. TESTING: Go to a clinic for a blood or stool test."
        ),
        warning_notes="Do not purchase antibiotics without a prescription. Incorrect antibiotic use causes drug resistance.",
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} or go to hospital if:\n"
            "- Fever continues for more than 3 days\n"
            "- Severe diarrhoea or blood in stool\n"
            "- Constant vomiting; unable to keep water down\n"
            "- Severe stomach pain"
        ),
    ),
    FirstAidSpec(
        disease_key="cholera",
        title="Cholera – First Aid",
        steps=(
            "1. ORS IMMEDIATELY: Mix oral rehydration salts with clean water. "
            "Home recipe if ORS unavailable: 1 litre clean water + 6 teaspoons sugar + ½ teaspoon salt.\n\n"
            "2. KEEP DRINKING: Even if vomiting occurs, continue giving small sips every few minutes.\n\n"
            "3. BREASTFEEDING: If the patient is an infant, continue breastfeeding and give ORS between feeds.\n\n"
            "4. HEALTH FACILITY: Cholera requires treatment at a health facility. Go immediately.\n\n"
            "5. HYGIENE: Wash hands with soap and water after every toilet visit."
        ),
        warning_notes="Cholera can cause death within hours from severe dehydration. This is a medical emergency.",
        when_to_seek_help=(
            f"Go to hospital immediately or call {KENYA_EMERGENCY} if:\n"
            "- Severe, watery diarrhoea\n"
            "- Persistent vomiting\n"
            "- Signs of dehydration: sunken eyes, dry mouth, no tears, little or no urine\n"
            "- Weakness; unable to stand"
        ),
    ),
    FirstAidSpec(
        disease_key="dengue",
        title="Dengue – First Aid",
        steps=(
            "1. REST: Stay in bed. Use a mosquito net even during daytime.\n\n"
            "2. FEVER CONTROL: Use paracetamol only. Do not use ibuprofen or aspirin – they increase bleeding risk.\n\n"
            "3. FLUIDS: Drink plenty of water, juice, coconut water, or ORS.\n\n"
            "4. CLOSE MONITORING: The most dangerous period is when the fever breaks (day 3–7). Watch carefully for warning signs."
        ),
        warning_notes="Dengue can cause internal bleeding. Never give ibuprofen, aspirin, or any anti-inflammatory medicine.",
        when_to_seek_help=(
            f"Go to hospital immediately or call {KENYA_EMERGENCY} if:\n"
            "- Severe stomach pain\n"
            "- Persistent vomiting\n"
            "- Bleeding from gums or nose\n"
            "- Dark-coloured vomit or stool\n"
            "- Restlessness or confusion"
        ),
    ),
    FirstAidSpec(
        disease_key="meningitis",
        title="Meningitis – First Aid",
        steps=(
            "1. HOSPITAL NOW: Meningitis is a life-threatening emergency. Go to hospital immediately.\n\n"
            "2. KEEP COMFORTABLE: While transporting, keep the person calm and still.\n\n"
            "3. MONITOR BREATHING: Watch breathing closely. If it stops and you are trained, begin CPR.\n\n"
            "4. NOTHING BY MOUTH: Do not give food or drink if the person is confused or drowsy."
        ),
        warning_notes="Meningitis can cause death or permanent brain damage within hours. Do not delay seeking care.",
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} immediately if:\n"
            "- Severe headache combined with fever\n"
            "- Stiff neck\n"
            "- Confusion or unusual drowsiness\n"
            "- Vomiting\n"
            "- Skin rash that does not fade when a glass is pressed against it\n"
            "- Seizures"
        ),
    ),
    FirstAidSpec(
        disease_key="acute_diarrhea",
        title="Acute Diarrhea – First Aid",
        steps=(
            "1. ORS IS THE MEDICINE: Begin oral rehydration salts immediately. "
            "Home recipe: 1 litre clean water + 6 teaspoons sugar + ½ teaspoon salt.\n\n"
            "2. CONTINUE EATING: Offer soft foods such as porridge, ugali, bananas, or plain rice.\n\n"
            "3. BREASTFEEDING: If the patient is an infant, continue breastfeeding and give ORS between feeds.\n\n"
            "4. ZINC TABLETS: If available, give zinc tablets for 10–14 days.\n\n"
            "5. HAND HYGIENE: Wash hands with soap and water after every toilet visit and before preparing food."
        ),
        warning_notes="The primary danger of diarrhoea is dehydration, which can be fatal, especially in young children.",
        when_to_seek_help=(
            f"Go to hospital immediately or call {KENYA_EMERGENCY} if:\n"
            "- Blood in stool\n"
            "- Unable to drink or keep fluids down\n"
            "- Signs of dehydration: sunken eyes, dry mouth, reduced urine\n"
            "- Person is very weak or unable to stand\n"
            "- High fever\n"
            "- Diarrhoea persists for more than 2 days"
        ),
    ),
    FirstAidSpec(
        disease_key="uti",
        title="Urinary Tract Infection (UTI) – First Aid",
        steps=(
            "1. DRINK WATER: Drink plenty of clean water to flush bacteria from the urinary tract.\n\n"
            "2. HYGIENE: Keep the genital area clean. Women should wipe from front to back.\n\n"
            "3. DO NOT HOLD URINE: Pass urine as soon as you feel the urge.\n\n"
            "4. AVOID IRRITANTS: Avoid strong soaps, sugary drinks, and excessive tea or coffee.\n\n"
            "5. PAIN RELIEF: Take paracetamol for pain as needed.\n\n"
            "6. CLINIC VISIT: A UTI requires prescription antibiotics. Do not self-medicate."
        ),
        warning_notes="If left untreated, infection can travel up to the kidneys and cause serious illness.",
        when_to_seek_help=(
            f"Go to hospital if:\n"
            "- Fever with chills\n"
            "- Pain in the lower back or side\n"
            "- Blood in urine\n"
            "- Vomiting\n"
            "- Pregnant woman with any urinary burning or pain"
        ),
    ),
    FirstAidSpec(
        disease_key="upper_respiratory_infection",
        title="Cold / Flu – First Aid",
        steps=(
            "1. REST: Stay at home and rest.\n\n"
            "2. WARM FLUIDS: Drink warm tea with lemon or honey, soup, or plain water regularly.\n\n"
            "3. STEAM INHALATION: Inhale steam from a bowl of hot water to help relieve a blocked nose.\n\n"
            "4. SALT-WATER GARGLE: Gargle with warm salt water to soothe a sore throat.\n\n"
            "5. FEVER CONTROL: Take paracetamol for fever or body aches.\n\n"
            "6. RESPIRATORY HYGIENE: Cough into your elbow; wash hands frequently to prevent spreading."
        ),
        warning_notes="Colds and flu spread easily. Avoid close contact with vulnerable individuals (elderly, infants, pregnant women).",
        when_to_seek_help=(
            f"Go to hospital if:\n"
            "- Difficulty breathing\n"
            "- Chest pain\n"
            "- Fever lasting more than 3 days\n"
            "- Child is breathing fast or refusing to drink"
        ),
    ),
    FirstAidSpec(
        disease_key="skin_infection",
        title="Skin Infection – First Aid",
        steps=(
            "1. CLEAN THE WOUND: Rinse with clean water and mild soap.\n\n"
            "2. ANTISEPTIC: Apply an antiseptic solution if available.\n\n"
            "3. COVER: Cover with a clean, dry dressing and change it daily.\n\n"
            "4. ELEVATE: If the wound is on an arm or leg, keep the limb raised to reduce swelling.\n\n"
            "5. MONITOR: Watch for spreading redness, increasing pain, or pus.\n\n"
            "6. CLINIC VISIT: Infected wounds usually require prescription antibiotics."
        ),
        warning_notes=(
            "Dirty wounds can cause tetanus. Ensure tetanus vaccination is up to date, "
            "especially after injuries from metal or animal bites."
        ),
        when_to_seek_help=(
            f"Go to hospital if:\n"
            "- Redness spreading around the wound\n"
            "- Pus or discharge\n"
            "- Fever\n"
            "- Red lines extending from the wound (sign of spreading infection)\n"
            "- Animal or human bite\n"
            "- Diabetic patient with any foot wound"
        ),
    ),
    FirstAidSpec(
        disease_key="hypertension",
        title="High Blood Pressure – Self-Care",
        steps=(
            "1. STAY CALM: A single high reading does not always mean an emergency. Sit and rest for 30 minutes, then re-check.\n\n"
            "2. REDUCE SALT: Cut back on salt in cooking and avoid salty processed foods.\n\n"
            "3. MANAGE STRESS: Rest, pray, talk to family, and practise deep breathing.\n\n"
            "4. AVOID TOBACCO: Tobacco damages blood vessel walls and raises blood pressure.\n\n"
            "5. TAKE MEDICATION: Take blood pressure medicine every day without skipping doses.\n\n"
            "6. EXERCISE: Walk for at least 30 minutes daily if able."
        ),
        warning_notes=(
            "High blood pressure usually has no symptoms until serious damage has occurred. "
            "Regular clinic check-ups are essential."
        ),
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} or go to hospital immediately if:\n"
            "- Severe headache that will not go away\n"
            "- Blurred vision\n"
            "- Chest pain or pressure\n"
            "- Difficulty speaking or weakness on one side of the body\n"
            "- Severe dizziness\n"
            "- Nosebleed that will not stop"
        ),
    ),
    FirstAidSpec(
        disease_key="diabetes",
        title="Diabetes – Self-Care",
        steps=(
            "1. DIET CONTROL: Eat at regular times. Limit sugar, soda, cakes, and white bread.\n\n"
            "2. HYDRATION: Drink plenty of water. Avoid sugary drinks.\n\n"
            "3. MEDICATION: Take diabetes medicine exactly as prescribed by your doctor.\n\n"
            "4. FOOT CARE: Check feet every day for cuts, sores, or blisters.\n\n"
            "5. EXERCISE: Walk daily to help the body use blood sugar more efficiently.\n\n"
            "6. REGULAR MONITORING: Attend clinic for regular blood sugar checks."
        ),
        warning_notes=(
            "People with diabetes heal very slowly. Any wound, especially on the feet, "
            "must be assessed by a healthcare worker promptly."
        ),
        when_to_seek_help=(
            f"Call {KENYA_EMERGENCY} or go to hospital immediately if:\n"
            "- Very high blood sugar\n"
            "- Confusion or altered behaviour\n"
            "- Fruity smell on the breath\n"
            "- Fast or laboured breathing\n"
            "- Vomiting\n"
            "- Unconsciousness\n"
            "- Any infected foot wound"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Emergency keyword catalogue
# ---------------------------------------------------------------------------

EMERGENCY_CATALOGUE: List[EmergencySpec] = [
    # --- CRITICAL ---
    EmergencySpec(
        keyword="unconscious",
        severity="CRITICAL",
        response_message=(
            f"🚨 EMERGENCY – Person is unconscious. Call {KENYA_EMERGENCY} immediately.\n\n"
            "WHILE WAITING FOR HELP:\n"
            "- Check if they are breathing\n"
            "- If breathing, place them on their side (recovery position)\n"
            "- If not breathing, begin CPR: push hard and fast on the centre of the chest\n"
            "- Loosen any tight clothing"
        ),
    ),
    EmergencySpec(
        keyword="not breathing",
        severity="CRITICAL",
        response_message=(
            f"🚨 EMERGENCY – Person is not breathing. Call {KENYA_EMERGENCY} NOW.\n\n"
            "BEGIN CPR:\n"
            "- Place the person on their back on a firm surface\n"
            "- Push hard and fast on the centre of the chest (100–120 times per minute)\n"
            "- Continue until emergency services arrive"
        ),
    ),
    EmergencySpec(
        keyword="severe bleeding",
        severity="CRITICAL",
        response_message=(
            f"🚨 SEVERE BLEEDING. Call {KENYA_EMERGENCY} immediately.\n\n"
            "CONTROL THE BLEEDING:\n"
            "- Apply firm pressure on the wound with a clean cloth or bandage\n"
            "- Do not remove the cloth if it soaks through – add more on top\n"
            "- Keep the person lying down and warm"
        ),
    ),
    EmergencySpec(
        keyword="snake bite",
        severity="CRITICAL",
        response_message=(
            f"🚨 SNAKE BITE. Call {KENYA_EMERGENCY} NOW.\n\n"
            "DO:\n"
            "- Keep the person calm and as still as possible\n"
            "- Remove tight clothing or jewellery near the bite\n"
            "- Note the snake's colour or pattern if safe to do so\n"
            "- Get to the nearest hospital immediately\n\n"
            "DO NOT:\n"
            "- Do not cut the wound or attempt to suck out venom\n"
            "- Do not apply a tourniquet"
        ),
    ),
    EmergencySpec(
        keyword="choking",
        severity="CRITICAL",
        response_message=(
            f"🚨 CHOKING – Person cannot breathe. Call {KENYA_EMERGENCY}.\n\n"
            "IF CONSCIOUS:\n"
            "- Stand behind the person\n"
            "- Give up to 5 firm back blows between the shoulder blades\n"
            "- If ineffective, give up to 5 abdominal thrusts (Heimlich manoeuvre)\n\n"
            "IF UNCONSCIOUS:\n"
            "- Lay the person down and begin CPR"
        ),
    ),
    EmergencySpec(
        keyword="heart attack",
        severity="CRITICAL",
        response_message=(
            f"🚨 POSSIBLE HEART ATTACK. Call {KENYA_EMERGENCY} immediately.\n\n"
            "WHILE WAITING:\n"
            "- Have the person sit or lie in a comfortable position – do not let them exert themselves\n"
            "- Loosen tight clothing around the neck and chest\n"
            "- If aspirin is available and the person is not allergic, give 300 mg to chew slowly"
        ),
    ),
    EmergencySpec(
        keyword="drowning",
        severity="CRITICAL",
        response_message=(
            f"🚨 DROWNING. Call {KENYA_EMERGENCY} immediately.\n\n"
            "- Remove the person from the water safely – do not put yourself at risk\n"
            "- Check for breathing\n"
            "- If not breathing, begin CPR immediately\n"
            "- Keep the person warm while waiting for help"
        ),
    ),
    EmergencySpec(
        keyword="poison",
        severity="CRITICAL",
        response_message=(
            f"🚨 POISONING. Call {KENYA_EMERGENCY} immediately.\n\n"
            "- Identify what was swallowed; bring the container to the hospital\n"
            "- If poison is on skin, rinse thoroughly with clean water for 15–20 minutes\n"
            "- If fumes were inhaled, move the person to fresh air immediately\n"
            "- Do not induce vomiting unless specifically instructed by a healthcare professional"
        ),
    ),
    # --- HIGH ---
    EmergencySpec(
        keyword="seizure",
        severity="HIGH",
        response_message=(
            f"⚠️ SEIZURE. Call {KENYA_EMERGENCY} if this is the person's first seizure or it lasts longer than 5 minutes.\n\n"
            "DO:\n"
            "- Clear the area of any hard or sharp objects\n"
            "- Cushion the person's head with something soft\n"
            "- Time how long the seizure lasts\n"
            "- Roll the person onto their side once the jerking stops\n\n"
            "DO NOT:\n"
            "- Do not hold the person down or restrain them\n"
            "- Do not put anything in their mouth"
        ),
    ),
    EmergencySpec(
        keyword="burn",
        severity="HIGH",
        response_message=(
            f"⚠️ BURN. Go to hospital if the burn is large, deep, or on the face, hands, or genitals. Call {KENYA_EMERGENCY} for severe burns.\n\n"
            "IMMEDIATE STEPS:\n"
            "- Cool the burn with cool (not cold) running water for at least 20 minutes\n"
            "- Remove jewellery and loose clothing near the burn before swelling starts\n"
            "- Cover loosely with a clean, non-fluffy cloth\n\n"
            "DO NOT:\n"
            "- Do not apply toothpaste, butter, or oil\n"
            "- Do not burst any blisters"
        ),
    ),
    # --- Intentional spelling / phrasing variants ---
    EmergencySpec(
        keyword="unconcious",  # intentional misspelling variant
        severity="CRITICAL",
        response_message=f"🚨 Unconscious person detected. Call {KENYA_EMERGENCY} NOW. Check breathing immediately.",
        is_typo_variant=True,
    ),
    EmergencySpec(
        keyword="fainting",
        severity="HIGH",
        response_message=(
            f"⚠️ Person has fainted. Lay them flat and raise their legs. "
            f"Call {KENYA_EMERGENCY} if they do not regain consciousness within 1 minute."
        ),
        is_typo_variant=True,
    ),
    EmergencySpec(
        keyword="convulsions",
        severity="HIGH",
        response_message=(
            f"⚠️ Convulsions (seizure). Clear the area and cushion the head. "
            f"Call {KENYA_EMERGENCY} if it lasts more than 5 minutes or is the first episode."
        ),
        is_typo_variant=True,
    ),
    EmergencySpec(
        keyword="bleeding",
        severity="HIGH",
        response_message=(
            f"⚠️ Bleeding. Apply firm pressure with a clean cloth. "
            f"Call {KENYA_EMERGENCY} if bleeding is severe or does not stop."
        ),
        is_typo_variant=True,
    ),
]


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Populate the database with Kenya-specific medical data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip the confirmation prompt and proceed immediately.",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            self.stdout.write(self.style.WARNING(
                "\nThis command will DELETE all existing Disease, Symptom, "
                "FirstAidProcedure, and EmergencyKeyword records and rebuild "
                "the database from scratch.\n"
            ))
            confirm = input("Type 'yes' to continue or anything else to abort: ")
            if confirm.strip().lower() != "yes":
                self.stdout.write(self.style.ERROR("Aborted. No changes were made."))
                return

        try:
            counts = self._run_population()
        except Exception as exc:
            logger.exception("Database population failed.")
            raise CommandError(f"Population failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("\nKenyan medical data populated successfully.\n"))
        self.stdout.write(f"   Diseases          : {counts['diseases']}")
        self.stdout.write(f"   Symptoms          : {counts['symptoms']}")
        self.stdout.write(f"   First-aid records : {counts['first_aid']}")
        self.stdout.write(f"   Emergency keywords: {counts['emergency_keywords']}")

    # ------------------------------------------------------------------
    # Core population logic
    # ------------------------------------------------------------------

    def _run_population(self) -> Dict[str, int]:
        """
        Execute all database writes inside a single atomic transaction.
        Returns a dict of record counts for reporting.
        """
        with transaction.atomic():
            self._clear_existing_data()
            symptoms = self._create_symptoms()
            diseases = self._create_diseases(symptoms)
            self._create_first_aid(diseases)
            self._create_emergency_keywords()
            # Invalidate RAG cache so stale data is not served after repopulation
            cache.delete("rag_diseases_text")

        return {
            "diseases": len(diseases),
            "symptoms": len(symptoms),
            "first_aid": len(FIRST_AID_CATALOGUE),
            "emergency_keywords": len(EMERGENCY_CATALOGUE),
        }

    # ------------------------------------------------------------------
    # Step 1: Clear
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_existing_data() -> None:
        """
        Delete records in an order that respects relational constraints:
        M2M through-table rows first, then parent rows.
        """
        Disease.symptoms.through.objects.all().delete()
        FirstAidProcedure.objects.all().delete()
        Disease.objects.all().delete()
        Symptom.objects.all().delete()
        EmergencyKeyword.objects.all().delete()

    # ------------------------------------------------------------------
    # Step 2: Symptoms
    # ------------------------------------------------------------------

    @staticmethod
    def _create_symptoms() -> Dict[str, Symptom]:
        symptom_objects: Dict[str, Symptom] = {}
        symptom_objects_to_create = [
            Symptom(name=spec.name, alternative_names=spec.alternative_names)
            for spec in SYMPTOM_CATALOGUE
        ]
        created = Symptom.objects.bulk_create(symptom_objects_to_create)
        for spec, obj in zip(SYMPTOM_CATALOGUE, created):
            symptom_objects[spec.key] = obj
        return symptom_objects

    # ------------------------------------------------------------------
    # Step 3: Diseases
    # ------------------------------------------------------------------

    @staticmethod
    def _create_diseases(symptoms: Dict[str, Symptom]) -> Dict[str, Disease]:
        disease_objects: Dict[str, Disease] = {}

        for spec in DISEASE_CATALOGUE:
            linked_symptoms = [symptoms[k] for k in spec.symptom_keys if k in symptoms]

            # Derive common_symptoms from linked symptom objects so the
            # RAGRetriever's substring matching stays consistent with M2M links.
            common_symptoms_parts = [spec.name.lower()]
            for sym in linked_symptoms:
                common_symptoms_parts.append(sym.name)
                common_symptoms_parts.append(sym.alternative_names)
            common_symptoms_text = ", ".join(common_symptoms_parts)

            disease = Disease.objects.create(
                name=spec.name,
                description=spec.description,
                common_symptoms=common_symptoms_text,
            )
            disease.symptoms.set(linked_symptoms)
            disease_objects[spec.key] = disease

        return disease_objects

    # ------------------------------------------------------------------
    # Step 4: First-aid procedures
    # ------------------------------------------------------------------

    @staticmethod
    def _create_first_aid(diseases: Dict[str, Disease]) -> None:
        procedures = [
            FirstAidProcedure(
                disease=diseases[spec.disease_key],
                title=spec.title,
                steps=spec.steps,
                warning_notes=spec.warning_notes,
                when_to_seek_help=spec.when_to_seek_help,
            )
            for spec in FIRST_AID_CATALOGUE
            if spec.disease_key in diseases
        ]
        FirstAidProcedure.objects.bulk_create(procedures)

    # ------------------------------------------------------------------
    # Step 5: Emergency keywords
    # ------------------------------------------------------------------

    @staticmethod
    def _create_emergency_keywords() -> None:
        keywords = [
            EmergencyKeyword(
                keyword=spec.keyword,
                severity=spec.severity,
                response_message=spec.response_message,
            )
            for spec in EMERGENCY_CATALOGUE
        ]
        EmergencyKeyword.objects.bulk_create(keywords)


# ---------------------------------------------------------------------------
# Cache invalidation signals
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Disease)
@receiver(post_save, sender=FirstAidProcedure)
def invalidate_disease_cache(sender, **kwargs):  # noqa: ANN001
    """
    Clear the RAG disease cache whenever a Disease or FirstAidProcedure record
    is saved outside of this management command (e.g. via the admin or an API).
    """
    cache.delete("rag_diseases_text")
    logger.debug("RAG disease cache invalidated due to %s save.", sender.__name__)
