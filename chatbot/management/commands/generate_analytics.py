# chatbot/management/commands/generate_analytics.py
from django.core.management.base import BaseCommand
from chatbot.analytics import run_daily_analytics_job

class Command(BaseCommand):
    help = 'Generate daily analytics for the chatbot'

    def handle(self, *args, **options):
        self.stdout.write("Generating daily analytics...")
        result = run_daily_analytics_job()
        
        if result:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully generated analytics for {result.date}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR("Failed to generate analytics")
            )
