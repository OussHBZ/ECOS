from app import create_app
from models import db # Make sure this imports your updated models

app = create_app()

with app.app_context():
    db.create_all()
    print("Database initialized successfully with all tables (including new ones)!")