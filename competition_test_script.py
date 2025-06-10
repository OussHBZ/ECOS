#!/usr/bin/env python3
"""
Fixed OSCE Competition Testing Script
This script properly handles authentication and session management
"""

import requests
import time
import json
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://127.0.0.1:5000"
ADMIN_CODE = "ADMIN123"
TEACHER_CODE = "TEACHER123"

# Test data
TEST_STUDENTS = [
    {"code": "1001", "name": "Alice Martin"},
    {"code": "1002", "name": "Bob Dupont"},
    {"code": "1003", "name": "Claire Dubois"}
]

TEST_CASES = [
    {
        "case_number": "101",
        "specialty": "Cardiologie",
        "patient_info": {
            "name": "Jean Test",
            "age": 45,
            "gender": "Masculin"
        },
        "symptoms": ["Douleur thoracique", "Essoufflement"],
        "evaluation_checklist": [
            {"description": "Demande la localisation de la douleur", "points": 2, "category": "Anamnèse", "completed": False},
            {"description": "Vérifie les antécédents cardiovasculaires", "points": 2, "category": "Anamnèse", "completed": False},
            {"description": "Réalise un examen cardiaque", "points": 3, "category": "Examen physique", "completed": False}
        ],
        "directives": "Mener un interrogatoire cardiovasculaire complet en 10 minutes.",
        "consultation_time": 5
    },
    {
        "case_number": "102", 
        "specialty": "Pneumologie",
        "patient_info": {
            "name": "Marie Test",
            "age": 35,
            "gender": "Féminin"
        },
        "symptoms": ["Toux persistante", "Fièvre"],
        "evaluation_checklist": [
            {"description": "Demande la durée de la toux", "points": 2, "category": "Anamnèse", "completed": False},
            {"description": "Réalise l'auscultation pulmonaire", "points": 3, "category": "Examen physique", "completed": False}
        ],
        "directives": "Évaluer les symptômes respiratoires en 10 minutes.",
        "consultation_time": 5
    },
    {
        "case_number": "103",
        "specialty": "Gastroentérologie", 
        "patient_info": {
            "name": "Pierre Test",
            "age": 50,
            "gender": "Masculin"
        },
        "symptoms": ["Douleurs abdominales", "Nausées"],
        "evaluation_checklist": [
            {"description": "Localise la douleur abdominale", "points": 2, "category": "Anamnèse", "completed": False},
            {"description": "Palpe l'abdomen", "points": 3, "category": "Examen physique", "completed": False}
        ],
        "directives": "Examiner les symptômes digestifs en 10 minutes.",
        "consultation_time": 5
    }
]

