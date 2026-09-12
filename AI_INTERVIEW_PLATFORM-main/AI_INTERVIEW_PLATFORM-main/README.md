# 🤖 AI Interview Studio & Assessment Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-Flash%20Lite%20AI-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Database](https://img.shields.io/badge/Database-MySQL%20%7C%20PostgreSQL%20%7C%20SQLite-00758F?style=for-the-badge&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Deployment](https://img.shields.io/badge/Deployment-Render%20Cloud-46E3B7?style=for-the-badge&logo=render&logoColor=black)](https://render.com/)

> **An enterprise-grade, full-stack AI-powered mock interview platform** that simulates realistic, unscripted hiring evaluations — powered by **Google Gemini AI**, built on **Flask & SQLAlchemy**, with adaptive assessments, voice dictation, Monaco code sandbox, automated anti-cheat proctoring, and printable PDF scorecards.

> **Designed for:** University students, aspiring engineers, and job seekers who want to master technical, behavioral, and domain-specific interviews through intelligent, real-time AI simulations — completely free.

---

## 💡 Why This Platform Was Built

The technical interview process is one of the most anxiety-inducing and poorly-prepared-for stages in a student's academic and professional journey. Most students realize too late that:

- **Mock interviews are expensive** — professional platforms charge monthly subscriptions, and human mentors are hard to access.
- **Generic question banks go stale** — static PDFs and YouTube videos don't simulate the real pressure of live questioning.
- **There is no personalization** — every student gets the same questions regardless of their resume, domain, or semester level.
- **Language barriers exist** — many students struggle to articulate technically correct ideas in English under time pressure.
- **Practice environments are disconnected** — code editors, voice practice, and company-specific prep live in different tools.

**This platform was built to solve all of that in one place** — a single, free, open-source solution where a student can upload their resume, select a domain, and get interrogated by an AI examiner that adapts dynamically to their answers, flags behavioral violations, and delivers an honest, structured performance report — just like a real recruiter would.

The platform was designed with the needs of **tier-2 and tier-3 engineering college students in India** specifically in mind, where access to quality placement training infrastructure is limited but the aspirations are not.

---

## 🎯 Key Capabilities & Highlights

* 🧠 **Adaptive AI Examiner**: Evaluates technical depth, analytical reasoning, and communication clarity in real-time, dynamically adjusting questions based on candidate performance.
* 🛡️ **Automated Security Proctoring**: Real-time window focus tracking, tab-switch breach detection, two-strike disciplinary warning modals, and automatic session disqualification for code of conduct breaches.
* 🎓 **Multi-Track Practice Hub**:
  * **Academic Viva Voce**: Oral university exam simulations testing definitions, theoretical rigor, and algorithms.
  * **FluentFlow Language Practice**: Conversational multilingual practice with instant grammatical corrections and translations.
  * **Concept Drills**: Rapid-fire architectural and scenario reasoning challenges.
* 🏢 **Company-Specific Prep Hub**: Curated, categorized resource links for 11 top companies — Google, Microsoft, Amazon, Meta, Netflix, TCS, Infosys, Wipro, Accenture, Cognizant, and Capgemini — covering LeetCode, GeeksForGeeks, PrepInsta, and InterviewBit.
* 🎙️ **Hands-Free Voice Dictation**: Integrated client-side Web Speech API (`webkitSpeechRecognition`) with animated neural waveform visualizers.
* 💻 **Monaco Code Editor**: Built-in VS Code-style Python 3 programming sandbox for coding challenges.
* 📄 **Resume-Driven Questioning**: Automatic PDF/DOCX resume text extraction embedded into the candidate's interview context for hyper-personalized questioning.
* 📊 **Instant Competency Scorecards**: High-contrast score gauge rings, competency matrix breakdowns, qualitative executive summaries, and single-click printable PDF report generation.
* 🔐 **Triple-Redundant OTP Delivery**: Resend HTTP API, SendGrid HTTP API, and SMTP failover routing for ultra-reliable email authentication.
* ⚙️ **Executive Operations Dashboard**: Administrative candidate management, live assessment monitoring, candidate resume viewers, per-user attempt unlock, and real-time pass-score threshold configuration.
* 🔑 **Three Authentication Pathways**: Classic password login, Google OAuth 2.0 Single Sign-On, and passwordless OTP login — all under one unified session layer.

