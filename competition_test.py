#!/usr/bin/env python3
"""
ECOS Competition Session Test Script
This script tests the complete competition workflow from admin creation to student completion.
"""

import requests
import json
import time
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://localhost:5000"
ADMIN_CODE = "ADMIN123"  # Change this to your admin code
TEACHER_CODE = "TEACHER123"  # Change this to your teacher code

# Test data
TEST_STUDENTS = [
    {"code": "1001", "name": "Alice Dupont"},
    {"code": "1002", "name": "Bob Martin"},
    {"code": "1003", "name": "Claire Rousseau"}
]

TEST_CASE = {
    "case_number": "TEST001",
    "specialty": "Cardiologie",
    "patient_info": {
        "name": "Patient Test",
        "age": 45,
        "gender": "Masculin",
        "occupation": "Ingénieur"
    },
    "symptoms": [
        "Douleur thoracique depuis 2 heures",
        "Essoufflement à l'effort",
        "Sensation d'oppression"
    ],
    "evaluation_checklist": [
        {"description": "Questionne sur la douleur thoracique", "points": 2, "category": "Anamnèse", "completed": False},
        {"description": "Évalue les facteurs de risque cardiovasculaire", "points": 2, "category": "Anamnèse", "completed": False},
        {"description": "Ausculte le cœur", "points": 3, "category": "Examen physique", "completed": False},
        {"description": "Prend la tension artérielle", "points": 2, "category": "Examen physique", "completed": False},
        {"description": "Explique les prochaines étapes", "points": 2, "category": "Communication", "completed": False}
    ],
    "diagnosis": "Syndrome coronarien aigu",
    "directives": "Vous devez évaluer ce patient qui présente une douleur thoracique. Durée: 10 minutes.",
    "consultation_time": 10
}

class CompetitionTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_logged_in = False
        self.created_students = []
        self.created_case = None
        self.competition_session_id = None
        self.student_sessions = {}

    def log(self, message, level="INFO"):
        """Log messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def test_connection(self):
        """Test if the server is running"""
        self.log("Testing server connection...")
        try:
            response = self.session.get(f"{BASE_URL}/")
            if response.status_code == 200:
                self.log("✓ Server is running")
                return True
            else:
                self.log(f"✗ Server responded with status {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"✗ Cannot connect to server: {e}", "ERROR")
            return False

    def admin_login(self):
        """Login as admin"""
        self.log("Logging in as admin...")
        try:
            # Get login page first
            response = self.session.get(f"{BASE_URL}/login")
            
            # Submit admin login
            login_data = {
                "login_type": "admin",
                "access_code": ADMIN_CODE
            }
            response = self.session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
            
            if "admin" in response.url:
                self.log("✓ Admin login successful")
                self.admin_logged_in = True
                return True
            else:
                self.log("✗ Admin login failed", "ERROR")
                return False
        except Exception as e:
            self.log(f"✗ Admin login error: {e}", "ERROR")
            return False

    def create_test_case(self):
        """Create a test case via teacher interface"""
        self.log("Creating test case...")
        try:
            # Create a separate session for teacher operations
            teacher_session = requests.Session()
            
            # Get login page first to establish session
            response = teacher_session.get(f"{BASE_URL}/login")
            if response.status_code != 200:
                self.log("✗ Could not access login page", "ERROR")
                return False
            
            # Login as teacher
            teacher_login_data = {
                "login_type": "teacher",
                "access_code": TEACHER_CODE
            }
            response = teacher_session.post(f"{BASE_URL}/login", data=teacher_login_data, allow_redirects=True)
            
            # Check if login was successful
            if response.status_code != 200 or "teacher" not in response.url:
                self.log(f"✗ Teacher login failed. Response: {response.status_code}, URL: {response.url}", "ERROR")
                return False
            
            self.log("✓ Teacher login successful")
            
            # Wait a moment for session to stabilize
            time.sleep(1)
            
            # Create case via API with proper headers
            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            response = teacher_session.post(
                f"{BASE_URL}/teacher/process_manual_case",
                data=self._prepare_form_data(),
                headers={"X-Requested-With": "XMLHttpRequest"}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    self.created_case = TEST_CASE["case_number"]
                    self.log(f"✓ Test case {self.created_case} created successfully")
                    return True
            
            self.log(f"✗ Failed to create test case: Status {response.status_code}, Response: {response.text}", "ERROR")
            return False
        except Exception as e:
            self.log(f"✗ Error creating test case: {e}", "ERROR")
            return False

    def _prepare_form_data(self):
        """Prepare form data for manual case creation"""
        form_data = {
            'case_number': TEST_CASE["case_number"],
            'specialty': TEST_CASE["specialty"],
            'patient_name': TEST_CASE["patient_info"]["name"],
            'patient_age': str(TEST_CASE["patient_info"]["age"]),
            'patient_gender': TEST_CASE["patient_info"]["gender"],
            'patient_occupation': TEST_CASE["patient_info"]["occupation"],
            'chief_complaint': "Douleur thoracique",
            'diagnosis': TEST_CASE["diagnosis"],
            'case_directives': TEST_CASE["directives"],
            'consultation_time': str(TEST_CASE["consultation_time"]),
            'symptoms[]': TEST_CASE["symptoms"],
            'checklist_descriptions[]': [item["description"] for item in TEST_CASE["evaluation_checklist"]],
            'checklist_points[]': [str(item["points"]) for item in TEST_CASE["evaluation_checklist"]],
            'checklist_categories[]': [item["category"] for item in TEST_CASE["evaluation_checklist"]]
        }
        return form_data

    def create_test_students(self):
        """Create test students"""
        self.log("Creating test students...")
        try:
            for student_data in TEST_STUDENTS:
                # Students are created automatically on first login
                # We'll simulate this by trying to login with each student
                login_data = {
                    "login_type": "student",
                    "student_code": student_data["code"],
                    "student_name": student_data["name"]
                }
                
                response = self.session.post(f"{BASE_URL}/login", data=login_data)
                
                if response.status_code in [200, 302]:
                    self.created_students.append(student_data)
                    self.log(f"✓ Student {student_data['name']} ({student_data['code']}) created/verified")
                else:
                    self.log(f"✗ Failed to create student {student_data['name']}", "ERROR")
            
            self.log(f"✓ {len(self.created_students)} students ready for testing")
            return len(self.created_students) > 0
        except Exception as e:
            self.log(f"✗ Error creating test students: {e}", "ERROR")
            return False

    def create_competition_session(self):
        """Create a competition session"""
        self.log("Creating competition session...")
        try:
            # Make sure we're logged in as admin with a fresh session
            admin_session = requests.Session()
            
            # Get login page first
            response = admin_session.get(f"{BASE_URL}/login")
            if response.status_code != 200:
                self.log("✗ Could not access login page", "ERROR")
                return False
            
            # Login as admin
            admin_login_data = {
                "login_type": "admin",
                "access_code": ADMIN_CODE
            }
            response = admin_session.post(f"{BASE_URL}/login", data=admin_login_data, allow_redirects=True)
            
            # Check if login was successful
            if response.status_code != 200 or "admin" not in response.url:
                self.log(f"✗ Admin login failed for competition creation", "ERROR")
                return False
            
            self.log("✓ Admin logged in for competition creation")
            
            # Get available students and stations first
            students_response = admin_session.get(f"{BASE_URL}/admin/available-students")
            stations_response = admin_session.get(f"{BASE_URL}/admin/available-stations")
            
            if students_response.status_code != 200 or stations_response.status_code != 200:
                self.log("✗ Could not get available students/stations", "ERROR")
                return False
            
            students_data = students_response.json()
            stations_data = stations_response.json()
            
            available_students = students_data.get("students", [])
            available_stations = stations_data.get("stations", [])
            
            if len(available_students) < 2:
                self.log(f"✗ Not enough students available: {len(available_students)}", "ERROR")
                return False
            
            if len(available_stations) < 1:
                self.log(f"✗ No stations available", "ERROR")
                return False
            
            # Use the first 3 students and first station
            participant_ids = [s["id"] for s in available_students[:3]]
            station_numbers = [available_stations[0]["case_number"]]
            
            self.log(f"Using students: {participant_ids} and stations: {station_numbers}")

            # Prepare session data
            start_time = (datetime.now() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
            end_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
            
            session_data = {
                "name": "Test Competition Session",
                "description": "Automated test competition session",
                "start_time": start_time,
                "end_time": end_time,
                "stations_per_session": 1,
                "time_per_station": 5,  # 5 minutes for quick testing
                "time_between_stations": 1,  # 1 minute between stations
                "randomize_stations": False,
                "participants": participant_ids,
                "stations": station_numbers
            }
            
            # Create competition session
            response = admin_session.post(
                f"{BASE_URL}/admin/create-competition-session",
                json=session_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.competition_session_id = result.get("session_id")
                    self.log(f"✓ Competition session created with ID: {self.competition_session_id}")
                    # Store admin session for later use
                    self.session = admin_session
                    return True
            
            self.log(f"✗ Failed to create competition session: {response.text}", "ERROR")
            return False
        except Exception as e:
            self.log(f"✗ Error creating competition session: {e}", "ERROR")
            return False

    def student_login_and_join(self, student_data):
        """Login as student and join competition"""
        self.log(f"Student {student_data['name']} joining competition...")
        try:
            # Create new session for this student
            student_session = requests.Session()
            
            # Login as student
            login_data = {
                "login_type": "student",
                "student_code": student_data["code"],
                "student_name": student_data["name"]
            }
            
            response = student_session.post(f"{BASE_URL}/login", data=login_data)
            if response.status_code not in [200, 302]:
                self.log(f"✗ Student {student_data['name']} login failed", "ERROR")
                return False
            
            # Check available competitions
            response = student_session.get(f"{BASE_URL}/student/available-competitions")
            if response.status_code != 200:
                self.log(f"✗ Could not get competitions for {student_data['name']}", "ERROR")
                return False
            
            competitions = response.json().get("competitions", [])
            if not competitions:
                self.log(f"✗ No competitions available for {student_data['name']}", "ERROR")
                return False
            
            # Join the competition
            response = student_session.post(f"{BASE_URL}/student/join-competition/{self.competition_session_id}")
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.log(f"✓ {student_data['name']} joined competition successfully")
                    self.student_sessions[student_data['code']] = student_session
                    return True
            
            self.log(f"✗ {student_data['name']} failed to join competition", "ERROR")
            return False
        except Exception as e:
            self.log(f"✗ Error with student {student_data['name']}: {e}", "ERROR")
            return False

    def start_competition(self):
        """Start the competition (admin action)"""
        self.log("Starting competition...")
        try:
            response = self.session.post(f"{BASE_URL}/admin/competition-sessions/{self.competition_session_id}/start")
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.log("✓ Competition started successfully")
                    return True
            
            self.log(f"✗ Failed to start competition: {response.text}", "ERROR")
            return False
        except Exception as e:
            self.log(f"✗ Error starting competition: {e}", "ERROR")
            return False

    def simulate_student_session(self, student_code, student_name):
        """Simulate a student going through a competition station"""
        self.log(f"Simulating session for {student_name}...")
        try:
            student_session = self.student_sessions.get(student_code)
            if not student_session:
                self.log(f"✗ No session found for {student_name}", "ERROR")
                return False

            # Wait for competition to start
            time.sleep(2)
            
            # Get competition status
            response = student_session.get(f"{BASE_URL}/student/competition/{self.competition_session_id}/status")
            if response.status_code != 200:
                self.log(f"✗ Could not get status for {student_name}", "ERROR")
                return False
            
            status = response.json()
            self.log(f"Student {student_name} status: {status.get('student_status', 'unknown')}")
            
            # Start station if available
            if status.get('student_status') == 'active':
                response = student_session.post(f"{BASE_URL}/student/competition/{self.competition_session_id}/start-station")
                if response.status_code == 200:
                    self.log(f"✓ {student_name} started station")
                    
                    # Simulate conversation
                    self.simulate_conversation(student_session, student_name)
                    
                    # Complete station
                    response = student_session.post(f"{BASE_URL}/student/competition/complete-station")
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success'):
                            score = result.get('evaluation', {}).get('percentage', 0)
                            self.log(f"✓ {student_name} completed station with score: {score}%")
                            return True
            
            return False
        except Exception as e:
            self.log(f"✗ Error in student session for {student_name}: {e}", "ERROR")
            return False

    def simulate_conversation(self, student_session, student_name):
        """Simulate a conversation between student and patient"""
        self.log(f"Simulating conversation for {student_name}...")
        
        # Sample questions/responses
        questions = [
            "Bonjour, pouvez-vous me décrire votre douleur?",
            "Depuis quand avez-vous cette douleur?",
            "Avez-vous des antécédents cardiaques?",
            "Prenez-vous des médicaments?",
            "Je vais maintenant écouter votre cœur."
        ]
        
        try:
            for question in questions:
                response = student_session.post(
                    f"{BASE_URL}/chat",
                    json={"message": question},
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    result = response.json()
                    self.log(f"  Q: {question[:50]}...")
                    self.log(f"  A: {result.get('reply', 'No response')[:50]}...")
                else:
                    self.log(f"  Failed to send message: {question[:30]}...", "WARNING")
                
                time.sleep(1)  # Small delay between messages
                
        except Exception as e:
            self.log(f"✗ Error in conversation simulation: {e}", "ERROR")

    def get_final_results(self):
        """Get final competition results"""
        self.log("Getting final competition results...")
        try:
            response = self.session.get(f"{BASE_URL}/admin/competition-sessions/{self.competition_session_id}")
            if response.status_code == 200:
                result = response.json()
                leaderboard = result.get('leaderboard', [])
                
                self.log("=== FINAL COMPETITION RESULTS ===")
                if leaderboard:
                    for entry in leaderboard:
                        self.log(f"  {entry.get('rank', '?')}. {entry.get('student_name', 'Unknown')} - {entry.get('average_score', 0)}%")
                else:
                    self.log("  No results available yet")
                self.log("=================================")
                return True
        except Exception as e:
            self.log(f"✗ Error getting final results: {e}", "ERROR")
            return False

    def cleanup(self):
        """Clean up test data"""
        self.log("Cleaning up test data...")
        try:
            # Delete test case if created
            if self.created_case:
                response = self.session.delete(f"{BASE_URL}/teacher/delete_case/{self.created_case}")
                if response.status_code == 200:
                    self.log(f"✓ Deleted test case {self.created_case}")
                else:
                    self.log(f"✗ Failed to delete test case", "WARNING")
            
            # Competition sessions and students are typically kept for analysis
            self.log("✓ Cleanup completed")
        except Exception as e:
            self.log(f"✗ Error during cleanup: {e}", "WARNING")

    def run_full_test(self):
        """Run the complete test suite"""
        self.log("Starting ECOS Competition Session Full Test")
        self.log("=" * 50)
        
        # Test sequence
        test_steps = [
            ("Connection Test", self.test_connection),
            ("Admin Login", self.admin_login),
            ("Create Test Case", self.create_test_case),
            ("Create Test Students", self.create_test_students),
            ("Create Competition Session", self.create_competition_session),
        ]
        
        # Execute setup steps
        for step_name, step_func in test_steps:
            self.log(f"\n--- {step_name} ---")
            if not step_func():
                self.log(f"✗ Test failed at step: {step_name}", "ERROR")
                return False
        
        # Student operations
        self.log("\n--- Student Operations ---")
        for student in self.created_students:
            if not self.student_login_and_join(student):
                self.log(f"✗ Failed student operations for {student['name']}", "ERROR")
                return False
        
        # Start competition
        self.log("\n--- Starting Competition ---")
        if not self.start_competition():
            return False
        
        # Wait a moment for competition to initialize
        time.sleep(3)
        
        # Simulate student sessions
        self.log("\n--- Student Sessions ---")
        for student in self.created_students:
            self.simulate_student_session(student["code"], student["name"])
            time.sleep(2)  # Delay between students
        
        # Wait for all sessions to complete
        time.sleep(5)
        
        # Get final results
        self.log("\n--- Final Results ---")
        self.get_final_results()
        
        # Cleanup
        self.log("\n--- Cleanup ---")
        self.cleanup()
        
        self.log("\n" + "=" * 50)
        self.log("✓ COMPETITION TEST COMPLETED SUCCESSFULLY!")
        return True

def main():
    """Main test function"""
    tester = CompetitionTester()
    
    try:
        success = tester.run_full_test()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        tester.cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        tester.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()