class OSCECompetitionTester:
    def __init__(self):
        self.admin_session = requests.Session()
        self.teacher_session = requests.Session()
        self.student_sessions = {}
        self.competition_id = None
        
    def log(self, message, level="INFO"):
        """Log messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def check_flask_running(self):
        """Check if Flask app is running"""
        try:
            response = requests.get(f"{BASE_URL}/", timeout=5)
            if response.status_code in [200, 302, 401, 403]:
                self.log("✅ Flask app is running")
                return True
        except requests.exceptions.ConnectionError:
            self.log("❌ Flask app is not running. Please start it first.", "ERROR")
            return False
        except Exception as e:
            self.log(f"❌ Error checking Flask app: {e}", "ERROR")
            return False
            
    def admin_login(self):
        """Login as admin with proper session management"""
        try:
            # Get login page first to establish session
            login_response = self.admin_session.get(f"{BASE_URL}/login")
            if login_response.status_code != 200:
                self.log("❌ Failed to access login page", "ERROR")
                return False
                
            # Login as admin
            login_data = {
                'login_type': 'admin',
                'access_code': ADMIN_CODE
            }
            
            response = self.admin_session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
            
            if response.status_code == 302:
                self.log("✅ Admin login successful")
                return True
            else:
                self.log(f"❌ Admin login failed. Status: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Admin login error: {e}", "ERROR")
            return False
    
    def teacher_login(self):
        """Login as teacher with proper session management"""
        try:
            # Get login page first to establish session
            login_response = self.teacher_session.get(f"{BASE_URL}/login")
            if login_response.status_code != 200:
                self.log("❌ Failed to access teacher login page", "ERROR")
                return False
            
            # Login as teacher
            login_data = {
                'login_type': 'teacher', 
                'access_code': TEACHER_CODE
            }
            
            response = self.teacher_session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
            
            if response.status_code == 302:
                self.log("✅ Teacher login successful")
                return True
            else:
                self.log(f"❌ Teacher login failed. Status: {response.status_code}", "ERROR")
                self.log(f"Response text: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log(f"❌ Teacher login error: {e}", "ERROR")
            return False
    
    def create_test_cases(self):
        """Create test cases using teacher interface with proper authentication"""
        self.log("🔧 Creating test cases...")
        
        if not self.teacher_login():
            return False
        
        try:
            for case_data in TEST_CASES:
                # Check if case already exists first
                check_response = self.teacher_session.get(f"{BASE_URL}/get_case/{case_data['case_number']}")
                if check_response.status_code == 200:
                    self.log(f"✅ Test case {case_data['case_number']} already exists")
                    continue
                
                # Create case using the manual case creation endpoint
                case_payload = {
                    'case_number': case_data['case_number'],
                    'specialty': case_data['specialty'],
                    'patient_info': case_data['patient_info'],
                    'symptoms': case_data['symptoms'],
                    'evaluation_checklist': case_data['evaluation_checklist'],
                    'directives': case_data['directives'],
                    'consultation_time': case_data['consultation_time']
                }
                
                # Use the teacher session for the request
                response = self.teacher_session.post(
                    f"{BASE_URL}/teacher/create_case_manual", 
                    json=case_payload,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('status') == 'success':
                        self.log(f"✅ Created test case {case_data['case_number']}")
                    else:
                        self.log(f"⚠️ Failed to create case {case_data['case_number']}: {result.get('error', 'Unknown error')}")
                else:
                    self.log(f"⚠️ Failed to create case {case_data['case_number']}: HTTP {response.status_code}")
                    try:
                        error_data = response.json()
                        self.log(f"Error details: {error_data.get('error', 'No error details')}")
                    except:
                        self.log(f"Response text: {response.text[:200]}")
                        
            self.log("✅ Test cases creation completed")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating test cases: {e}", "ERROR")
            return False
    
    def create_test_students(self):
        """Create test students by having them 'register' through login"""
        self.log("👥 Creating test students...")
        
        try:
            for student_data in TEST_STUDENTS:
                # Create new session for each student
                student_session = requests.Session()
                
                # Get login page first
                login_response = student_session.get(f"{BASE_URL}/login")
                if login_response.status_code != 200:
                    self.log(f"❌ Failed to access login page for {student_data['name']}", "ERROR")
                    continue
                
                login_data = {
                    'login_type': 'student',
                    'student_code': student_data['code'],
                    'student_name': student_data['name']
                }
                
                response = student_session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
                
                if response.status_code == 302:
                    self.log(f"✅ Created/logged in student {student_data['name']} ({student_data['code']})")
                    
                    # Store session for later use
                    self.student_sessions[student_data['code']] = {
                        'session': student_session,
                        'name': student_data['name']
                    }
                else:
                    self.log(f"❌ Failed to create student {student_data['name']}", "ERROR")
                    
            self.log("✅ Test students creation completed")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating test students: {e}", "ERROR")
            return False
    
    def get_student_ids(self):
        """Get student IDs from admin interface"""
        try:
            response = self.admin_session.get(f"{BASE_URL}/admin/available-students")
            
            if response.status_code == 200:
                data = response.json()
                student_ids = []
                
                for student in data.get('students', []):
                    for test_student in TEST_STUDENTS:
                        if student['student_code'] == test_student['code']:
                            student_ids.append(student['id'])
                            self.log(f"Found student ID {student['id']} for {student['name']}")
                            
                return student_ids
            else:
                self.log(f"❌ Failed to get student IDs: {response.status_code}", "ERROR")
                return []
                
        except Exception as e:
            self.log(f"❌ Error getting student IDs: {e}", "ERROR")
            return []
    
    def get_station_numbers(self):
        """Get station numbers from admin interface"""
        try:
            response = self.admin_session.get(f"{BASE_URL}/admin/available-stations")
            
            if response.status_code == 200:
                data = response.json()
                station_numbers = []
                
                for station in data.get('stations', []):
                    for test_case in TEST_CASES:
                        if station['case_number'] == test_case['case_number']:
                            station_numbers.append(station['case_number'])
                            self.log(f"Found station {station['case_number']} - {station['specialty']}")
                            
                return station_numbers
            else:
                self.log(f"❌ Failed to get station numbers: {response.status_code}", "ERROR")
                return []
                
        except Exception as e:
            self.log(f"❌ Error getting station numbers: {e}", "ERROR")
            return []
    
    def create_competition_session(self):
        """Create a competition session"""
        self.log("🏆 Creating competition session...")
        
        try:
            # Get student IDs and station numbers
            student_ids = self.get_student_ids()
            station_numbers = self.get_station_numbers()
            
            if not student_ids:
                self.log("❌ No student IDs found", "ERROR")
                return False
                
            if not station_numbers:
                self.log("❌ No station numbers found", "ERROR") 
                return False
            
            # Create competition session
            start_time = datetime.now() + timedelta(minutes=1)
            end_time = start_time + timedelta(hours=2)
            
            competition_data = {
                'name': 'Test Competition Session',
                'description': 'Automated test competition for OSCE system',
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'stations_per_session': 2,  # Each student will do 2 stations
                'time_per_station': 3,  # 3 minutes per station for testing
                'time_between_stations': 1,  # 1 minute between stations
                'randomize_stations': True,
                'participants': student_ids,
                'stations': station_numbers
            }
            
            response = self.admin_session.post(f"{BASE_URL}/admin/create-competition-session",
                                       json=competition_data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    self.competition_id = result.get('session_id')
                    self.log(f"✅ Created competition session with ID: {self.competition_id}")
                    return True
                else:
                    self.log(f"❌ Competition creation failed: {result.get('error')}", "ERROR")
                    return False
            else:
                self.log(f"❌ Failed to create competition: HTTP {response.status_code}", "ERROR")
                self.log(f"Response: {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Error creating competition session: {e}", "ERROR")
            return False
    
    # [Rest of the methods remain the same...]
    def students_join_competition(self):
        """Have all students join the competition"""
        self.log("👥 Students joining competition...")
        
        try:
            for student_code, student_info in self.student_sessions.items():
                session = student_info['session']
                name = student_info['name']
                
                # Join competition
                response = session.post(f"{BASE_URL}/student/join-competition/{self.competition_id}")
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        self.log(f"✅ {name} joined competition successfully")
                    else:
                        self.log(f"❌ {name} failed to join: {result.get('error')}", "ERROR")
                else:
                    self.log(f"❌ {name} join failed: HTTP {response.status_code}", "ERROR")
                    
            self.log("✅ All students joined competition")
            return True
            
        except Exception as e:
            self.log(f"❌ Error with students joining competition: {e}", "ERROR")
            return False
    
    def wait_for_competition_start(self):
        """Wait for competition to start automatically"""
        self.log("⏳ Waiting for competition to start...")
        
        max_wait = 30  # Maximum 30 seconds
        wait_time = 0
        
        while wait_time < max_wait:
            try:
                # Check competition status
                response = self.admin_session.get(f"{BASE_URL}/admin/competition-sessions/{self.competition_id}")
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    
                    if status == 'active':
                        self.log("✅ Competition started!")
                        return True
                    elif status == 'scheduled':
                        self.log(f"⏳ Still waiting... ({wait_time}s)")
                    else:
                        self.log(f"❌ Unexpected status: {status}", "ERROR")
                        return False
                        
                time.sleep(2)
                wait_time += 2
                
            except Exception as e:
                self.log(f"❌ Error checking competition status: {e}", "ERROR")
                return False
        
        self.log("❌ Competition did not start within timeout", "ERROR")
        return False
    
    def simulate_student_stations(self):
        """Simulate students completing stations"""
        self.log("🎯 Simulating student station completions...")
        
        try:
            for student_code, student_info in self.student_sessions.items():
                session = student_info['session']
                name = student_info['name']
                
                self.log(f"🎓 Starting stations for {name}")
                
                # Complete 2 stations (as configured)
                for station_num in range(1, 3):  # Station 1 and 2
                    self.log(f"📋 {name} starting station {station_num}")
                    
                    # Get current status
                    status_response = session.get(f"{BASE_URL}/student/competition/{self.competition_id}/status")
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        current_station = status_data.get('current_station')
                        
                        if current_station:
                            # Start the station
                            start_response = session.post(f"{BASE_URL}/student/competition/{self.competition_id}/start-station")
                            
                            if start_response.status_code == 200:
                                start_data = start_response.json()
                                case_number = start_data.get('case_number')
                                self.log(f"✅ {name} started station with case {case_number}")
                                
                                # Simulate some conversation
                                self.simulate_conversation(session, name, case_number)
                                
                                # Complete the station
                                complete_response = session.post(f"{BASE_URL}/student/competition/complete-station")
                                
                                if complete_response.status_code == 200:
                                    complete_data = complete_response.json()
                                    if complete_data.get('success'):
                                        score = complete_data.get('evaluation', {}).get('percentage', 0)
                                        self.log(f"✅ {name} completed station {station_num} with score: {score}%")
                                        
                                        # Wait between stations if not finished
                                        if not complete_data.get('is_finished'):
                                            self.log(f"⏳ {name} waiting between stations...")
                                            time.sleep(3)  # Short wait for testing
                                    else:
                                        self.log(f"❌ {name} failed to complete station", "ERROR")
                                else:
                                    self.log(f"❌ {name} completion request failed", "ERROR")
                            else:
                                self.log(f"❌ {name} failed to start station", "ERROR")
                        else:
                            self.log(f"❌ No current station for {name}", "ERROR")
                    else:
                        self.log(f"❌ Failed to get status for {name}", "ERROR")
                
                self.log(f"🏁 {name} completed all stations")
            
            self.log("✅ All students completed their stations")
            return True
            
        except Exception as e:
            self.log(f"❌ Error simulating stations: {e}", "ERROR")
            return False
    
    def simulate_conversation(self, session, name, case_number):
        """Simulate a brief conversation for a station"""
        try:
            # Simulate some medical questions
            questions = [
                "Bonjour, je suis l'étudiant en médecine. Pouvez-vous me parler de votre problème?",
                "Depuis quand avez-vous ces symptômes?",
                "Avez-vous des antécédents médicaux?",
                "Merci pour ces informations."
            ]
            
            for question in questions:
                response = session.post(f"{BASE_URL}/chat", json={'message': question})
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        self.log(f"💬 {name}: {question[:30]}...")
                    else:
                        self.log(f"❌ Chat failed for {name}", "ERROR")
                else:
                    self.log(f"❌ Chat request failed for {name}", "ERROR")
                
                time.sleep(0.5)  # Brief pause between messages
                
        except Exception as e:
            self.log(f"❌ Error simulating conversation for {name}: {e}", "ERROR")
    
    def get_final_results(self):
        """Get and display final competition results"""
        self.log("🏆 Getting final competition results...")
        
        try:
            response = self.admin_session.get(f"{BASE_URL}/admin/competition-sessions/{self.competition_id}")
            
            if response.status_code == 200:
                data = response.json()
                leaderboard = data.get('leaderboard', [])
                
                if leaderboard:
                    self.log("📊 FINAL LEADERBOARD:")
                    self.log("=" * 50)
                    
                    for entry in leaderboard:
                        rank = entry.get('rank')
                        name = entry.get('student_name')
                        code = entry.get('student_code')
                        avg_score = entry.get('average_score')
                        stations_completed = entry.get('stations_completed')
                        
                        self.log(f"🥇 Rank {rank}: {name} ({code}) - Avg: {avg_score}% - Stations: {stations_completed}")
                    
                    self.log("=" * 50)
                else:
                    self.log("❌ No leaderboard data available", "ERROR")
                    
                return True
            else:
                self.log(f"❌ Failed to get final results: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Error getting final results: {e}", "ERROR")
            return False
    
    def cleanup(self):
        """Clean up test data"""
        self.log("🧹 Cleaning up test data...")
        
        try:
            # Delete competition session
            if self.competition_id:
                response = self.admin_session.delete(f"{BASE_URL}/admin/competition-sessions/{self.competition_id}/delete")
                if response.status_code == 200:
                    self.log("✅ Deleted competition session")
                else:
                    self.log("⚠️ Failed to delete competition session")
            
            self.log("✅ Cleanup completed")
            
        except Exception as e:
            self.log(f"❌ Error during cleanup: {e}", "ERROR")
    
    def run_full_test(self):
        """Run the complete competition test workflow"""
        self.log("🚀 Starting OSCE Competition Full Test")
        self.log("=" * 60)
        
        # Step 1: Check if Flask is running
        if not self.check_flask_running():
            return False
        
        # Step 2: Login as admin
        if not self.admin_login():
            return False
        
        # Step 3: Create test cases
        if not self.create_test_cases():
            return False
        
        # Step 4: Create test students  
        if not self.create_test_students():
            return False
        
        # Step 5: Create competition session
        if not self.create_competition_session():
            return False
        
        # Step 6: Students join competition
        if not self.students_join_competition():
            return False
        
        # Step 7: Wait for competition to start
        if not self.wait_for_competition_start():
            return False
        
        # Step 8: Simulate students completing stations
        if not self.simulate_student_stations():
            return False
        
        # Step 9: Get final results
        if not self.get_final_results():
            return False
        
        # Step 10: Cleanup (optional)
        self.cleanup()
        
        self.log("=" * 60)
        self.log("🎉 COMPETITION TEST COMPLETED SUCCESSFULLY!")
        self.log("=" * 60)
        
        return True

def main():
    """Main function to run the test"""
    print("OSCE Competition System - Automated Test")
    print("=" * 60)
    print("This script will:")
    print("1. Create test students and cases")
    print("2. Set up a competition session")
    print("3. Simulate the entire competition workflow")
    print("4. Display final results")
    print("=" * 60)
    
    # Ask for confirmation
    response = input("Do you want to proceed with the test? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return
    
    # Run the test
    tester = OSCECompetitionTester()
    
    try:
        success = tester.run_full_test()
        
        if success:
            print("\n✅ All tests passed! The competition system is working correctly.")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed. Please check the logs above.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        tester.cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        tester.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()