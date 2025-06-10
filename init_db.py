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
    from models import db, Student, PatientCase, CompetitionSession
    import logging
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

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
                'student_station_assignments'
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
                print("Attempting to recreate all tables...")
                
                # Drop and recreate all tables
                db.drop_all()
                db.create_all()
                
                # Check again
                existing_tables = db.inspect(db.engine).get_table_names()
                still_missing = [table for table in tables_to_check if table not in existing_tables]
                
                if still_missing:
                    print(f"❌ Still missing tables: {still_missing}")
                    return False
                else:
                    print("✅ All tables created successfully on second attempt")
            
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