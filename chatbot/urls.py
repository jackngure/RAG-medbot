# chatbot/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_interface, name='chat'),
    path('process-message/', views.process_message, name='process_message'),
    path('get-nearby-hospitals/', views.get_nearby_hospitals, name='get_nearby_hospitals'),
]