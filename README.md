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
- **AI/LLM**: LangChain with Groq API (Llama4)
- **Document Processing**: PyPDF2, python-docx, docx2txt
- **PDF Generation**: ReportLab
- **Image Processing**: Pillow (PIL)
- **Database**: SQLAlchemy with SQLite

### Frontend
- **HTML/CSS/JavaScript**: Vanilla JavaScript with modern CSS
- **UI Components**: Custom modal dialogs and responsive layouts
- **Real-time Features**: Fetch API for asynchronous communication

### Storage
- **Case Data**: SQLite database for case storage
- **Images**: File system storage with web-accessible paths
- **Sessions**: Flask session management

## Installation

### Prerequisites
- Python 3.8+
- Groq API key

### Organisation

osce-chat-simulator/
├── app.py                     # Main Flask application
├── auth.py                    # Authentication logic
├── document_processor.py      # Document extraction agent
├── evaluation_agent.py        # Evaluation processing
├── simple_pdf_generator.py    # PDF report generation
├── init_db.py                 # Database initialization script
├── models.py                  # SQLAlchemy models
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (create this)
├── blueprints/
│   ├── admin.py               # Admin routes
│   ├── student.py             # Student routes
│   └── teacher.py             # Teacher routes
├── templates/
│   ├── home.html              # Landing page
│   ├── login.html             # Login page
│   ├── admin.html             # Admin interface
│   ├── teacher.html           # Teacher interface
│   └── student.html           # Student interface
├── static/
│   ├── css/
│   │   └── styles.css         # Application styles
│   ├── js/
│   │   ├── admin.js           # Admin interface logic
│   │   ├── teacher.js         # Teacher interface logic
│   │   └── student.js         # Student interface logic
│   └── images/
│       └── cases/             # Uploaded medical images
├── uploads/                   # Temporary file uploads
└── README.md        
└──instance/
   └──osce_simulator.db          # This file

These changes should address all the issues you've raised and provide a more robust and maintainable structure for your ECOS project. Let me know if you have any other questions!

 Sources





