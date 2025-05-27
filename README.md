# OSCE Chat Simulator

An AI-powered medical training application that simulates OSCE (Objective Structured Clinical Examination) consultations using chatbot technology to replace human standardized patients.

## Overview

The OSCE Chat Simulator enables medical students to practice clinical consultations with AI-simulated patients. Teachers can upload medical case files or create cases manually, while students interact with AI patients powered by fine-tuned Llama 3 models via Groq API. The system provides automated evaluation and generates comprehensive PDF reports.

## Features

### For Teachers
- **Case Creation**: Upload medical case files (PDF, Word) or enter cases manually
- **Automatic Extraction**: AI-powered extraction of patient information, symptoms, and evaluation criteria
- **Image Support**: Upload and manage medical images (radiographs, scans)
- **Evaluation Setup**: Create custom evaluation checklists with point-based scoring
- **Directives Management**: Set specific instructions and timing for OSCE stations
- **Case Management**: View, edit, and delete existing cases

### For Students
- **Case Selection**: Browse available cases by specialty
- **Real-time Chat**: Interactive conversations with AI-simulated patients
- **Directives Display**: Access station instructions and timing requirements
- **Timer Integration**: Built-in consultation timer with visual alerts
- **Image Viewing**: View medical images with zoom and navigation features
- **Automated Evaluation**: Receive immediate performance feedback

### System Features
- **AI-Powered Evaluation**: Intelligent assessment of consultation performance
- **PDF Reports**: Comprehensive consultation reports with transcripts and scores
- **Multi-language Support**: French interface with medical terminology
- **Responsive Design**: Works on desktop and mobile devices
- **Session Management**: Secure handling of consultation sessions

## Technology Stack

### Backend
- **Framework**: Flask (Python)
- **AI/LLM**: LangChain with Groq API (Llama 4)
- **Document Processing**: PyPDF2, python-docx, docx2txt
- **PDF Generation**: ReportLab
- **Image Processing**: Pillow (PIL)

### Frontend
- **HTML/CSS/JavaScript**: Vanilla JavaScript with modern CSS
- **UI Components**: Custom modal dialogs and responsive layouts
- **Real-time Features**: Fetch API for asynchronous communication

### Storage
- **Case Data**: JSON files for case storage
- **Images**: File system storage with web-accessible paths
- **Sessions**: Flask session management

## Installation

### Prerequisites
- Python 3.8+
- Groq API key

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/your-username/osce-chat-simulator.git
cd osce-chat-simulator
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_api_key_here
```

4. **Create required directories**
```bash
mkdir -p uploads patient_data static/images/cases
```

5. **Run the application**
```bash
python app.py
```

6. **Access the application**
Open your browser and navigate to `http://localhost:5000`

## Usage

### Getting Started

1. **Choose Your Role**
   - Navigate to the homepage
   - Select "Teacher" to create and manage cases
   - Select "Student" to practice consultations

### For Teachers

1. **Create a New Case**
   - Choose between file upload or manual entry
   - For file upload: Upload PDF/Word documents with case details
   - For manual entry: Fill in patient information, symptoms, and evaluation criteria

2. **Set Up Directives**
   - Specify consultation timing (e.g., "3 minutes for history taking")
   - Define specific tasks (e.g., "Interpret radiograph at minute 6")
   - Set diagnostic expectations

3. **Configure Evaluation**
   - Create checklist items with point values
   - Organize items by categories (History, Physical Exam, Communication, etc.)
   - Set total consultation time

4. **Add Medical Images**
   - Upload radiographs, CT scans, or other medical images
   - Provide descriptions for each image
   - Images will be available to students during consultations

### For Students

1. **Select a Case**
   - Browse available cases by specialty
   - Filter by case number or specialty
   - Review case information before starting

2. **Start Consultation**
   - Click "Start Consultation" to begin
   - View directives to understand requirements
   - Monitor the timer for time management

3. **Conduct the Consultation**
   - Ask questions as you would with a real patient
   - Request to see medical images when appropriate
   - Follow the directives for structured examination

4. **Receive Evaluation**
   - End the consultation when complete
   - Review detailed performance feedback
   - Download PDF report for your records

## File Structure

```
osce-chat-simulator/
├── app.py                     # Main Flask application
├── document_processor.py     # Document extraction agent
├── evaluation_agent.py       # Evaluation processing
├── simple_pdf_generator.py   # PDF report generation
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (create this)
├── templates/
│   ├── home.html             # Landing page
│   ├── teacher.html          # Teacher interface
│   └── student.html          # Student interface
├── static/
│   ├── css/
│   │   └── styles.css        # Application styles
│   ├── js/
│   │   ├── teacher.js        # Teacher interface logic
│   │   └── student.js        # Student interface logic
│   └── images/
│       └── cases/            # Uploaded medical images
├── patient_data/             # JSON files for case storage
├── uploads/                  # Temporary file uploads
└── README.md                 # This file
```

## API Endpoints

### Case Management
- `POST /process_case_file` - Process uploaded case file
- `POST /process_manual_case` - Create case from manual entry
- `GET /get_case/<case_number>` - Retrieve case details
- `DELETE /delete_case/<case_number>` - Delete a case

### Chat System
- `POST /initialize_chat` - Start new consultation session
- `POST /chat` - Send message in consultation
- `POST /end_chat` - End consultation and generate evaluation

### File Handling
- `GET /download_pdf/<filename>` - Download generated PDF reports

## Configuration

### Environment Variables
- `GROQ_API_KEY`: Your Groq API key for LLM access
- `FLASK_ENV`: Set to 'development' for debug mode
- `FLASK_SECRET_KEY`: Custom secret key for sessions (optional)

### Customization
- **Consultation Time**: Default 10 minutes, configurable per case
- **Evaluation Criteria**: Fully customizable checklists
- **UI Language**: Currently French, can be localized
- **AI Model**: Uses Llama 4, can be changed in app.py

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For questions, issues, or feature requests:
- Create an issue on GitHub
- Contact the development team
- Check the documentation wiki

## Acknowledgments

- Groq for providing fast LLM inference
- LangChain for LLM integration framework
- Medical education community for requirements and feedback
- Open source contributors



---

**Note**: This application is designed for educational purposes in medical training. It should supplement, not replace, traditional clinical training methods.