---

## 🗺️ App Flow — Step-by-Step User Journey

This section walks through the **complete experience** of a candidate from first visit to final scorecard.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE CANDIDATE JOURNEY                           │
└─────────────────────────────────────────────────────────────────────────────┘

STEP 1 ─ LANDING & DISCOVERY
  └─► Candidate visits the platform landing page (/)
      ├── Reviews platform capabilities, features, and testimonials
      └── Clicks "Get Started" → routed to registration / login

STEP 2 ─ ACCOUNT CREATION & IDENTITY VERIFICATION
  └─► Three pathways available:
      ├── [A] Classic Registration (/register)
      │     ├── Fills in full name, email, password, education, course, semester
      │     └── PBKDF2-SHA256 hashed password stored securely
      ├── [B] Google OAuth (/auth/google)
      │     └── One-click sign-in via Google OpenID Connect, auto-profile sync
      └── [C] OTP Passwordless (/auth/otp/send → /auth/otp/verify)
            ├── Email entered → OTP dispatched via Resend → SendGrid → SMTP
            └── 6-digit code verified, session initialized

STEP 3 ─ CANDIDATE WORKSPACE DASHBOARD (/dashboard)
  └─► Personalized workspace loads:
      ├── Profile card: name, education, course, semester
      ├── Resume upload zone (PDF/DOCX, max 5 MB) → auto text extraction
      ├── Latest interview result summary with score gauge ring
      ├── Interview history progress chart (Chart.js trend line)
      ├── Quick-launch cards: Assessment, Practice, Tech Prep, History
      └── Edit profile (/edit-profile): update name, education, course, semester

STEP 4A ─ LIVE ASSESSMENT INTERVIEW (/interview)
  └─► Domain selection screen → Pick from:
      │   Web Dev, Python, Java, DSA, DBMS, OS, CN, AI/ML,
      │   System Design, Cybersecurity, Cloud, DevOps, and more
      ├── Resume context auto-injected into Gemini's system prompt
      ├── Anti-cheat proctoring activates immediately on page load
      │
      ├── QUESTION LOOP:
      │     ├── Gemini streams the first question (domain + resume aware)
      │     ├── Candidate types OR uses voice dictation (waveform animates)
      │     ├── Code questions → Monaco Editor sandbox appears
      │     ├── Answer submitted → Gemini evaluates and generates next question
      │     └── Adaptive depth: deeper follow-ups if answers are strong
      │
      ├── PROCTORING LAYER (parallel):
      │     ├── Page visibility & window focus monitored via JS events
      │     ├── Strike 1: Tab switched → Full-screen red warning modal fires
      │     └── Strike 2: Another violation → Session auto-terminated & flagged
      │
      └── COMPLETION (after min. questions reached):
            └── Candidate clicks "Finish" → /finish-interview

STEP 4B ─ PRACTICE HUB (/practice-setup)
  └─► Select one of three modes:
      ├── 🎓 Viva Voce: Enter any academic subject → AI conducts oral Q&A
      ├── 💬 FluentFlow Language Practice:
      │     ├── Choose target language (English, Hindi, French, etc.)
      │     ├── Set focus: conversation / grammar / vocabulary / pronunciation
      │     └── Set level: beginner / intermediate / advanced
      └── ⚡ Concept Drills: Enter a topic → rapid-fire scenario challenges
      (Practice sessions are NOT scored or saved to history)

STEP 4C ─ COMPANY PREP HUB (/tech-questions)
  └─► Browse 11 companies (Google, Microsoft, Amazon, Meta, Netflix,
      TCS, Infosys, Wipro, Accenture, Cognizant, Capgemini)
      └── Each company card → curated resource links:
            LeetCode tagged problems, GeeksForGeeks guides,
            PrepInsta placement papers, InterviewBit mock Q&A

