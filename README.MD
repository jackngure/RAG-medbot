# Kenya Medical Assistant Chatbot

A medical chatbot that provides first aid guidance for common Kenyan diseases and emergency assistance with hospital location services.

## Features

- 🩺 Symptom analysis using NLP (spaCy + NLTK)
- 🏥 First aid guidance for common Kenyan diseases
- 🚨 Emergency detection with automatic hospital locator
- 🗺️ Free OpenStreetMap integration for nearby hospitals
- 💬 Real-time chat interface

## Technologies Used

- Django 4.2
- PostgreSQL
- spaCy & NLTK for NLP
- Redis for caching
- OpenStreetMap + Leaflet.js
- RAG (Retrieval-Augmented Generation) for first aid retrieval

## Installation

1. Clone the repository
2. Create virtual environment: `python -m venv venv`
3. Activate: `venv\Scripts\activate`
4. Install requirements: `pip install -r requirements.txt`
5. Create PostgreSQL database
6. Copy `.env.example` to `.env` and configure
7. Run migrations: `python manage.py migrate`
8. Populate data: `python manage.py populate_kenya_data`
9. Run server: `python manage.py runserver`

## Usage

- Visit `http://localhost:8000`
- Describe your symptoms (e.g., "I have fever and headache")
- For emergencies, use words like "unconscious", "snake bite", "severe bleeding"