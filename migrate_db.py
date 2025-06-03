#!/usr/bin/env python3
"""
Updated database migration script to fix image relationship issues.
Run this script to update your database with the new CaseImage table and fix relationships.
"""

import os
import sys
import json
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Student, TeacherAccess, PatientCase, StudentPerformance, CaseImage

def migrate_database():
    """Create new tables and migrate existing image data"""
    
    app = create_app()
    
    with app.app_context():
        try:
            print("🔄 Starting database migration...")
            
            # Create all tables (this will create new ones and skip existing ones)
            db.create_all()
            
            # Check if new tables were created
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'case_images' in tables:
                print("✅ CaseImage table created successfully")
            else:
                print("ℹ️  CaseImage table already exists")
                
            if 'student_performance' in tables:
                print("✅ StudentPerformance table exists")
            else:
                print("⚠️  StudentPerformance table missing")
            
            # Migrate existing image data from JSON files to database
            migrate_images_from_json()
            
            print("🎉 Database migration completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            return False

def migrate_images_from_json():
    """Migrate image data from JSON files to the database"""
    try:
        patient_data_folder = 'patient_data'
        
        if not os.path.exists(patient_data_folder):
            print("ℹ️  No patient_data folder found - skipping image migration")
            return
        
        # Get all JSON case files
        case_files = [f for f in os.listdir(patient_data_folder) 
                     if f.startswith('patient_case_') and f.endswith('.json')]
        
        if not case_files:
            print("ℹ️  No case files found - skipping image migration")
            return
        
        print(f"📁 Found {len(case_files)} case files, checking for images...")
        
        migrated_images = 0
        
        for case_file in case_files:
            try:
                # Extract case number from filename
                case_number = case_file.replace('patient_case_', '').replace('.json', '')
                
                # Load JSON data
                file_path = os.path.join(patient_data_folder, case_file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                # Check if case has images
                images = case_data.get('images', [])
                if not images:
                    continue
                
                print(f"📋 Case {case_number}: Found {len(images)} images")
                
                # Check if case exists in database
                db_case = PatientCase.query.filter_by(case_number=case_number).first()
                if not db_case:
                    print(f"⚠️  Case {case_number} not found in database - skipping image migration")
                    continue
                
                # Migrate each image
                for img_data in images:
                    # Check if image already exists in database
                    existing_img = CaseImage.query.filter_by(
                        case_number=case_number,
                        path=img_data.get('path', '')
                    ).first()
                    
                    if not existing_img:
                        # Create new image record
                        new_image = CaseImage(
                            case_number=case_number,
                            filename=img_data.get('filename', 'unknown'),
                            path=img_data.get('path', ''),
                            description=img_data.get('description', 'Image médicale')
                        )
                        db.session.add(new_image)
                        migrated_images += 1
                        print(f"   ➕ Added image: {new_image.filename}")
                
            except Exception as e:
                print(f"   ❌ Error processing {case_file}: {str(e)}")
                continue
        
        # Commit all changes
        if migrated_images > 0:
            db.session.commit()
            print(f"✅ Successfully migrated {migrated_images} images to database")
        else:
            print("ℹ️  No new images to migrate")
            
    except Exception as e:
        print(f"❌ Error during image migration: {str(e)}")
        db.session.rollback()

def verify_migration():
    """Verify that the migration was successful"""
    app = create_app()
    
    with app.app_context():
        try:
            print("\n🔍 Verifying migration...")
            
            # Check tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            expected_tables = ['student', 'teacher_access', 'patient_case1', 'student_performance', 'case_images']
            missing_tables = [table for table in expected_tables if table not in tables]
            
            if missing_tables:
                print(f"❌ Missing tables: {missing_tables}")
                return False
            else:
                print("✅ All required tables exist")
            
            # Test relationships
            case_count = PatientCase.query.count()
            image_count = CaseImage.query.count()
            performance_count = StudentPerformance.query.count()
            
            print(f"📊 Database contents:")
            print(f"   📋 Cases: {case_count}")
            print(f"   🖼️  Images: {image_count}")
            print(f"   📈 Performances: {performance_count}")
            
            # Test a case with images
            case_with_images = PatientCase.query.filter(PatientCase.images.any()).first()
            if case_with_images:
                print(f"   ✅ Case {case_with_images.case_number} has {len(case_with_images.images)} images")
            
            print("✅ Migration verification completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Error during verification: {str(e)}")
            return False

def fix_existing_cases():
    """Fix existing cases that might be missing image relationships"""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔧 Fixing existing cases...")
            
            # Ensure all existing cases have proper structure
            cases = PatientCase.query.all()
            
            for case in cases:
                try:
                    # Test that the case data can be loaded
                    case_data = case.to_json_data()
                    if 'images' not in case_data:
                        print(f"⚠️  Case {case.case_number} missing images structure")
                    else:
                        print(f"✅ Case {case.case_number} structure OK")
                        
                except Exception as e:
                    print(f"❌ Error with case {case.case_number}: {str(e)}")
            
            print("✅ Case fixing completed")
            
        except Exception as e:
            print(f"❌ Error fixing cases: {str(e)}")

def show_help():
    """Show help message"""
    print("""
🔧 Database Migration Utility for OSCE Simulator (Image Fix)

Usage:
    python migrate_db_fix.py [command]

Commands:
    migrate   - Run database migration with image fixes (default)
    verify    - Verify migration was successful
    fix       - Fix existing cases structure
    help      - Show this help message

Examples:
    python migrate_db_fix.py           # Run migration
    python migrate_db_fix.py migrate   # Same as above
    python migrate_db_fix.py verify    # Verify migration
    python migrate_db_fix.py fix       # Fix existing cases
    python migrate_db_fix.py help      # Show help
    """)

if __name__ == "__main__":
    import sys
    
    # Get command from command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    
    if command == 'migrate':
        success = migrate_database()
        if success:
            verify_migration()
    elif command == 'verify':
        verify_migration()
    elif command == 'fix':
        fix_existing_cases()
    elif command == 'help':
        show_help()
    else:
        print(f"❌ Unknown command: {command}")
        print("Run 'python migrate_db_fix.py help' for usage information")
        sys.exit(1)