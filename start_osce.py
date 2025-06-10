#!/usr/bin/env python3
"""
OSCE Competition System Startup Script
This script ensures proper initialization and starts the Flask application
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Check if all requirements are installed"""
    print("🔍 Checking requirements...")
    
    try:
        import flask
        import flask_login
        import flask_sqlalchemy
        import langchain_groq
        import reportlab
        print("✅ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing requirement: {e}")
        print("Please install requirements with: pip install -r requirements.txt")
        return False

def check_env_file():
    """Check if .env file exists and has required variables"""
    print("🔍 Checking environment configuration...")
    
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️ .env file not found, creating one...")
        
        env_content = """# OSCE Competition System Environment Variables
GROQ_API_KEY=your_groq_api_key_here
TEACHER_CODE=TEACHER123
ADMIN_CODE=ADMIN123
FLASK_ENV=development
FLASK_DEBUG=True
"""
        
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("✅ Created .env file")
        print("⚠️ Please edit .env file and add your GROQ_API_KEY")
        return False
    
    # Check if GROQ_API_KEY exists
    with open('.env', 'r') as f:
        content = f.read()
        
    if 'GROQ_API_KEY=your_groq_api_key_here' in content or 'GROQ_API_KEY=' not in content:
        print("⚠️ Please set your GROQ_API_KEY in the .env file")
        return False
    
    print("✅ Environment configuration looks good")
    return True

def check_database():
    """Check if database is initialized"""
    print("🔍 Checking database...")
    
    db_file = Path('instance/osce_simulator.db')
    if not db_file.exists():
        print("⚠️ Database not found, initializing...")
        
        # Create instance directory
        os.makedirs('instance', exist_ok=True)
        
        # Initialize database
        try:
            from init_db import init_database
            if init_database():
                print("✅ Database initialized successfully")
                return True
            else:
                print("❌ Database initialization failed")
                return False
        except Exception as e:
            print(f"❌ Error initializing database: {e}")
            return False
    
    print("✅ Database exists")
    return True

def check_directories():
    """Check and create required directories"""
    print("🔍 Checking required directories...")
    
    required_dirs = [
        'static/images/cases',
        'uploads',
        'instance',
        'templates',
        'blueprints'
    ]
    
    for dir_path in required_dirs:
        os.makedirs(dir_path, exist_ok=True)
    
    print("✅ All directories are ready")
    return True

def create_response_template():
    """Create response template file if it doesn't exist"""
    print("🔍 Checking response template...")
    
    template_file = Path('response_template.json')
    if not template_file.exists():
        print("📄 Creating response template...")
        
        template_content = {
            "content": "Vous êtes un patient simulé dans un examen OSCE. Répondez aux questions de l'étudiant en médecine de manière réaliste selon les informations du cas médical fourni. Restez dans le rôle du patient et ne révélez pas d'informations que le patient ne connaîtrait pas normalement. Répondez en français."
        }
        
        import json
        with open('response_template.json', 'w', encoding='utf-8') as f:
            json.dump(template_content, f, ensure_ascii=False, indent=2)
        
        print("✅ Response template created")
    else:
        print("✅ Response template exists")
    
    return True

def start_application():
    """Start the Flask application"""
    print("🚀 Starting OSCE Competition System...")
    print("=" * 50)
    
    try:
        # Import and run the app
        from app import create_app
        
        app = create_app()
        
        print("✅ Flask application initialized")
        print("🌐 Starting server on http://127.0.0.1:5000")
        print("=" * 50)
        print("Available interfaces:")
        print("  👨‍🎓 Students: http://127.0.0.1:5000")
        print("  👨‍🏫 Teachers: http://127.0.0.1:5000") 
        print("  ⚙️  Admin: http://127.0.0.1:5000")
        print("=" * 50)
        print("Default access codes:")
        print("  Teacher: TEACHER123")
        print("  Admin: ADMIN123")
        print("=" * 50)
        print("Press Ctrl+C to stop the server")
        print()
        
        # Start the Flask development server
        app.run(debug=True, host='127.0.0.1', port=5000)
        
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main startup function"""
    print("OSCE Competition System Startup")
    print("=" * 40)
    
    # Run all checks
    checks = [
        ("Requirements", check_requirements),
        ("Environment", check_env_file),
        ("Directories", check_directories),
        ("Response Template", create_response_template),
        ("Database", check_database)
    ]
    
    failed_checks = []
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            failed_checks.append(check_name)
    
    if failed_checks:
        print(f"\n❌ Failed checks: {', '.join(failed_checks)}")
        print("Please fix the issues above before starting the application.")
        return False
    
    print("\n✅ All checks passed!")
    print("\n" + "=" * 40)
    
    # Ask user if they want to start
    response = input("Start the OSCE Competition System? (Y/n): ")
    if response.lower() in ['', 'y', 'yes']:
        return start_application()
    else:
        print("Startup cancelled.")
        return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)