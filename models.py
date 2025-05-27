from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(4), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def get_id(self):
        return f"student_{self.id}"

class TeacherAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)