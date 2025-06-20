# migration_apogee.py
"""
Database migration script to update student code from 4 digits to Numéro d'Apogée (6-7 digits)
Run this script to update the existing database structure
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app
    from models import db, Student
    import logging
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

def migrate_student_codes():
    """Migrate existing student codes and update database structure"""
    print("🔄 Starting Numéro d'Apogée migration...")
    
    # Create Flask app
    app = create_app()
    
    with app.app_context():
        try:
            # Get database inspector to check current structure
            inspector = db.inspect(db.engine)
            
            # Check if student table exists
            if 'student' not in inspector.get_table_names():
                print("❌ Student table not found. Please run init_db.py first.")
                return False
            
            # Get current column info
            columns = inspector.get_columns('student')
            student_code_column = None
            
            for col in columns:
                if col['name'] == 'student_code':
                    student_code_column = col
                    break
            
            if not student_code_column:
                print("❌ student_code column not found in student table")
                return False
            
            print(f"📋 Current student_code column type: {student_code_column['type']}")
            print(f"📋 Current student_code column length: {getattr(student_code_column['type'], 'length', 'Variable')}")
            
            # Check current constraints
            current_length = getattr(student_code_column['type'], 'length', None)
            
            if current_length and current_length >= 7:
                print("✅ Column already supports 6-7 digit codes")
            else:
                print("🔧 Updating student_code column to support 6-7 digits...")
                
                # For SQLite, we need to recreate the table
                # First, get all existing students
                existing_students = db.session.query(Student).all()
                student_data = []
                
                for student in existing_students:
                    student_data.append({
                        'id': student.id,
                        'student_code': student.student_code,
                        'name': student.name,
                        'created_at': student.created_at,
                        'last_login': student.last_login
                    })
                
                print(f"📊 Found {len(student_data)} existing students")
                
                # Create backup table
                db.engine.execute("""
                    CREATE TABLE student_backup AS 
                    SELECT * FROM student;
                """)
                
                # Drop the existing table
                db.engine.execute("DROP TABLE student;")
                
                # Recreate the table with new constraints
                # This will be handled by updating the model and calling db.create_all()
                print("🔄 Recreating student table with updated constraints...")
                db.create_all()
                
                # Restore data
                for student_info in student_data:
                    # Validate existing codes
                    code = student_info['student_code']
                    if len(code) < 6:
                        # Pad short codes with leading zeros to make them 6 digits
                        code = code.zfill(6)
                        print(f"📝 Padded student code {student_info['student_code']} to {code}")
                    
                    new_student = Student(
                        student_code=code,
                        name=student_info['name'],
                        created_at=student_info['created_at'],
                        last_login=student_info['last_login']
                    )
                    db.session.add(new_student)
                
                db.session.commit()
                print(f"✅ Restored {len(student_data)} students with updated codes")
                
                # Clean up backup table
                db.engine.execute("DROP TABLE student_backup;")
            
            # Verify the migration
            students = Student.query.all()
            print(f"\n📊 Migration Summary:")
            print(f"  - Total students: {len(students)}")
            
            for student in students:
                code_length = len(student.student_code)
                if code_length < 6 or code_length > 7:
                    print(f"  ⚠️  Warning: Student {student.name} has code '{student.student_code}' (length: {code_length})")
                else:
                    print(f"  ✅ Student {student.name}: {student.student_code} (length: {code_length})")
            
            print("\n✅ Migration completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            db.session.rollback()
            return False

def main():
    """Main function"""
    print("ECOS - Numéro d'Apogée Migration Tool")
    print("=" * 45)
    
    confirm = input("This will update the student code format from 4 digits to 6-7 digits (Numéro d'Apogée).\nDo you want to continue? (type 'YES' to confirm): ")
    
    if confirm != 'YES':
        print("Migration cancelled.")
        return False
    
    success = migrate_student_codes()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)