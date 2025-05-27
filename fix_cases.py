import os
import json
import re

def fix_existing_cases():
    patient_data_folder = 'patient_data'
    
    for filename in os.listdir(patient_data_folder):
        if filename.startswith("patient_case_") and filename.endswith(".json"):
            file_path = os.path.join(patient_data_folder, filename)
            
            # Extract case number from filename
            match = re.search(r'patient_case_(.+?)\.json', filename)
            if not match:
                continue
                
            case_number = match.group(1)
            
            try:
                # Load the case data
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Fix the case number and specialty
                data['case_number'] = case_number
                
                # Ask for the specialty for this case
                if not data.get('specialty') or data.get('specialty') == "None" or data.get('specialty') == "Non spécifié":
                    specialty = input(f"Enter specialty for case {case_number} (or press Enter for 'Non spécifié'): ")
                    data['specialty'] = specialty if specialty.strip() else "Non spécifié"
                
                # Save the fixed data
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
                print(f"Fixed case {case_number}")
                
            except Exception as e:
                print(f"Error fixing case {case_number}: {str(e)}")

if __name__ == "__main__":
    fix_existing_cases()