STEP 5 ─ AI EVALUATION PIPELINE (/finish-interview)
  └─► Full chat transcript submitted to Gemini evaluation prompt
      ├── Scores 10-point scale: Technical Accuracy, Communication,
      │     Depth of Knowledge, Problem Solving, Confidence
      ├── Generates qualitative executive summary paragraph
      ├── Determines PASS / FAIL against admin-configured cutoff
      └── Result stored in DB → redirects to scorecard

STEP 6 ─ SCORECARD & REPORT (/interview-result)
  └─► High-contrast result card renders:
      ├── Score gauge ring with PASS / FAIL / TERMINATED badge
      ├── Competency breakdown table (5 dimensions)
      ├── AI-written qualitative executive summary
      ├── "Print / Save PDF" button → browser print-to-PDF
      └── Navigation back to Dashboard or History

STEP 7 ─ HISTORY & PROGRESSION (/my-history)
  └─► Full attempt log table: date, domain, score, status
      ├── Click any row → detailed scorecard for that attempt
      └── Trend analysis via Chart.js score progression graph
```

---

## 🔄 End-to-End Platform Architecture

```mermaid
flowchart TD
    User([Candidate / Job Seeker]) --> AuthLayer{Authentication Gateway}
    
    AuthLayer -->|Local Account| LocalLogin[PBKDF2 Password Auth]
    AuthLayer -->|Social Login| GoogleOAuth[Google OAuth 2.0]
    AuthLayer -->|Passwordless| OTPAuth[Multi-Provider OTP Dispatcher]
    
    LocalLogin --> Dashboard[Candidate Workspace Dashboard]
    GoogleOAuth --> Dashboard
    OTPAuth --> Dashboard
    
    Dashboard --> ResumeUpload[Resume Indexing & Text Extraction]
    Dashboard --> TrackSelection[Mode Selection: Assessment vs Practice vs Prep Hub]
    
    TrackSelection --> InterviewEngine[Live Assessment Studio Engine]
    TrackSelection --> PracticeHub[Practice Hub: Viva / Language / Drills]
    TrackSelection --> CompanyPrep[Company Prep Hub: 11 Companies]
    ResumeUpload -.->|Embedded Context| InterviewEngine
    
    InterviewEngine --> Proctor[Active Anti-Cheat Proctoring Monitor]
    InterviewEngine --> VoiceInput[Web Speech Voice Transcription]
    InterviewEngine --> Monaco[Monaco Code Editor Sandbox]
    InterviewEngine --> GeminiEngine[Google Gemini Flash AI Engine]
    
    GeminiEngine -->|Streaming Q&A| InterviewEngine
    Proctor -->|2nd Strike Breach| Terminate[Disqualification & Termination]
    
    InterviewEngine -->|Completion| ResultGen[Rapid AI Evaluation Pipeline]
    ResultGen --> Scorecard[Performance Evaluation Report & PDF]
    Scorecard --> History[Candidate Attempt Progression & History]
    
    Scorecard -.-> DB[(Relational Database: MySQL / PostgreSQL / SQLite)]
    History -.-> DB
    
    AdminUser([Recruiter / Administrator]) --> AdminPanel[Admin Operations Control Center]
    AdminPanel --> DB
    AdminPanel --> ConfigMgmt[Global Settings & Cutoff Configuration]
    AdminPanel --> UserMgmt[User Management & Attempt Unlock]
