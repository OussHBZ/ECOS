#!/usr/bin/env python3
"""
Utility script to synchronize existing JSON case files with the database.
Run this script to populate the database with existing cases.
"""

import os
import json
import sys
from datetime import datetime

# Add the parent directory to the Python path so we can import our models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, PatientCase

def sync_json_to_database():
    """Synchronize all JSON case files with the database"""
    
    app = create_app()
    
    with app.app_context():
        # Ensure database tables exist
        db.create_all()
        
        patient_data_folder = 'patient_data'
        
        if not os.path.exists(patient_data_folder):
            print(f"❌ Patient data folder '{patient_data_folder}' not found!")
            return
        
        # Get all JSON case files
        case_files = [f for f in os.listdir(patient_data_folder) 
                     if f.startswith('patient_case_') and f.endswith('.json')]
        
        if not case_files:
            print("❌ No case files found in patient_data folder!")
            return
        
        print(f"📁 Found {len(case_files)} case files")
        print("🔄 Starting synchronization...\n")
        
        synced_count = 0
        error_count = 0
        
        for case_file in sorted(case_files):
            file_path = os.path.join(patient_data_folder, case_file)
            
            try:
                # Extract case number from filename
                case_number = case_file.replace('patient_case_', '').replace('.json', '')
                
                # Load JSON data
                with open(file_path, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                print(f"📄 Processing case {case_number}...")
                
                # Check if case already exists in database
                existing_case = PatientCase.query.filter_by(case_number=case_number).first()
                
                if existing_case:
                    print(f"   ✏️  Updating existing database record")
                    existing_case.update_from_json_data(case_data)
                else:
                    print(f"   ➕ Creating new database record")
                    new_case = PatientCase.from_json_data(case_data)
                    db.session.add(new_case)
                
                # Commit after each case to avoid losing progress
                db.session.commit()
                synced_count += 1
                print(f"   ✅ Successfully synchronized case {case_number}")
                
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON parsing error in {case_file}: {str(e)}")
                error_count += 1
                
            except Exception as e:
                print(f"   ❌ Error processing {case_file}: {str(e)}")
                db.session.rollback()
                error_count += 1
            
            print()  # Empty line for readability
        
        print("=" * 50)
        print(f"📊 Synchronization Summary:")
        print(f"   ✅ Successfully synchronized: {synced_count} cases")
        print(f"   ❌ Errors: {error_count} cases")
        print(f"   📁 Total files processed: {len(case_files)}")
        print("=" * 50)
        
        if synced_count > 0:
            print("🎉 Database synchronization completed successfully!")
            
            # Verify the synchronization
            total_db_cases = PatientCase.query.count()
            print(f"📈 Total cases now in database: {total_db_cases}")
            
        else:
            print("⚠️  No cases were synchronized. Please check for errors above.")

def verify_database_sync():
    """Verify that the database contains the expected cases"""
    
    app = create_app()
    
    with app.app_context():
        print("\n🔍 Verifying database synchronization...")
        
        # Get all cases from database
        db_cases = PatientCase.query.all()
        
        print(f"📊 Database contains {len(db_cases)} cases:")
        
        for case in db_cases:
            print(f"   📋 Case {case.case_number}: {case.specialty}")
            print(f"      👤 Patient: {json.loads(case.patient_info_json).get('name', 'N/A') if case.patient_info_json else 'N/A'}")
            print(f"      🏥 Symptoms: {len(json.loads(case.symptoms_json)) if case.symptoms_json else 0}")
            print(f"      📝 Checklist items: {len(json.loads(case.evaluation_checklist_json)) if case.evaluation_checklist_json else 0}")
            print(f"      📅 Created: {case.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"      📅 Updated: {case.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

def clean_database():
    """Remove all cases from database (useful for testing)"""
    
    app = create_app()
    
    with app.app_context():
        response = input("⚠️  Are you sure you want to DELETE ALL cases from the database? (yes/no): ")
        
        if response.lower() == 'yes':
            try:
                count = PatientCase.query.count()
                PatientCase.query.delete()
                db.session.commit()
                print(f"🗑️  Successfully deleted {count} cases from database")
            except Exception as e:
                print(f"❌ Error cleaning database: {str(e)}")
                db.session.rollback()
        else:
            print("❌ Database cleaning cancelled")

def show_help():
    """Show help message"""
    print("""
🔧 Database Synchronization Utility for OSCE Simulator

Usage:
    python sync_database.py [command]

Commands:
    sync     - Synchronize JSON files with database (default)
    verify   - Show database contents
    clean    - Remove all cases from database
    help     - Show this help message

Examples:
    python sync_database.py           # Sync JSON files to database
    python sync_database.py sync      # Same as above
    python sync_database.py verify    # Show database contents
    python sync_database.py clean     # Clean database
    python sync_database.py help      # Show help
    """)

if __name__ == "__main__":
    import sys
    
    # Get command from command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else 'sync'
    
    if command == 'sync':
        sync_json_to_database()
    elif command == 'verify':
        verify_database_sync()
    elif command == 'clean':
        clean_database()
    elif command == 'help':
        show_help()
    else:
        print(f"❌ Unknown command: {command}")
        print("Run 'python sync_database.py help' for usage information")
        sys.exit(1)