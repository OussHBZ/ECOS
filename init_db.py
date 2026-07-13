#!/usr/bin/env python3
"""
Database Initialization Script for OSCE Competition System
Run this before starting the application to ensure all tables are created
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app
    from models import db, Student, Teacher, PatientCase, CompetitionSession, PathologyFolder
    import logging
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


KINE_PATHOLOGY_FOLDER_TRANSLATIONS = {
    'Ischemic heart disease': 'Cardiopathie ischémique',
    'Non-ischemic heart disease': 'Cardiopathie non ischémique',
    'Congenital heart disease': 'Cardiopathie congénitale',
    'Cardiac surgery': 'Chirurgie cardiaque',
    'Heart transplant': 'Transplantation cardiaque',
    'Hypertension (HTN)': 'Hypertension artérielle (HTA)',
    'Hemodynamic regulation': 'Régulation hémodynamique',
    'Peripheral arterial disease of the lower limbs (PAD)': 'Artériopathie oblitérante des membres inférieurs (AOMI)',
    'Special arterial diseases': 'Pathologies artérielles particulières',
    'Vascular compression syndromes': 'Syndromes de compression vasculaire',
    'Venous diseases': 'Pathologies veineuses',
    'Mild venous and lymphatic diseases': 'Pathologies veineuses et lymphatiques légères',
}

DEFAULT_KINE_PATHOLOGY_FOLDERS = list(KINE_PATHOLOGY_FOLDER_TRANSLATIONS.values())


def seed_default_accounts():
    """Create optional local-development accounts without overwriting users."""
    enabled = os.getenv('SEED_DEMO_ACCOUNTS', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    if not enabled:
        print("Demo account seeding disabled (SEED_DEMO_ACCOUNTS=false)")
        return

    accounts = [
        {
            'student_code': os.getenv('DEMO_LICENCE_CODE', '123456'),
            'name': 'Demo Licence Student', 'level': 'licence',
            'ecos_type': 'kine',
            'password': os.getenv('DEMO_LICENCE_PASSWORD', 'Student123!'),
        },
        {
            'student_code': os.getenv('DEMO_MASTER_CODE', '123457'),
            'name': 'Demo Master Student', 'level': 'master',
            'ecos_type': 'kine',
            'password': os.getenv('DEMO_MASTER_PASSWORD', 'Master123!'),
        },
    ]
    for account in accounts:
        student = Student.query.filter_by(student_code=account['student_code']).first()
        if not student:
            student = Student(student_code=account['student_code'], name=account['name'], level=account['level'], ecos_type=account['ecos_type'])
            student.set_password(account['password'])
            db.session.add(student)
        elif not student.password_hash:
            student.set_password(account['password'])
            student.level = student.level or account['level']
        student.ecos_type = account['ecos_type']

    teacher_email = os.getenv('DEMO_TEACHER_EMAIL', 'teacher@ecos.local').strip().lower()
    teacher = Teacher.query.filter_by(email=teacher_email).first()
    if not teacher:
        teacher = Teacher(email=teacher_email, name='Demo Kine Teacher', password_hash='temporary', ecos_type='kine')
        teacher.set_password(os.getenv('DEMO_TEACHER_PASSWORD', 'Teacher123!'))
        db.session.add(teacher)
    teacher.ecos_type = 'kine'
    db.session.commit()
    print("Demo teacher and Licence/Master student accounts are ready")


def apply_additive_schema_updates():
    """Add kine columns to legacy SQLite tables without deleting data."""
    inspector = db.inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    additions = {
        'student': {
            'level': "VARCHAR(20) DEFAULT 'licence'",
            'group_name': 'VARCHAR(100)',
            'class_name': 'VARCHAR(100)',
            'ecos_type': "VARCHAR(20) NOT NULL DEFAULT 'standard'",
        },
        'patient_case1': {
            'title': 'VARCHAR(250)',
            'folder_id': 'INTEGER REFERENCES pathology_folders(id)',
            'level': "VARCHAR(20) DEFAULT 'both'",
            'mode_availability': "VARCHAR(20) DEFAULT 'both'",
            'pedagogical_objectives': 'TEXT',
            'emotional_state': 'VARCHAR(50)',
            'is_archived': 'BOOLEAN NOT NULL DEFAULT 0',
        },
        'simulation_sessions': {
            'conversation': "JSON DEFAULT '[]'",
            'evaluation_results': 'JSON',
            'runtime_state': "JSON DEFAULT '{}'",
            'paused_at': 'DATETIME',
            'total_paused_seconds': 'INTEGER DEFAULT 0',
            'supplementary_score': 'FLOAT',
            'teacher_comments': 'TEXT',
            'reviewed_by': 'INTEGER REFERENCES teacher(id)',
            'reviewed_at': 'DATETIME',
        },
        'exams': {
            'group_names': "JSON DEFAULT '[]'",
        },
        'teacher': {
            'ecos_type': "VARCHAR(20) NOT NULL DEFAULT 'standard'",
        },
    }
    with db.engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {
                column['name'] for column in inspector.get_columns(table_name)
            }
            for column_name, definition in columns.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}'
                    )


def seed_pathology_folders():
    """Seed editable default kine folders idempotently."""
    existing_folders = PathologyFolder.query.filter_by(specialty='kine').all()
    for folder in existing_folders:
        if folder.name in KINE_PATHOLOGY_FOLDER_TRANSLATIONS:
            folder.name = KINE_PATHOLOGY_FOLDER_TRANSLATIONS[folder.name]
    existing_names = {folder.name for folder in existing_folders}
    for name in DEFAULT_KINE_PATHOLOGY_FOLDERS:
        if name not in existing_names:
            db.session.add(PathologyFolder(name=name, specialty='kine'))
    db.session.commit()

def init_database():
    """Initialize the database with all required tables"""
    print("🔧 Initializing OSCE Competition Database...")
    
    # Create Flask app
    app = create_app()
    
    with app.app_context():
        try:
            # Create all tables
            print("📋 Creating database tables...")
            db.create_all()
            apply_additive_schema_updates()
            seed_pathology_folders()
            seed_default_accounts()
            
            # Verify critical tables exist
            print("✅ Verifying table creation...")
            
            # Check main tables
            tables_to_check = [
                'student',
                'patient_case1', 
                'student_performance',
                'competition_sessions',
                'competition_participants',
                'competition_station_bank',
                'student_competition_sessions',
                'student_station_assignments',
                'pathology_folders',
                'patient_records',
                'interventions',
                'medications',
                'incidents',
                'evaluation_grids',
                'simulation_sessions',
                'exams',
                'exam_cases',
                'exam_students'
            ]
            
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            missing_tables = []
            for table in tables_to_check:
                if table in existing_tables:
                    print(f"  ✅ {table}")
                else:
                    print(f"  ❌ {table} - MISSING")
                    missing_tables.append(table)
            
            if missing_tables:
                print(f"\n❌ Missing tables: {missing_tables}")
                print("Existing data was left untouched; initialization cannot continue.")
                return False
            
            # Create some sample data for testing
            print("\n📊 Creating sample data...")
            
            # Check if we already have data
            student_count = Student.query.count()
            case_count = PatientCase.query.count()
            
            if student_count == 0:
                print("👥 Creating sample students...")
                sample_students = [
                    Student(student_code="9001", name="Test Student 1"),
                    Student(student_code="9002", name="Test Student 2"),
                    Student(student_code="9003", name="Test Student 3")
                ]
                
                for student in sample_students:
                    db.session.add(student)
                
                db.session.commit()
                print(f"✅ Created {len(sample_students)} sample students")
            else:
                print(f"ℹ️ Found {student_count} existing students")
            
            if case_count == 0:
                print("📋 Creating sample cases...")
                sample_cases = [
                    PatientCase(
                        case_number="TEST001",
                        specialty="Test Specialty",
                        patient_info_json='{"name": "Test Patient", "age": 40, "gender": "Test"}',
                        symptoms_json='["Test symptom 1", "Test symptom 2"]',
                        evaluation_checklist_json='[{"description": "Test evaluation", "points": 1, "category": "Test", "completed": false}]',
                        directives="Test directives for students",
                        consultation_time=10
                    )
                ]
                
                for case in sample_cases:
                    db.session.add(case)
                
                db.session.commit()
                print(f"✅ Created {len(sample_cases)} sample cases")
            else:
                print(f"ℹ️ Found {case_count} existing cases")
            
            print("\n✅ Database initialization completed successfully!")
            print("\nDatabase Summary:")
            print(f"  - Students: {Student.query.count()}")
            print(f"  - Cases: {PatientCase.query.count()}")
            print(f"  - Competition Sessions: {CompetitionSession.query.count()}")
            print(f"  - Kine pathology folders: {PathologyFolder.query.filter_by(specialty='kine').count()}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error during database initialization: {e}")
            import traceback
            traceback.print_exc()
            return False

def reset_database():
    """Reset the database (delete all data)"""
    print("⚠️  RESETTING DATABASE - ALL DATA WILL BE LOST!")
    response = input("Are you sure you want to continue? (type 'YES' to confirm): ")
    
    if response != 'YES':
        print("Database reset cancelled.")
        return False
    
    app = create_app()
    
    with app.app_context():
        try:
            print("🗑️ Dropping all tables...")
            db.drop_all()
            
            print("🔧 Recreating all tables...")
            db.create_all()
            seed_pathology_folders()
            seed_default_accounts()
            
            print("✅ Database reset completed!")
            return True
            
        except Exception as e:
            print(f"❌ Error during database reset: {e}")
            return False

def check_database():
    """Check database status"""
    print("🔍 Checking database status...")
    
    app = create_app()
    
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            print(f"📊 Found {len(existing_tables)} tables:")
            for table in sorted(existing_tables):
                print(f"  - {table}")
            
            # Count records in main tables
            print("\n📈 Record counts:")
            try:
                print(f"  - Students: {Student.query.count()}")
                print(f"  - Cases: {PatientCase.query.count()}")
                print(f"  - Competition Sessions: {CompetitionSession.query.count()}")
            except Exception as e:
                print(f"  ⚠️ Error counting records: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error checking database: {e}")
            return False

def main():
    """Main function"""
    print("OSCE Competition Database Manager")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'init':
            return init_database()
        elif command == 'reset':
            return reset_database()
        elif command == 'check':
            return check_database()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: init, reset, check")
            return False
    else:
        print("Available commands:")
        print("  python init_db.py init   - Initialize database")
        print("  python init_db.py reset  - Reset database (delete all data)")
        print("  python init_db.py check  - Check database status")
        print()
        
        response = input("What would you like to do? (init/reset/check): ").lower()
        
        if response == 'init':
            return init_database()
        elif response == 'reset':
            return reset_database()
        elif response == 'check':
            return check_database()
        else:
            print("Invalid option.")
            return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