```

---

## 🏢 Company Prep Hub — Supported Companies

The platform includes a curated preparation hub for **11 major tech companies**, each with 4 structured resource links:

| # | Company | Focus Areas |
|---|---|---|
| 1 | **Google** | DSA, Algorithms, System Design, Behavioral |
| 2 | **Microsoft** | OOP, OS, Networking, SDE/SDET roles |
| 3 | **Amazon** | Leadership Principles, System Design, SDE |
| 4 | **Meta (Facebook)** | Graphs, DP, System Design at Scale |
| 5 | **Netflix** | Distributed Systems, Microservices, Culture Fit |
| 6 | **TCS** | NQT Aptitude, Verbal, Logical, Coding |
| 7 | **Infosys** | InfyTQ, Aptitude, Verbal, Technical Rounds |
| 8 | **Wipro** | NLTH Aptitude, Written Communication, Coding |
| 9 | **Accenture** | Cognitive Ability, Verbal, Communication |
| 10 | **Cognizant** | GenC/GenC Next, Aptitude, Coding |
| 11 | **Capgemini** | Pseudocode, Essay Writing, Behavioral |

Each company page aggregates resources from **LeetCode**, **GeeksForGeeks**, **PrepInsta**, and **InterviewBit**.

---

## 🛠️ Technical Stack

| Component | Technology | Description |
|---|---|---|
| **Backend Framework** | Python 3.11+ / Flask 3.0+ | Core application server, routing, and session management |
| **Database ORM** | Flask-SQLAlchemy 3.1+ | Unified relational ORM supporting MySQL, PostgreSQL, and SQLite |
| **AI Assessment Engine** | Google Gemini (`gemini-flash-lite-latest`) | High-speed, context-aware conversational questioning & grading |
| **Authentication & Security** | Werkzeug / Authlib / PyCryptodome | PBKDF2-SHA256 password hashing, Google OAuth 2.0 OpenID Connect |
| **Email Delivery Engine** | Resend API / SendGrid API / SMTP | Multi-provider fallback delivery system for verification codes |
| **Speech Processing** | Web Speech API | Client-side browser-native speech-to-text recognition |
| **Code Editor** | Monaco Editor CDN | Embedded VS Code syntax highlighter and code input |
| **Data Visualization** | Chart.js 4.4+ | Interactive score progression and trend lines |
| **Styling & Theme** | Bootstrap 5.3 + Custom CSS3 | Elite Cyber-Blue high-contrast dark theme with neural aurora backdrop |
| **Production WSGI** | Gunicorn | High-concurrency production HTTP application server |

---

## 🔐 Security & Anti-Cheat System

```
                      PROCTORING LIFECYCLE
                     
  [Active Interview] ────── Tab Switch / Focus Lost ──────► [Strike 1 Recorded]
          ▲                                                         │
          │                        Dismiss Modal                    ▼
          └──────────────────────── (Warning Only) ◄───── [Proctor Warning Modal]
                                                                    │
                                   Second Tab Switch                ▼
                             ─────────────────────────────► [Strike 2 Triggered]
                                                                    │
                                                                    ▼
                                                         [Immediate Disqualification]
                                                                    │
                                                                    ▼
                                                         [Record Flagged in DB]
```

* **Window Focus Detection**: Uses the browser Page Visibility API and `window.onblur` event listeners to monitor candidate window focus.
* **Two-Strike Escalation**: First focus violation triggers a full-screen red warning modal; second violation immediately disqualifies the session.
* **Encrypted Sessions**: Server-signed cryptographic session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` in production).
* **Role-Based Access Control**: Strict multi-tier authentication barriers isolating administrative dashboards, user modification tools, and scoring metrics from standard users.
* **Admin Credential Hardening**: If `ADMIN_PASSWORD` is not set, a cryptographically random 24-character token is auto-generated and printed to the startup log — no predictable default is ever used.

---

## 📊 Database Entity Model

