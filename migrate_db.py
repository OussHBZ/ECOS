#!/usr/bin/env python3
"""
Database migration script to add new performance tracking tables.
Run this script to update your database with the new StudentPerformance table.
"""

import os
import sys
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Student, TeacherAccess, PatientCase, StudentPerformance

def migrate_database():
    """Create new tables and update existing ones"""
    
    app = create_app()
    
    with app.app_context():
        try:
            print("🔄 Starting database migration...")
            
            # Create all tables (this will create new ones and skip existing ones)
            db.create_all()
            
            # Check if StudentPerformance table was created
            if StudentPerformance.query.first() is None:
                print("✅ StudentPerformance table created successfully")
            else:
                print("✅ StudentPerformance table already exists")
            
            # Verify all tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            expected_tables = ['student', 'teacher_access', 'patient_case1', 'student_performance']
            missing_tables = [table for table in expected_tables if table not in tables]
            
            if missing_tables:
                print(f"⚠️  Missing tables: {missing_tables}")
                return False
            else:
                print("✅ All required tables exist")
            
            # Add some sample performance data if needed (optional)
            # create_sample_performance_data()
            
            print("🎉 Database migration completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            return False

def create_sample_performance_data():
    """Create some sample performance data for testing (optional)"""
    try:
        # Check if we have students and cases
        students = Student.query.all()
        cases = PatientCase.query.all()
        
        if not students or not cases:
            print("⚠️  No students or cases found - skipping sample data creation")
            return
        
        # Create sample performance for first student and first case
        sample_student = students[0]
        sample_case = cases[0]
        
        # Check if performance already exists
        existing_perf = StudentPerformance.query.filter_by(
            student_id=sample_student.id,
            case_number=sample_case.case_number
        ).first()
        
        if not existing_perf:
            sample_evaluation = {
                'points_earned': 8,
                'points_total': 10,
                'percentage': 80.0,
                'checklist': [],
                'feedback': 'Sample consultation evaluation'
            }
            
            sample_recommendations = [
                'Continue practicing patient communication',
                'Review diagnostic procedures',
                'Focus on time management'
            ]
            
            performance = StudentPerformance.create_from_evaluation(
                student_id=sample_student.id,
                case_number=sample_case.case_number,
                evaluation_results=sample_evaluation,
                recommendations=sample_recommendations,
                consultation_duration=600,  # 10 minutes
                time_remaining=0
            )
            
            db.session.add(performance)
            db.session.commit()
            print("✅ Sample performance data created")
        else:
            print("✅ Sample performance data already exists")
            
    except Exception as e:
        print(f"⚠️  Error creating sample data: {str(e)}")
        db.session.rollback()

def verify_migration():
    """Verify that the migration was successful"""
    app = create_app()
    
    with app.app_context():
        try:
            print("\n🔍 Verifying migration...")
            
            # Test StudentPerformance model
            performance_count = StudentPerformance.query.count()
            print(f"📊 StudentPerformance records: {performance_count}")
            
            # Test relationships
            students = Student.query.all()
            for student in students[:3]:  # Check first 3 students
                perf_count = len(student.performances)
                total_workouts = student.get_total_workouts()
                unique_stations = student.get_unique_stations_played()
                avg_score = student.get_average_score()
                
                print(f"👤 {student.name}: {perf_count} performances, {total_workouts} workouts, {unique_stations} stations, {avg_score}% avg")
            
            # Test PatientCase enhancements
            cases = PatientCase.query.all()
            for case in cases[:3]:  # Check first 3 cases
                completion_count = case.get_completion_count()
                avg_score = case.get_average_score()
                print(f"📋 Case {case.case_number}: {completion_count} completions, {avg_score}% avg score")
            
            print("✅ Migration verification completed successfully!")
            
        except Exception as e:
            print(f"❌ Error during verification: {str(e)}")

def rollback_migration():
    """Rollback migration (use with caution)"""
    app = create_app()
    
    with app.app_context():
        response = input("⚠️  Are you sure you want to DROP the StudentPerformance table? This will delete all performance data! (yes/no): ")
        
        if response.lower() == 'yes':
            try:
                # Drop only the new table
                StudentPerformance.__table__.drop(db.engine, checkfirst=True)
                print("🗑️  StudentPerformance table dropped successfully")
            except Exception as e:
                print(f"❌ Error during rollback: {str(e)}")
        else:
            print("❌ Rollback cancelled")

def show_help():
    """Show help message"""
    print("""
🔧 Database Migration Utility for OSCE Simulator

Usage:
    python migrate_db.py [command]

Commands:
    migrate   - Run database migration (default)
    verify    - Verify migration was successful
    rollback  - Rollback migration (DANGEROUS - deletes data)
    help      - Show this help message

Examples:
    python migrate_db.py           # Run migration
    python migrate_db.py migrate   # Same as above
    python migrate_db.py verify    # Verify migration
    python migrate_db.py rollback  # Rollback (DANGEROUS)
    python migrate_db.py help      # Show help
    """)

if __name__ == "__main__":
    import sys
    
    # Get command from command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    
    if command == 'migrate':
        migrate_database()
    elif command == 'verify':
        verify_migration()
    elif command == 'rollback':
        rollback_migration()
    elif command == 'help':
        show_help()
    else:
        print(f"❌ Unknown command: {command}")
        print("Run 'python migrate_db.py help' for usage information")
        sys.exit(1)