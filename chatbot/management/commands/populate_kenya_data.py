from django.core.management.base import BaseCommand
from chatbot.models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword

class Command(BaseCommand):
    help = 'Populate database with Kenyan medical data'
    
    def handle(self, *args, **options):
        self.stdout.write('Populating Kenyan medical data...')
        
        # Clear existing data
        Disease.objects.all().delete()
        Symptom.objects.all().delete()
        FirstAidProcedure.objects.all().delete()
        EmergencyKeyword.objects.all().delete()
        
        # 1. Create Symptoms
        symptoms = {
            'fever': Symptom.objects.create(
                name='fever',
                alternative_names='high temperature, hot body, sweating, chills'
            ),
            'headache': Symptom.objects.create(
                name='headache',
                alternative_names='head pain, migraine, throbbing head'
            ),
            'cough': Symptom.objects.create(
                name='cough',
                alternative_names='coughing, dry cough, wet cough, chest cough'
            ),
            'diarrhea': Symptom.objects.create(
                name='diarrhea',
                alternative_names='diarrhoea, loose stools, running stomach, watery stool'
            ),
            'vomiting': Symptom.objects.create(
                name='vomiting',
                alternative_names='throwing up, nausea, sick stomach'
            ),
            'fatigue': Symptom.objects.create(
                name='fatigue',
                alternative_names='tiredness, weakness, exhaustion, lethargy'
            ),
            'chest_pain': Symptom.objects.create(
                name='chest pain',
                alternative_names='chest discomfort, heart pain, tight chest'
            ),
            'difficulty_breathing': Symptom.objects.create(
                name='difficulty breathing',
                alternative_names='shortness of breath, breathlessness, can\'t breathe'
            ),
        }
        
        # 2. Create Diseases (Kenyan common conditions)
        diseases = {
            'malaria': Disease.objects.create(
                name='Malaria',
                description='Common mosquito-borne disease in Kenya',
                common_symptoms='fever, chills, headache, sweating, fatigue'
            ),
            'pneumonia': Disease.objects.create(
                name='Pneumonia',
                description='Lung infection common during rainy season',
                common_symptoms='cough, difficulty breathing, chest pain, fever'
            ),
            'typhoid': Disease.objects.create(
                name='Typhoid',
                description='Bacterial infection from contaminated food/water',
                common_symptoms='fever, headache, fatigue, stomach pain, diarrhea'
            ),
            'chikungunya': Disease.objects.create(
                name='Chikungunya',
                description='Viral disease transmitted by mosquitoes',
                common_symptoms='fever, joint pain, headache, rash, fatigue'
            ),
        }
        
        # Link symptoms to diseases
        diseases['malaria'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue']
        )
        diseases['pneumonia'].symptoms.add(
            symptoms['cough'], symptoms['difficulty_breathing'], 
            symptoms['chest_pain'], symptoms['fever']
        )
        diseases['typhoid'].symptoms.add(
            symptoms['fever'], symptoms['headache'], 
            symptoms['fatigue'], symptoms['diarrhea']
        )
        diseases['chikungunya'].symptoms.add(
            symptoms['fever'], symptoms['headache'], symptoms['fatigue']
        )
        
        # 3. Create First Aid Procedures
        FirstAidProcedure.objects.create(
            disease=diseases['malaria'],
            title='Malaria First Aid',
            steps='1. Rest in a cool, quiet place\n2. Take paracetamol for fever (if available)\n3. Drink plenty of clean water\n4. Use mosquito net to prevent further bites\n5. Go to the nearest health facility for a malaria test',
            warning_notes='Do not take anti-malarial drugs without testing. Malaria tests are free at public health facilities.',
            when_to_seek_help='Seek immediate help if: fever persists >24 hours, person is unconscious, or if it\'s a child under 5'
        )
        
        FirstAidProcedure.objects.create(
            disease=diseases['pneumonia'],
            title='Pneumonia First Aid',
            steps='1. Keep the person sitting upright to help breathing\n2. Loosen tight clothing\n3. Give plenty of fluids\n4. Use paracetamol for fever\n5. Seek medical help immediately',
            warning_notes='Pneumonia can be fatal if not treated promptly. Do not wait at home.',
            when_to_seek_help='Go to hospital IMMEDIATELY if: difficulty breathing, chest pain, or the person is a child/elderly'
        )
        
        FirstAidProcedure.objects.create(
            disease=diseases['typhoid'],
            title='Typhoid First Aid',
            steps='1. Rest and avoid solid foods\n2. Drink plenty of clean water\n3. Oral rehydration salts (ORS) if available\n4. Take paracetamol for fever\n5. Go to health facility for testing',
            warning_notes='Do not take antibiotics without prescription. Typhoid requires specific antibiotics.',
            when_to_seek_help='Seek help if: high fever >3 days, severe diarrhea, or blood in stool'
        )
        
        # 4. Create Emergency Keywords
        emergencies = [
            {
                'keyword': 'unconscious',
                'severity': 'CRITICAL',
                'response': '🚨 This is a LIFE-THREATENING EMERGENCY. The person is unconscious. Call 911 or 112 immediately. While waiting: Check if they are breathing, place them in recovery position if breathing, start CPR if not breathing.'
            },
            {
                'keyword': 'not breathing',
                'severity': 'CRITICAL',
                'response': '🚨 EMERGENCY! Person is not breathing. Call 911/112 NOW. Start CPR: Push hard and fast in center of chest (100-120 compressions per minute). Continue until help arrives.'
            },
            {
                'keyword': 'severe bleeding',
                'severity': 'CRITICAL',
                'response': '🚨 SEVERE BLEEDING EMERGENCY. Call 911/112 immediately. Apply firm pressure to wound with clean cloth. Do not remove cloth if blood soaks through - add more on top. Keep person warm and lying down.'
            },
            {
                'keyword': 'snake bite',
                'severity': 'CRITICAL',
                'response': '🚨 SNAKE BITE EMERGENCY. Call 911/112 NOW. Keep the person calm and still. Remove tight clothing/jewelry. Do NOT cut the wound or suck out venom. Try to remember snake color/pattern for treatment.'
            },
            {
                'keyword': 'choking',
                'severity': 'CRITICAL',
                'response': '🚨 CHOKING EMERGENCY. If person cannot breathe or speak: Stand behind them, wrap arms around waist, make fist above navel, thrust inward and upward (Heimlich maneuver). Call 911/112 if unsuccessful.'
            },
            {
                'keyword': 'heart attack',
                'severity': 'CRITICAL',
                'response': '🚨 POSSIBLE HEART ATTACK. Call 911/112 immediately. Have person sit and rest. If conscious, give aspirin (if available and not allergic). Loosen tight clothing. Be ready to start CPR.'
            },
        ]
        
        for em in emergencies:
            EmergencyKeyword.objects.create(
                keyword=em['keyword'],
                severity=em['severity'],
                response_message=em['response']
            )
        
        self.stdout.write(self.style.SUCCESS('✅ Kenyan medical data populated successfully!'))
        self.stdout.write(f'   • {Disease.objects.count()} diseases added')
        self.stdout.write(f'   • {Symptom.objects.count()} symptoms added')
        self.stdout.write(f'   • {FirstAidProcedure.objects.count()} first aid procedures added')
        self.stdout.write(f'   • {EmergencyKeyword.objects.count()} emergency keywords added')