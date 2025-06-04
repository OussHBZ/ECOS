#!/usr/bin/env python3
"""
Database update script for OSCE Chat Simulator
Adds new tables for Administrator functionality
"""

from app import create_app
from models import db

def update_database():
    """Update the database with new tables for administrator functionality"""
    app = create_app()
    
    with app.app_context():
        try:
            print("Updating database with new tables...")
            
            # Create all tables (this will only create missing tables)
            db.create_all()
            
            print("✅ Database updated successfully!")
            print("\nNew tables added:")
            print("- admin_access: For administrator authentication tracking")
            print("- osce_session: For OSCE examination sessions")
            print("- session_participant: For tracking students in sessions")
            print("- session_station_assignment: For assigning stations to sessions")
            print("\nUpdated tables:")
            print("- student_performance: Added conversation_transcript field")
            
            print("\n🔧 Next steps:")
            print("1. Set your administrator access code in environment variables:")
            print("   export ADMIN_CODE='your_admin_code_here'")
            print("2. Restart your Flask application")
            print("3. Access the admin interface at /admin")
            
        except Exception as e:
            print(f"❌ Error updating database: {str(e)}")
            return False
    
    return True

if __name__ == "__main__":
    success = update_database()
    if not success:
        exit(1)