```mermaid
erDiagram
    users ||--o{ interview_results : "completes"
    users ||--o| interview_progress : "tracks active session"

    users {
        int id PK
        varchar full_name
        varchar email UK
        varchar password "Hashed PBKDF2"
        varchar auth_provider "local | google | otp"
        varchar google_id UK
        varchar education
        varchar course
        varchar semester
        text resume_text
        varchar resume_filename
        int extra_allowed_interviews "Admin-granted extra attempts"
        datetime registered_at
    }

    interview_results {
        int id PK
        int user_id FK
        decimal score "Score out of 10"
        varchar status "PASS | FAIL | Terminated | Selected"
        text summary "AI Assessment Summary"
        varchar domain "Interview Domain"
        boolean is_terminated "Anti-cheat flag"
        text termination_reason
        datetime interview_datetime
    }

    interview_progress {
        int id PK
        int user_id FK
        text chat_history "Serialized conversation transcript"
        int q_count "Question progress index"
        datetime updated_at
    }

    admin_settings {
        int id PK
        int min_questions "Default: 5"
        int max_questions "Default: 5"
        int pass_score "Cutoff: 6"
        varchar default_difficulty
    }
```

---

## 🗂️ Project Structure

```
ai_interview_platform/
│
├── app.py                          # Main Flask application (all routes, models, logic)
├── requirements.txt                # Python package dependencies
├── Procfile                        # Gunicorn start command for Render/Heroku
├── render.yaml                     # Render cloud service configuration
├── runtime.txt                     # Python runtime version pin
├── .env                            # Local environment variables (never commit this)
├── .gitignore                      # Git ignore rules
│
├── templates/                      # Jinja2 HTML templates
│   ├── index.html                  # Landing page
│   ├── login.html                  # Login page (password + Google + OTP)
│   ├── signup.html                 # OTP-based signup entry
│   ├── register.html               # Full registration form
│   ├── dashboard.html              # Candidate workspace dashboard
│   ├── interview.html              # Live interview studio
│   ├── interview_result.html       # Score report & competency card
│   ├── practice_setup.html         # Practice mode selector
│   ├── my_history.html             # Attempt history log
│   ├── tech_questions.html         # Company prep hub index
│   ├── company_questions.html      # Per-company resource page
│   ├── admin.html                  # Admin operations dashboard
│   ├── admin_users.html            # User management table
│   ├── admin_user_detail.html      # Individual user profile view
│   ├── admin_interview_detail.html # Individual result deep-dive
│   ├── admin_settings.html         # Platform settings configuration
│   ├── edit_profile.html           # Profile editor
│   ├── forgot_password.html        # Password reset request
│   ├── send_otp.html               # OTP login entry
│   ├── verify_otp.html             # OTP verification
│   └── privacy.html                # Privacy policy
│
├── static/                         # CSS, JS, images, fonts
└── uploads/                        # Candidate resume file storage
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory and configure the required environment variables:

```bash
# -------------------------------------------------------------
# CORE APPLICATION SETTINGS
# -------------------------------------------------------------
SECRET_KEY=your_secure_random_flask_secret_key_here
FLASK_ENV=production

# -------------------------------------------------------------
# DATABASE CONFIGURATION
# (Leave empty or unset to automatically fallback to local SQLite)
# -------------------------------------------------------------
DATABASE_URL=mysql+pymysql://username:password@hostname:3306/database_name

# -------------------------------------------------------------
# GOOGLE GEMINI AI ENGINE
# -------------------------------------------------------------
GEMINI_API_KEY=your_gemini_api_key_here

# -------------------------------------------------------------
# GOOGLE OAUTH 2.0 (Optional - for Google Single Sign-On)
# -------------------------------------------------------------
GOOGLE_CLIENT_ID=your_google_oauth_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret

# -------------------------------------------------------------
# EMAIL DELIVERY & OTP SERVICES (Optional - with SMTP fallback)
# -------------------------------------------------------------
RESEND_API_KEY=your_resend_api_key_here
SENDGRID_API_KEY=your_sendgrid_api_key_here
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_sender_email@gmail.com
MAIL_PASSWORD=your_email_app_password
MAIL_DEFAULT_SENDER=your_sender_email@gmail.com

