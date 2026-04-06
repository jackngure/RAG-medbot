from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from chatbot.models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword

class Command(BaseCommand):
    help = 'Populate database with Kenyan medical data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt and force reset',
        )

    def handle(self, *args, **options):
        force = options['force']

        if not force:
            self.stdout.write(self.style.WARNING(
                'This will DELETE all existing Disease, Symptom, FirstAidProcedure, '
                'and EmergencyKeyword records and repopulate from scratch.'
            ))
            confirm = input('Are you sure you want to continue? (y/N): ')
            if confirm.lower() != 'y':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        try:
            with transaction.atomic():
                self._populate_data()
        except Exception as e:
            raise CommandError(f'Population failed: {e}')

        self.stdout.write(self.style.SUCCESS('✅ Kenyan medical data populated successfully!'))
        self.stdout.write(f'   • {Disease.objects.count()} diseases added')
        self.stdout.write(f'   • {Symptom.objects.count()} symptoms added')
        self.stdout.write(f'   • {FirstAidProcedure.objects.count()} first aid procedures added')
        self.stdout.write(f'   • {EmergencyKeyword.objects.count()} emergency keywords added')

    def _populate_data(self):
        # Clearing existing data
        Disease.objects.all().delete()
        Symptom.objects.all().delete()
        FirstAidProcedure.objects.all().delete()
        EmergencyKeyword.objects.all().delete()

        # Creating Symptoms
        symptoms_data = {
            'fever': ('fever', 'high temperature, hot body, sweating, chills, feeling hot even when cold'),
            'headache': ('headache', 'head pain, migraine, throbbing head, pressure in head'),
            'cough': ('cough', 'coughing, dry cough, wet cough, chest cough, barking cough'),
            'diarrhea': ('diarrhea', 'diarrhoea, loose stools, running stomach, watery stool, frequent bathroom, stomach running'),
            'vomiting': ('vomiting', 'throwing up, nausea, sick stomach, can\'t keep food down'),
            'fatigue': ('fatigue', 'tiredness, weakness, exhaustion, lethargy, no energy, body weak'),
            'chest_pain': ('chest pain', 'chest discomfort, heart pain, tight chest, squeezing in chest'),
            'difficulty_breathing': ('difficulty breathing', 'shortness of breath, breathlessness, can\'t breathe, breathing fast, wheezing'),
            'joint_pain': ('joint pain', 'joint ache, arthritis, pain in joints, knees hurt, back pain'),
            'muscle_pain': ('muscle pain', 'myalgia, body aches, sore muscles, whole body pain'),
            'rash': ('rash', 'skin rash, red spots, itching, hives, skin bumps, scratching'),
            'abdominal_pain': ('abdominal pain', 'stomach ache, belly pain, cramping, tummy hurts, stomach problems'),
            'dehydration': ('dehydration', 'dry mouth, sunken eyes, reduced urine, thirsty, no tears, dark urine'),
            'confusion': ('confusion', 'disoriented, altered mental state, delirium, not acting normal, confused mind'),
            'burning_urination': ('burning urination', 'pain when passing urine, painful urination, burning sensation, urine burns'),
            'frequent_urination': ('frequent urination', 'passing urine often, many times bathroom, can\'t hold urine'),
            'blood_urine': ('blood in urine', 'red urine, bloody urine, pink urine, blood when passing urine'),
            'lower_back_pain': ('lower back pain', 'backache, pain in lower back, kidney pain, spine hurts'),
            'runny_nose': ('runny nose', 'running nose, nasal discharge, blocked nose, flu'),
            'sneezing': ('sneezing', 'sneezing constantly, allergy sneezing'),
            'sore_throat': ('sore throat', 'painful throat, throat pain, difficulty swallowing, swollen throat'),
            'yellow_discharge': ('yellow discharge', 'pus from wound, infected wound, yellow fluid, wound oozing'),
            'swelling': ('swelling', 'swollen body part, edema, puffy, inflamed'),
            'redness': ('redness', 'red skin, inflamed skin, hot skin'),
            'wound': ('wound', 'cut, injury, sore, ulcer, broken skin, open wound'),
            'high_blood_pressure_symptoms': ('high blood pressure symptoms', 'severe headache, blurred vision, nose bleeding, pounding heart, dizziness'),
            'high_blood_sugar_symptoms': ('high blood sugar symptoms', 'excessive thirst, frequent urination, hunger, weight loss, blurred vision, slow healing'),
            'numbness': ('numbness', 'tingling, pins and needles, loss of feeling, dead feeling'),
            'dizziness': ('dizziness', 'feeling faint, lightheaded, spinning sensation, vertigo, off balance'),
        }

        symptoms = {}
        for key, (name, alt_names) in symptoms_data.items():
            symptoms[key] = Symptom.objects.create(
                name=name,
                alternative_names=alt_names
            )

        # Create Diseases
        diseases_data = {
            'malaria': ('Malaria', 
                       'Disease spread by mosquitoes. Common during rainy season. Causes fever, chills, and body weakness. If not treated, can cause severe illness especially in children and pregnant women.',
                       'fever, headache, chills, sweating, fatigue, joint pain'),
            
            'pneumonia': ('Pneumonia', 
                         'Infection in the lungs that fills them with fluid. Common when weather is cold or rainy. Dangerous for children under 5 and elderly. Makes breathing difficult.',
                         'cough, difficulty breathing, chest pain, fever, fast breathing'),
            
            'typhoid': ('Typhoid', 
                       'Bacterial infection from eating food or drinking water contaminated with feces. Common where there is poor sanitation. Causes long fever that doesn\'t go away.',
                       'fever, headache, fatigue, stomach pain, diarrhea, loss of appetite'),
            
            'chikungunya': ('Chikungunya', 
                           'Viral disease spread by mosquitoes. Causes severe joint pain that can last months. Also called "bending fever" because pain makes you bend.',
                           'fever, joint pain, headache, rash, fatigue, muscle pain'),
            
            'cholera': ('Cholera', 
                       'Severe diarrheal disease from contaminated water. Causes rapid water loss from body. Can kill within hours if not treated. Common after floods.',
                       'severe diarrhea (rice-water stool), vomiting, dehydration, abdominal pain'),
            
            'dengue': ('Dengue', 
                      'Viral infection spread by daytime mosquitoes. Also called "break-bone fever" because of severe pain. Dangerous because can cause bleeding.',
                      'fever, severe headache, joint and muscle pain, rash, pain behind eyes'),
            
            'rift_valley_fever': ('Rift Valley Fever', 
                                 'Viral disease common in livestock areas. Spread by mosquitoes or contact with sick animals. Affects farmers and livestock keepers.',
                                 'fever, muscle pain, weakness, dizziness, back pain'),
            
            'meningitis': ('Meningitis', 
                          'Inflammation of the covering of brain and spinal cord. Medical emergency. Can cause death or brain damage within hours.',
                          'severe headache, fever, stiff neck, confusion, vomiting, sensitivity to light'),
            
            'acute_diarrhea': ('Acute Diarrhea', 
                              'Loose, watery stools several times a day. Usually from contaminated food/water or dirty hands. Main danger is water loss. Common in children under 5.',
                              'watery stool, frequent bathroom visits, vomiting, dehydration, abdominal pain'),
            
            'uti': ('Urinary Tract Infection', 
                   'Infection in the urine pipes or bladder. More common in women. Caused by holding urine too long or poor hygiene.',
                   'burning urination, frequent urination, lower back pain, blood in urine, lower stomach pain'),
            
            'upper_respiratory_infection': ('Upper Respiratory Infection', 
                                           'Infection of nose, throat, and breathing pipes. Spreads through coughing and sneezing. Common during cold weather.',
                                           'runny nose, sneezing, sore throat, cough, fever, headache'),
            
            'skin_infection': ('Skin Infection', 
                              'Infection of skin or wounds. Caused by dirt entering cuts or poor wound care.',
                              'redness around wound, swelling, pus, pain, fever'),
            
            'hypertension': ('High Blood Pressure', 
                            'Silent disease where blood pushes too hard against blood vessel walls. Often no symptoms until dangerous. Common in adults over 40, especially with stress and salty food.',
                            'severe headache, blurred vision, chest pain, difficulty breathing, nose bleeding, dizziness'),
            
            'diabetes': ('Diabetes', 
                        'Disease where body cannot control sugar in blood. Can cause blindness, kidney failure, and wounds that won\'t heal.',
                        'excessive thirst, frequent urination, hunger, weight loss, fatigue, blurred vision, slow healing wounds, numbness in feet'),
        }

        diseases = {}
        for key, (name, desc, symptoms_str) in diseases_data.items():
            diseases[key] = Disease.objects.create(
                name=name,
                description=desc,
                common_symptoms=symptoms_str
            )

        # Link symptoms to diseases
        diseases['malaria'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue'],
            symptoms['muscle_pain'], symptoms['vomiting']
        )
        
        diseases['pneumonia'].symptoms.add(
            symptoms['cough'], symptoms['difficulty_breathing'],
            symptoms['chest_pain'], symptoms['fever'], symptoms['fatigue']
        )
        
        diseases['typhoid'].symptoms.add(
            symptoms['fever'], symptoms['headache'],
            symptoms['fatigue'], symptoms['diarrhea'], symptoms['abdominal_pain'],
            symptoms['vomiting']
        )
        
        diseases['chikungunya'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue'],
            symptoms['joint_pain'], symptoms['rash'], symptoms['muscle_pain']
        )
        
        diseases['cholera'].symptoms.add(
            symptoms['diarrhea'], symptoms['vomiting'], symptoms['dehydration'],
            symptoms['abdominal_pain'], symptoms['fatigue']
        )
        
        diseases['dengue'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['joint_pain'],
            symptoms['muscle_pain'], symptoms['rash'], symptoms['vomiting']
        )
        
        diseases['rift_valley_fever'].symptoms.add(
            symptoms['fever'], symptoms['muscle_pain'], symptoms['fatigue'],
            symptoms['headache'], symptoms['dizziness']
        )
        
        diseases['meningitis'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['confusion'],
            symptoms['vomiting'], symptoms['muscle_pain']
        )
        
        diseases['acute_diarrhea'].symptoms.add(
            symptoms['diarrhea'], symptoms['abdominal_pain'], symptoms['vomiting'],
            symptoms['dehydration'], symptoms['fatigue']
        )
        
        diseases['uti'].symptoms.add(
            symptoms['burning_urination'], symptoms['frequent_urination'],
            symptoms['lower_back_pain'], symptoms['abdominal_pain'],
            symptoms['blood_urine'], symptoms['fever']
        )
        
        diseases['upper_respiratory_infection'].symptoms.add(
            symptoms['runny_nose'], symptoms['sneezing'], symptoms['sore_throat'],
            symptoms['cough'], symptoms['fever'], symptoms['headache'],
            symptoms['fatigue']
        )
        
        diseases['skin_infection'].symptoms.add(
            symptoms['redness'], symptoms['swelling'], symptoms['yellow_discharge'],
            symptoms['muscle_pain'], symptoms['fever'], symptoms['wound']
        )
        
        diseases['hypertension'].symptoms.add(
            symptoms['headache'], symptoms['dizziness'], symptoms['chest_pain'],
            symptoms['difficulty_breathing'], symptoms['confusion'],
            symptoms['high_blood_pressure_symptoms']
        )
        
        diseases['diabetes'].symptoms.add(
            symptoms['fatigue'], symptoms['high_blood_sugar_symptoms'],
            symptoms['headache'], symptoms['numbness'], symptoms['frequent_urination'],
            symptoms['dehydration'], symptoms['wound']
        )

        # Creating First Aid Procedures
        first_aid_data = [
            (diseases['malaria'], 'Malaria First Aid',
             '1. REST: Lie down and rest. Malaria makes you weak.\n\n'
             '2. FEVER: Use paracetamol if available. Sponge with room temperature water if very hot.\n\n'
             '3. DRINKS: Drink plenty of clean water, porridge, soup, or oral rehydration salts.\n\n'
             '4. MOSQUITO NET: Sleep under a treated mosquito net to prevent more bites.\n\n'
             '5. GO TO CLINIC: Go to the nearest health facility for a malaria test.',
             
             'Do not take anti-malarial drugs without testing first.',
             
             'Seek help immediately if:\n'
             '• Fever lasts more than 3 days\n'
             '• Person is unconscious or very sleepy\n'
             '• Child under 5 years old with fever\n'
             '• Pregnant woman with fever'),
            
            (diseases['pneumonia'], 'Pneumonia First Aid',
             '1. SITTING POSITION: Help the person sit upright. Do not let them lie flat.\n\n'
             '2. LOOSE CLOTHES: Remove tight clothes from chest and neck.\n\n'
             '3. AIR: Open windows for fresh air.\n\n'
             '4. FLUIDS: Give small sips of water, tea, or soup frequently.\n\n'
             '5. FEVER: Use paracetamol if fever is present.\n\n'
             '6. HOSPITAL: Go to hospital immediately.',
             
             'Pneumonia can be fatal if not treated promptly.',
             
             'Go to hospital now if:\n'
             '• Difficulty breathing or breathing fast\n'
             '• Chest pain when breathing\n'
             '• Child is too weak to drink or breastfeed\n'
             '• Lips or fingernails turn blue'),
            
            (diseases['typhoid'], 'Typhoid First Aid',
             '1. REST: Stay in bed. Typhoid makes the body very weak.\n\n'
             '2. FOOD: Eat soft foods like porridge, soup, mashed potatoes. Avoid oily food.\n\n'
             '3. DRINKS: Drink plenty of clean water, fresh juice, or ORS.\n\n'
             '4. FEVER: Use paracetamol for fever and body aches.\n\n'
             '5. HYGIENE: Wash hands with soap after bathroom. Use separate utensils.\n\n'
             '6. TEST: Go to clinic for a blood or stool test.',
             
             'Do not buy antibiotics without prescription.',
             
             'Go to hospital if:\n'
             '• Fever continues for more than 3 days\n'
             '• Severe diarrhea or blood in stool\n'
             '• Constant vomiting, can\'t keep water down\n'
             '• Severe stomach pain'),
            
            (diseases['chikungunya'], 'Chikungunya First Aid',
             '1. REST: Joints hurt because of the virus. Rest as much as possible.\n\n'
             '2. PAIN RELIEF: Use paracetamol for pain and fever. Avoid ibuprofen or aspirin.\n\n'
             '3. COLD COMPRESS: Use cold water on painful joints.\n\n'
             '4. DRINKS: Drink plenty of fluids to stay hydrated.\n\n'
             '5. MOSQUITO NET: Sleep under net to prevent spreading to family.',
             
             'Joint pain may persist for weeks or months.',
             
             'Go to hospital if:\n'
             '• Severe headache that doesn\'t go away\n'
             '• Vomiting constantly\n'
             '• Symptoms get worse after fever goes down\n'
             '• Bleeding from nose or gums'),
            
            (diseases['cholera'], 'Cholera First Aid',
             '1. ORS IMMEDIATELY: Mix oral rehydration salts with clean water. If no ORS, mix: 1 liter clean water + 6 teaspoons sugar + ½ teaspoon salt.\n\n'
             '2. KEEP DRINKING: Even if vomiting, keep giving small sips.\n\n'
             '3. BREASTFEEDING: If baby, continue breastfeeding. Give ORS between feeds.\n\n'
             '4. GO TO CLINIC: Cholera needs treatment at health facility.\n\n'
             '5. HYGIENE: Wash hands with soap and ash.',
             
             'Cholera can kill within hours from dehydration.',
             
             'Go to hospital immediately if:\n'
             '• Severe watery diarrhea\n'
             '• Vomiting\n'
             '• Signs of dehydration: sunken eyes, dry mouth, no tears, little urine\n'
             '• Weakness, can\'t stand'),
            
            (diseases['dengue'], 'Dengue First Aid',
             '1. REST: Stay in bed. Use mosquito net even during day.\n\n'
             '2. FEVER: Use paracetamol only. Do not use ibuprofen or aspirin.\n\n'
             '3. DRINKS: Drink plenty of water, juice, coconut water, ORS.\n\n'
             '4. WATCH CAREFULLY: The dangerous time is when fever goes down.',
             
             'Dengue can cause bleeding. Avoid anti-inflammatories.',
             
             'Go to hospital immediately if:\n'
             '• Severe stomach pain\n'
             '• Constant vomiting\n'
             '• Bleeding gums or nose\n'
             '• Dark vomit or dark stool\n'
             '• Restlessness or confusion'),
            
            (diseases['meningitis'], 'Meningitis First Aid',
             '1. HOSPITAL NOW: This is a medical emergency. Go to hospital immediately.\n\n'
             '2. KEEP COMFORTABLE: While traveling, keep person comfortable.\n\n'
             '3. MONITOR BREATHING: Watch breathing. If stops, start CPR if you know how.\n\n'
             '4. NO FOOD/DRINK: Do not give anything by mouth if person is confused.',
             
             'Meningitis can cause death or brain damage within hours.',
             
             'Go to hospital now if:\n'
             '• Severe headache with fever\n'
             '• Stiff neck\n'
             '• Confusion\n'
             '• Vomiting\n'
             '• Rash that doesn\'t fade when pressed\n'
             '• Seizures'),
            
            (diseases['acute_diarrhea'], 'Diarrhea First Aid',
             '1. ORS IS MEDICINE: Start oral rehydration salts immediately. If no ORS, make at home: 1 liter clean water + 6 teaspoons sugar + ½ teaspoon salt.\n\n'
             '2. CONTINUE EATING: Give soft foods like porridge, ugali, bananas, rice.\n\n'
             '3. BREASTFEEDING: If baby, continue breastfeeding. Give ORS between feeds.\n\n'
             '4. ZINC: If available, give zinc tablets for 10-14 days.\n\n'
             '5. WASH HANDS: Wash hands with soap and water after bathroom.',
             
             'The biggest danger from diarrhea is dehydration.',
             
             'Go to hospital immediately if:\n'
             '• Blood in stool\n'
             '• Cannot drink or keep anything down\n'
             '• Signs of dehydration\n'
             '• Very weak, can\'t stand\n'
             '• High fever\n'
             '• Diarrhea for more than 2 days'),
            
            (diseases['uti'], 'UTI First Aid',
             '1. DRINK WATER: Drink plenty of clean water to flush bacteria.\n\n'
             '2. HYGIENE: Keep private parts clean. Wipe from front to back.\n\n'
             '3. DO NOT HOLD URINE: Pass urine whenever you feel the need.\n\n'
             '4. AVOID: Avoid strong soap, sugar, and too much tea/coffee.\n\n'
             '5. PAIN: Use paracetamol for pain if needed.\n\n'
             '6. GO TO CLINIC: UTI needs antibiotics.',
             
             'If not treated, infection can travel up to kidneys.',
             
             'Go to hospital if:\n'
             '• Fever with chills\n'
             '• Pain in lower back or side\n'
             '• Blood in urine\n'
             '• Vomiting\n'
             '• Pregnant woman with burning urine'),
            
            (diseases['upper_respiratory_infection'], 'Cold/Flu First Aid',
             '1. REST: Stay home and rest.\n\n'
             '2. WARM DRINKS: Drink warm tea with lemon/honey, soup, or water.\n\n'
             '3. STEAM: Inhale steam from hot water to help blocked nose.\n\n'
             '4. SALT WATER GARGLE: For sore throat, gargle with warm salt water.\n\n'
             '5. FEVER: Use paracetamol if fever or body aches.\n\n'
             '6. COVER COUGH: Cough into elbow to prevent spreading.',
             
             'Colds spread easily. Wash hands often.',
             
             'Go to hospital if:\n'
             '• Difficulty breathing\n'
             '• Chest pain\n'
             '• Fever for more than 3 days\n'
             '• Child is breathing fast or not drinking'),
            
            (diseases['skin_infection'], 'Skin Infection First Aid',
             '1. CLEAN WOUND: Clean with clean water and mild soap.\n\n'
             '2. ANTISEPTIC: Apply antiseptic if available.\n\n'
             '3. COVER: Cover with clean, dry dressing. Change daily.\n\n'
             '4. ELEVATE: If wound on arm or leg, keep raised to reduce swelling.\n\n'
             '5. WATCH SIGNS: Monitor for spreading redness, more pain, or pus.\n\n'
             '6. GO TO CLINIC: Infected wounds often need antibiotics.',
             
             'Dirty wounds can cause tetanus. Get tetanus shot if wound from metal or animal.',
             
             'Go to hospital if:\n'
             '• Redness spreading around wound\n'
             '• Pus or discharge\n'
             '• Fever\n'
             '• Red lines going up from wound\n'
             '• Wound from animal bite\n'
             '• Diabetes patient with any foot wound'),
            
            (diseases['hypertension'], 'High Blood Pressure - Self Care',
             '1. NO PANIC: One high reading doesn\'t mean emergency. Rest 30 minutes.\n\n'
             '2. SALT REDUCTION: Reduce salt in cooking. Avoid salty foods.\n\n'
             '3. STRESS REDUCTION: Rest, pray, talk to family, breathe deeply.\n\n'
             '4. STOP TOBACCO: Tobacco damages blood vessels.\n\n'
             '5. MEDICINE: Take BP medicine every day. Do not skip.\n\n'
             '6. EXERCISE: Walk for 30 minutes daily if able.',
             
             'Most people have no symptoms until damage occurs. Regular checkups are important.',
             
             'Go to hospital now if:\n'
             '• Severe headache that won\'t go away\n'
             '• Blurred vision\n'
             '• Chest pain or pressure\n'
             '• Difficulty speaking or weakness on one side\n'
             '• Severe dizziness\n'
             '• Nose bleeding that won\'t stop'),
            
            (diseases['diabetes'], 'Diabetes - Self Care',
             '1. FOOD CONTROL: Eat at regular times. Avoid too much sugar, soda, cakes.\n\n'
             '2. WATER: Drink plenty of water. Avoid sugary drinks.\n\n'
             '3. MEDICINE: Take diabetes medicine exactly as prescribed.\n\n'
             '4. FOOT CARE: Check feet daily for cuts or sores.\n\n'
             '5. EXERCISE: Walk daily to help body use sugar better.\n\n'
             '6. REGULAR CHECK: Go to clinic for blood sugar checks.',
             
             'People with diabetes heal slowly. Any wound should be checked.',
             
             'Go to hospital now if:\n'
             '• Very high blood sugar\n'
             '• Confusion\n'
             '• Fruity smell on breath\n'
             '• Fast breathing\n'
             '• Vomiting\n'
             '• Unconsciousness\n'
             '• Any infected foot wound'),
        ]

        for disease, title, steps, warning, when in first_aid_data:
            FirstAidProcedure.objects.create(
                disease=disease,
                title=title,
                steps=steps,
                warning_notes=warning,
                when_to_seek_help=when
            )

        # Creating Emergency Keywords
        emergency_list = [
            {'keyword': 'unconscious', 'severity': 'CRITICAL',
             'response': '🚨 EMERGENCY - Person is unconscious. Call 911 or 112 immediately.\n\nWHILE WAITING:\n• Check if they are breathing\n• If breathing, place on side\n• If not breathing, start CPR: Push hard and fast in center of chest\n• Loosen tight clothing'},
             
            {'keyword': 'not breathing', 'severity': 'CRITICAL',
             'response': '🚨 EMERGENCY - Person is not breathing. Call 911/112 NOW.\n\nSTART CPR:\n• Place person on back\n• Push hard and fast on center of chest\n• Continue until help arrives'},
             
            {'keyword': 'severe bleeding', 'severity': 'CRITICAL',
             'response': '🚨 SEVERE BLEEDING. Call 911/112 immediately.\n\nSTOP THE BLEEDING:\n• Apply firm pressure on wound with clean cloth\n• Do not remove cloth if blood soaks through\n• Keep person lying down and warm'},
             
            {'keyword': 'snake bite', 'severity': 'CRITICAL',
             'response': '🚨 SNAKE BITE. Call 911/112 NOW.\n\nDO:\n• Keep person calm and still\n• Remove tight clothing near bite\n• Try to remember snake color\n• Get to hospital immediately\n\nDO NOT cut wound or suck venom'},
             
            {'keyword': 'choking', 'severity': 'CRITICAL',
             'response': '🚨 CHOKING. Person cannot breathe.\n\nIF CONSCIOUS:\n• Stand behind them\n• Give abdominal thrusts\n\nIF UNCONSCIOUS:\n• Call 911/112\n• Start CPR'},
             
            {'keyword': 'heart attack', 'severity': 'CRITICAL',
             'response': '🚨 POSSIBLE HEART ATTACK. Call 911/112.\n\nWHILE WAITING:\n• Have person sit and rest\n• Loosen tight clothing\n• If aspirin available, give 300mg to chew'},
             
            {'keyword': 'seizure', 'severity': 'HIGH',
             'response': '⚠️ SEIZURE.\n\nDO:\n• Move objects away\n• Cushion head\n• Time the seizure\n• Roll on side after jerking stops\n\nCall 911 if lasts >5 minutes or first seizure'},
             
            {'keyword': 'drowning', 'severity': 'CRITICAL',
             'response': '🚨 DROWNING. Call 911/112.\n\n• Get person out of water safely\n• Check breathing\n• Start CPR if not breathing\n• Keep warm'},
             
            {'keyword': 'poison', 'severity': 'CRITICAL',
             'response': '🚨 POISONING. Call 911/112.\n\n• Find what they swallowed\n• Take container to hospital\n• If on skin, rinse with water\n• If fumes, get to fresh air'},
             
            {'keyword': 'burn', 'severity': 'HIGH',
             'response': '⚠️ BURN.\n\n• Cool with cool water for 20 minutes\n• Remove jewelry before swelling\n• Cover with clean cloth\n\nGo to hospital if burn is large or deep'},
        ]

        for em in emergency_list:
            EmergencyKeyword.objects.create(
                keyword=em['keyword'],
                severity=em['severity'],
                response_message=em['response']
            )
        
        # Alternative keywords for common variations
        alt_emergency_keywords = [
            {'keyword': 'unconcious', 'severity': 'CRITICAL', 
             'response': '🚨 Unconscious person. Call 911/112 NOW. Check breathing.'},
            {'keyword': 'fainting', 'severity': 'HIGH',
             'response': '⚠️ Person fainted. Lay them flat, raise legs. Call if not waking.'},
            {'keyword': 'convulsions', 'severity': 'HIGH',
             'response': '⚠️ Seizure. Clear area, cushion head. Call if >5 minutes.'},
            {'keyword': 'bleeding', 'severity': 'HIGH',
             'response': '⚠️ Bleeding. Apply pressure. Call if severe.'},
        ]
        
        for em in alt_emergency_keywords:
            EmergencyKeyword.objects.create(
                keyword=em['keyword'],
                severity=em['severity'],
                response_message=em['response']
            )
