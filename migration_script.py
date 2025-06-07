# migration_script.py - Database migration for competition sessions

"""
Database Migration Script for Competition Sessions
Run this script to migrate from the old session system to the new competition system.
"""

from flask import Flask
from models import db, OSCESession, SessionParticipant, SessionStationAssignment
from models import CompetitionSession, CompetitionParticipant, CompetitionStationBank, StudentCompetitionSession
from datetime import datetime
import os

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osce_simulator.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def migrate_sessions_to_competitions():
    """Migrate existing sessions to competition sessions"""
    print("Starting migration from sessions to competition sessions...")
    
    try:
        # Get all existing sessions
        old_sessions = OSCESession.query.all()
        
        if not old_sessions:
            print("No existing sessions found to migrate.")
            return
        
        print(f"Found {len(old_sessions)} sessions to migrate...")
        
        for old_session in old_sessions:
            print(f"Migrating session: {old_session.name}")
            
            # Create new competition session
            competition_session = CompetitionSession(
                name=old_session.name,
                description=old_session.description,
                start_time=old_session.start_time,
                end_time=old_session.end_time,
                created_at=old_session.created_at,
                created_by=old_session.created_by,
                status=old_session.status,
                # Default competition settings
                stations_per_session=3,  # Default value
                time_per_station=10,     # Default value
                time_between_stations=2,  # Default value
                randomize_stations=True
            )
            
            db.session.add(competition_session)
            db.session.flush()  # Get the ID
            
            # Migrate participants
            old_participants = SessionParticipant.query.filter_by(session_id=old_session.id).all()
            for old_participant in old_participants:
                # Create competition participant
                competition_participant = CompetitionParticipant(
                    session_id=competition_session.id,
                    student_id=old_participant.student_id,
                    added_at=old_participant.added_at
                )
                db.session.add(competition_participant)
                
                # Create student competition session
                student_session = StudentCompetitionSession(
                    session_id=competition_session.id,
                    student_id=old_participant.student_id,
                    status='registered'
                )
                db.session.add(student_session)
            
            # Migrate station assignments
            old_assignments = SessionStationAssignment.query.filter_by(session_id=old_session.id).all()
            for old_assignment in old_assignments:
                competition_station = CompetitionStationBank(
                    session_id=competition_session.id,
                    case_number=old_assignment.case_number,
                    added_at=old_assignment.assigned_at
                )
                db.session.add(competition_station)
            
            print(f"  - Migrated {len(old_participants)} participants")
            print(f"  - Migrated {len(old_assignments)} stations")
        
        # Commit all changes
        db.session.commit()
        print(f"Successfully migrated {len(old_sessions)} sessions to competition sessions!")
        
        # Optionally, drop old tables (uncomment if you want to remove old data)
        # print("Dropping old session tables...")
        # db.session.execute("DROP TABLE IF EXISTS session_station_assignment")
        # db.session.execute("DROP TABLE IF EXISTS session_participant")
        # db.session.execute("DROP TABLE IF EXISTS osce_session")
        # db.session.commit()
        # print("Old tables dropped.")
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        db.session.rollback()
        raise

def create_competition_tables():
    """Create new competition tables"""
    print("Creating competition session tables...")
    
    try:
        # Create all new tables
        db.create_all()
        print("Competition tables created successfully!")
        
    except Exception as e:
        print(f"Error creating tables: {str(e)}")
        raise

if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        print("=== OSCE Competition Migration ===")
        print("This script will migrate existing sessions to the new competition system.")
        
        response = input("Do you want to proceed? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            exit()
        
        # Backup database first
        print("Creating database backup...")
        import shutil
        backup_name = f"osce_simulator_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('osce_simulator.db', backup_name)
        print(f"Database backed up to: {backup_name}")
        
        try:
            # Create new tables
            create_competition_tables()
            
            # Migrate existing data
            migrate_sessions_to_competitions()
            
            print("\n=== Migration Complete ===")
            print("Your old session data has been migrated to the new competition system.")
            print(f"A backup of your original database is saved as: {backup_name}")
            print("\nNext steps:")
            print("1. Update your application code to use the new competition endpoints")
            print("2. Test the new competition functionality")
            print("3. If everything works correctly, you can delete the backup file")
            
        except Exception as e:
            print(f"\n=== Migration Failed ===")
            print(f"Error: {str(e)}")
            print(f"Your original database is backed up as: {backup_name}")
            print("You can restore it by replacing osce_simulator.db with the backup file.")
            
            # Restore from backup
            restore = input("Do you want to restore from backup now? (y/N): ")
            if restore.lower() == 'y':
                shutil.copy2(backup_name, 'osce_simulator.db')
                print("Database restored from backup.")
            
            exit(1)