# -------------------------------------------------------------
# ADMINISTRATOR CREDENTIALS (Auto-initialized on first launch)
# -------------------------------------------------------------
ADMIN_EMAIL=admin@platform.local
ADMIN_PASSWORD=your_custom_admin_password
```

> **Security Note:** Never commit your `.env` file to version control. The `.gitignore` already excludes it. For cloud deployments, set all variables directly in your hosting provider's environment dashboard.

---

## 🚀 Installation & Local Setup

### 1. Clone the Repository
```bash
git clone https://github.com/MR360-TECH/AI_INTERVIEW_PLATFORM.git
cd AI_INTERVIEW_PLATFORM
```

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the environment template and fill in your credentials before running the app.

### 5. Run the Application
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`.

> **First Launch:** The application automatically creates all required database tables and initializes the admin account on startup. No manual migration commands are needed.

---

## 🌐 Production Cloud Deployment (Render)

This repository includes native deployment support for **Render**:

1. Fork or push this repository to your GitHub account.
2. Log in to [Render Dashboard](https://dashboard.render.com/) and click **New + Web Service**.
3. Connect your repository and configure:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Under **Environment Variables**, add `SECRET_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`, and other optional credentials.
5. Deploy the service. The SQL engine will auto-verify database schemas and apply migrations automatically on startup.

> **Persistent Storage on Render:** SQLite data is written to `/var/data/` on Render's persistent disk when available, preventing data loss across deploys.

---

## 🗺️ Roadmap

The platform is under active development. Planned improvements include:

| Status | Feature |
|---|---|
| ✅ Done | Live AI interview with adaptive questioning |
| ✅ Done | Anti-cheat proctoring (2-strike system) |
| ✅ Done | Voice dictation with waveform visualizer |
| ✅ Done | Resume-driven personalized questions |
| ✅ Done | Monaco code editor sandbox |
| ✅ Done | Google OAuth + OTP + Password authentication |
| ✅ Done | Company-specific prep hub (11 companies) |
| ✅ Done | Admin control panel with attempt unlock |
| 🔄 Planned | Webcam-based facial proctoring (optional) |
| 🔄 Planned | Multi-language UI localization |
| 🔄 Planned | Recruiter portal for candidate shortlisting |
| 🔄 Planned | Scheduled interview slots with email reminders |
| 🔄 Planned | Leaderboard and peer performance benchmarking |
| 🔄 Planned | Mobile PWA wrapper |

---

## ❓ Frequently Asked Questions

**Q: Does the platform save my interview chat transcript?**  
A: Only the active in-progress chat history is stored temporarily in the database to support resume/refresh. After the interview is evaluated, only the final score, summary, and metadata are retained — not the raw question-answer chat log.

**Q: Can I retake the interview if I fail?**  
A: By default, one attempt is permitted per user to maintain assessment integrity. Admins can grant additional attempts individually from the admin panel using the "Unlock Attempt" feature.

**Q: What happens if I switch tabs during an interview?**  
A: The proctoring system detects it immediately. The first violation shows a warning modal. The second violation auto-terminates and flags your session as "Terminated" in the database.

**Q: Is an internet connection required for the code editor?**  
A: Yes — the Monaco Editor is loaded from CDN. However, the code editor is purely for input; Python code is not executed on the server — it is submitted as text and evaluated by the AI.

**Q: What databases are supported?**  
A: The platform supports **MySQL**, **PostgreSQL**, and **SQLite** out of the box. If no `DATABASE_URL` is configured, it falls back to a local SQLite file automatically.

**Q: Is a paid API key required to run the platform?**  
A: The Google Gemini API has a generous free tier that covers typical usage. Email delivery via Resend and SendGrid also offer free tiers. The platform is designed to be **fully operational at zero cost** for personal and small-scale use.

---

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "feat: add your feature description"`
4. Push to your branch: `git push origin feature/your-feature-name`
5. Open a Pull Request against the `main` branch

Please make sure your code follows PEP 8 style guidelines and that all new routes are properly secured with session checks.

---

## 📄 License & Attribution

Distributed under the **MIT License**. Developed and maintained by **MR360-TECH**.

---

**Developed by [Gowtham V](https://github.com/MR360-TECH)**
