from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from chatbot.models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword
import sys

class Command(BaseCommand):
    help = 'Populate database with Kenyan medical data (resets existing data)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt and force reset',
        )

    def handle(self, *args, **options):
        force = options['force']

        # Warn and ask for confirmation unless --force is used
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
        """Core data population logic – identical in effect to original but expanded."""
        # Clear existing data (same as before)
        Disease.objects.all().delete()
        Symptom.objects.all().delete()
        FirstAidProcedure.objects.all().delete()
        EmergencyKeyword.objects.all().delete()

        # 1. Create Symptoms (expanded list)
        symptoms_data = {
            'fever': ('fever', 'high temperature, hot body, sweating, chills'),
            'headache': ('headache', 'head pain, migraine, throbbing head'),
            'cough': ('cough', 'coughing, dry cough, wet cough, chest cough'),
            'diarrhea': ('diarrhea', 'diarrhoea, loose stools, running stomach, watery stool'),
            'vomiting': ('vomiting', 'throwing up, nausea, sick stomach'),
            'fatigue': ('fatigue', 'tiredness, weakness, exhaustion, lethargy'),
            'chest_pain': ('chest pain', 'chest discomfort, heart pain, tight chest'),
            'difficulty_breathing': ('difficulty breathing', 'shortness of breath, breathlessness, can\'t breathe'),
            'joint_pain': ('joint pain', 'joint ache, arthritis, pain in joints'),
            'muscle_pain': ('muscle pain', 'myalgia, body aches, sore muscles'),
            'rash': ('rash', 'skin rash, red spots, itching, hives'),
            'abdominal_pain': ('abdominal pain', 'stomach ache, belly pain, cramping'),
            'dehydration': ('dehydration', 'dry mouth, sunken eyes, reduced urine, thirsty'),
            'confusion': ('confusion', 'disoriented, altered mental state, delirium'),
        }

        symptoms = {}
        for key, (name, alt_names) in symptoms_data.items():
            symptoms[key] = Symptom.objects.create(
                name=name,
                alternative_names=alt_names
            )

        # 2. Create Diseases (expanded with more Kenyan‑common conditions)
        diseases_data = {
            'malaria': ('Malaria', 'Common mosquito‑borne disease in Kenya', 'fever, chills, headache, sweating, fatigue'),
            'pneumonia': ('Pneumonia', 'Lung infection common during rainy season', 'cough, difficulty breathing, chest pain, fever'),
            'typhoid': ('Typhoid', 'Bacterial infection from contaminated food/water', 'fever, headache, fatigue, stomach pain, diarrhea'),
            'chikungunya': ('Chikungunya', 'Viral disease transmitted by mosquitoes', 'fever, joint pain, headache, rash, fatigue'),
            'cholera': ('Cholera', 'Acute diarrheal illness from contaminated water', 'severe diarrhea, vomiting, dehydration, abdominal pain'),
            'dengue': ('Dengue', 'Viral infection spread by mosquitoes', 'fever, severe headache, joint and muscle pain, rash'),
            'rift_valley_fever': ('Rift Valley Fever', 'Viral disease common in livestock areas', 'fever, muscle pain, weakness, dizziness'),
            'meningitis': ('Meningitis', 'Inflammation of brain membranes', 'severe headache, fever, stiff neck, confusion'),
        }

        diseases = {}
        for key, (name, desc, symptoms_str) in diseases_data.items():
            diseases[key] = Disease.objects.create(
                name=name,
                description=desc,
                common_symptoms=symptoms_str
            )

        # 3. Link symptoms to diseases (maintain original relationships + new ones)
        diseases['malaria'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue']
        )
        diseases['pneumonia'].symptoms.add(
            symptoms['cough'], symptoms['difficulty_breathing'],
            symptoms['chest_pain'], symptoms['fever']
        )
        diseases['typhoid'].symptoms.add(
            symptoms['fever'], symptoms['headache'],
            symptoms['fatigue'], symptoms['diarrhea'], symptoms['abdominal_pain']
        )
        diseases['chikungunya'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue'],
            symptoms['joint_pain'], symptoms['rash']
        )
        diseases['cholera'].symptoms.add(
            symptoms['diarrhea'], symptoms['vomiting'], symptoms['dehydration'],
            symptoms['abdominal_pain']
        )
        diseases['dengue'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['joint_pain'],
            symptoms['muscle_pain'], symptoms['rash']
        )
        diseases['rift_valley_fever'].symptoms.add(
            symptoms['fever'], symptoms['muscle_pain'], symptoms['fatigue']
        )
        diseases['meningitis'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['confusion'],
            symptoms['vomiting']
        )

        # 4. Create First Aid Procedures (original + new)
        first_aid_data = [
            # Original ones
            (diseases['malaria'], 'Malaria First Aid',
             '1. Rest in a cool, quiet place\n2. Take paracetamol for fever (if available)\n3. Drink plenty of clean water\n4. Use mosquito net to prevent further bites\n5. Go to the nearest health facility for a malaria test',
             'Do not take anti-malarial drugs without testing. Malaria tests are free at public health facilities.',
             'Seek immediate help if: fever persists >24 hours, person is unconscious, or if it\'s a child under 5'),
            (diseases['pneumonia'], 'Pneumonia First Aid',
             '1. Keep the person sitting upright to help breathing\n2. Loosen tight clothing\n3. Give plenty of fluids\n4. Use paracetamol for fever\n5. Seek medical help immediately',
             'Pneumonia can be fatal if not treated promptly. Do not wait at home.',
             'Go to hospital IMMEDIATELY if: difficulty breathing, chest pain, or the person is a child/elderly'),
            (diseases['typhoid'], 'Typhoid First Aid',
             '1. Rest and avoid solid foods\n2. Drink plenty of clean water\n3. Oral rehydration salts (ORS) if available\n4. Take paracetamol for fever\n5. Go to health facility for testing',
             'Do not take antibiotics without prescription. Typhoid requires specific antibiotics.',
             'Seek help if: high fever >3 days, severe diarrhea, or blood in stool'),
            (diseases['chikungunya'], 'Chikungunya First Aid',
             '1. Rest and stay hydrated\n2. Use paracetamol for fever and pain (avoid aspirin/ibuprofen)\n3. Apply cold compresses to painful joints\n4. Sleep under a mosquito net',
             'Joint pain may persist for weeks or months. Avoid mosquito bites to prevent spreading.',
             'Seek medical help if: severe headache, vomiting, or symptoms worsen after fever subsides'),
            # New ones
            (diseases['cholera'], 'Cholera First Aid',
             '1. Start oral rehydration salts (ORS) immediately – mix 1 liter clean water with 6 teaspoons sugar and ½ teaspoon salt\n2. Continue breastfeeding if infant\n3. Seek medical help urgently\n4. Do not stop fluids even if vomiting',
             'Cholera can kill within hours from dehydration. Every minute counts.',
             'Go to health facility IMMEDIATELY if: severe diarrhea, vomiting, signs of dehydration (sunken eyes, dry mouth, little urine)'),
            (diseases['dengue'], 'Dengue First Aid',
             '1. Rest and drink plenty of fluids\n2. Use paracetamol for fever (avoid aspirin/ibuprofen – risk of bleeding)\n3. Watch for warning signs after fever subsides',
             'Dengue can cause sudden drop in platelets. Avoid non‑steroidal anti‑inflammatories.',
             'Seek urgent care if: severe abdominal pain, persistent vomiting, bleeding gums, fatigue, restlessness'),
            (diseases['meningitis'], 'Meningitis First Aid',
             '1. Seek medical help IMMEDIATELY – meningitis is a medical emergency\n2. Keep person comfortable and monitor breathing\n3. Do not give anything by mouth if confused',
             'Bacterial meningitis can progress rapidly. Early treatment saves lives.',
             'Call 911/112 NOW if: severe headache, fever, stiff neck, confusion, or purple rash'),
        ]

        for disease, title, steps, warning, when in first_aid_data:
            FirstAidProcedure.objects.create(
                disease=disease,
                title=title,
                steps=steps,
                warning_notes=warning,
                when_to_seek_help=when
            )

        # 5. Create Emergency Keywords (original set, plus a few more)
        emergency_list = [
            {'keyword': 'unconscious', 'severity': 'CRITICAL',
             'response': '🚨 This is a LIFE‑THREATENING EMERGENCY. The person is unconscious. Call 911 or 112 immediately. While waiting: Check if they are breathing, place them in recovery position if breathing, start CPR if not breathing.'},
            {'keyword': 'not breathing', 'severity': 'CRITICAL',
             'response': '🚨 EMERGENCY! Person is not breathing. Call 911/112 NOW. Start CPR: Push hard and fast in center of chest (100‑120 compressions per minute). Continue until help arrives.'},
            {'keyword': 'severe bleeding', 'severity': 'CRITICAL',
             'response': '🚨 SEVERE BLEEDING EMERGENCY. Call 911/112 immediately. Apply firm pressure to wound with clean cloth. Do not remove cloth if blood soaks through – add more on top. Keep person warm and lying down.'},
            {'keyword': 'snake bite', 'severity': 'CRITICAL',
             'response': '🚨 SNAKE BITE EMERGENCY. Call 911/112 NOW. Keep the person calm and still. Remove tight clothing/jewelry. Do NOT cut the wound or suck out venom. Try to remember snake color/pattern for treatment.'},
            {'keyword': 'choking', 'severity': 'CRITICAL',
             'response': '🚨 CHOKING EMERGENCY. If person cannot breathe or speak: Stand behind them, wrap arms around waist, make fist above navel, thrust inward and upward (Heimlich maneuver). Call 911/112 if unsuccessful.'},
            {'keyword': 'heart attack', 'severity': 'CRITICAL',
             'response': '🚨 POSSIBLE HEART ATTACK. Call 911/112 immediately. Have person sit and rest. If conscious, give aspirin (if available and not allergic). Loosen tight clothing. Be ready to start CPR.'},
            {'keyword': 'seizure', 'severity': 'HIGH',
             'response': '⚠️ SEIZURE. Do not restrain. Move objects away, cushion head. Time the seizure. Call 911/112 if lasts >5 minutes or person has never had seizures before.'},
            {'keyword': 'drowning', 'severity': 'CRITICAL',
             'response': '🚨 DROWNING EMERGENCY. Call 911/112 immediately. If person is not breathing, start CPR immediately – even in water if safe. Continue until help arrives.'},
        ]

        for em in emergency_list:
            EmergencyKeyword.objects.create(
                keyword=em['keyword'],
                severity=em['severity'],
                response_message=em['response']
            )
