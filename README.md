# 🎯 Personal AI Job Search Agent

A fast, strict, and automated job hunting pipeline designed specifically for **immediate joiners and active job seekers in India and globally**.

Instead of manually browsing hundreds of outdated or irrelevant aggregator listings, this agent continuously polls multiple live APIs & search engines, enforces a **strict freshness filter (<24h–48h)**, eliminates spam/staffing mills, deduplicates postings across platforms, scores matches against your resume & target profile (0–100%), and delivers actionable HTML reports and a **unified Excel spreadsheet** with direct application links.

---

## ⚡ Key Highlights

- **Multi-Source Polling & India Tech-Hub Engine:**
  - **LinkedIn (Direct Guest API with Multi-City Pagination):** Scans top Indian tech hubs (**Bengaluru, Hyderabad, Pune, Mumbai, Gurgaon, Delhi NCR, Kolkata, Chennai, and Remote India**) with multi-page pagination (`start=0, 25, 50`) for fresh openings (<48h) with direct apply URLs.
  - **JobSpy Adapter (Google Jobs, Indeed India, Glassdoor, LinkedIn):** Broad scraper integration with localized country parameters (`country_indeed="India"`).
  - **Arbeitnow API:** Real-time jobs from corporate ATS systems (**Greenhouse**, **Lever**, **Ashby**, **Workday**) with post-search location filtering.
  - **Jobicy API:** Free live remote tech feed with direct employer links (Canonical, Pinterest, Zuora, Roboflow, StackAdapt, etc.).
  - **Remotive & RemoteOK:** Curated remote analytics, data, and engineering listings.
  - **Himalayas API:** Global remote startup opportunities.
  - **Adzuna API:** Free key with coverage across India (`api.adzuna.com/v1/api/jobs/in/search/1`) and 16+ countries.
- **Unified Clean Excel Workbook (`latest_job_matches.xlsx` & `.csv`):**
  - **Sheet 1 (`📋 All Jobs & Matches`):** Compiles **every single discovered job from all sources** into one master sheet sorted by match score.
  - **Sheet 2 (`🎯 Top Matches (70%+)`):** Filtered view of high-priority applications scored $\ge 70\%$.
  - **Direct Clickable Apply URLs** in every row.
  - Built-in **Application Status Tracker** column (`To Apply`, `Applied`, `Interviewing`, `Rejected`).
  - Overwrites cleanly each run to prevent folder clutter.
- **Strict Location & Country Filtering:** Eliminates US/EU-restricted postings when targeting India, while keeping India-eligible and global remote postings.
- **Strict Freshness Filter:** Drops stale jobs older than your time threshold (48h default for weekend/fresh capture, configurable down to 6h/24h).
- **Multi-Signal Deduplication:** Cross-source hashing on normalized title + company + location, token sorting, and fuzzy similarity matching.
- **Resume & Profile Scoring Engine (0–100%):**
  - Title & Role Alignment (25%)
  - Skills Match & Keyword Overlap (20%) — SQL, Power BI, Python, Tableau, Excel, Alteryx, DAX, Risk/Fraud Analytics, etc.
  - Experience & Responsibility (20%)
  - Seniority Fit (10%)
  - Industry & Domain Match (10%)
  - Location & Work Mode Fit (5%)
  - Education & Certifications (5%)
  - Other Requirements (5%)
- **Action Priority Categorization:**
  - 🔴 **Apply Immediately** (Score ≥90% & Age <6h)
  - 🟠 **Apply Today** (Score 80–89% or Age 6–12h)
  - 🟡 **Consider** (Score 70–79%)
- **Automatic Gap Analysis:** Pinpoints missing skills per job so you can tailor your resume before applying.
- **Responsive HTML Reports:** Modern glassmorphism report ([`reports/latest_report.html`](reports/latest_report.html)) with one-click direct apply links.

---

## 📁 Directory Structure

```
job-search-agent/
├── config/
│   ├── profile.yaml        # Your target roles, skills, experience, locations
│   └── settings.yaml       # Freshness hours, match thresholds, source toggles, SMTP
├── data/
│   └── jobs.db             # SQLite database tracking seen jobs & match history
├── reports/                # Clean single-file outputs: latest_job_matches.xlsx, .csv, .html
├── resume/                 # Place your PDF / DOCX / TXT resume here (optional)
├── src/
│   ├── sources/            # Source adapters (LinkedIn, JobSpy, Arbeitnow, Jobicy, Remotive, RemoteOK, Himalayas, Adzuna)
│   ├── config.py           # Configuration loader & validation
│   ├── db.py               # SQLite storage layer
│   ├── dedup.py            # Multi-signal deduplication
│   ├── excel_exporter.py   # Multi-sheet styled Excel & CSV exporter
│   ├── fraud_filter.py     # Spam / agency / low-quality filtering
│   ├── freshness.py        # Timestamp evaluator & age formatter
│   ├── models.py           # Typed Pydantic/dataclass data structures
│   ├── notifier.py         # SMTP email dispatcher
│   ├── report.py           # Jinja2 HTML report & console visualizer
│   ├── resume_parser.py    # Resume text & skill extractor
│   ├── scorer.py           # 0–100 matching engine
│   └── main.py             # Pipeline orchestrator
├── templates/
│   └── report.html         # Modern glassmorphism email/web template
├── export_excel.py         # Standalone database to Excel exporter
├── requirements.txt        # Python dependencies
└── run_search.py           # Entry-point CLI runner
```

---

## 🚀 Quick Start

### 1. Install Dependencies

Ensure Python 3.9+ is installed:

```bash
pip install -r requirements.txt
```

### 2. Configure Your Candidate Profile

Edit `config/profile.yaml` with your target roles, years of experience, primary/secondary skills, and preferred locations:

```yaml
candidate:
  name: "Avik Chatterjee"
  current_role: "Data & Risk Analyst"
  total_experience_years: 5
  target_roles:
    - "Data Analyst"
    - "Senior Data Analyst"
    - "Data & Risk Analyst"
    - "Risk Analyst"
    - "Fraud Analyst"
    - "Product Data Analyst"
    - "Business Intelligence Analyst"
    - "BI Analyst"
    - "Analytics Engineer"
  primary_skills:
    - SQL
    - Python
    - Power BI
    - Tableau
    - Excel
    - Alteryx
    - DAX
  preferred_countries:
    - India
  preferred_cities:
    - Bengaluru
    - Hyderabad
    - Pune
    - Mumbai
    - Gurgaon
    - Kolkata
    - Remote
  work_preference: "any" # remote / hybrid / onsite / any
```

### 3. Run the Search Pipeline

**Standard Run (Searches all sources, updates SQLite DB, Excel & HTML):**
```bash
python run_search.py
```

**Dry Run (Test search without saving to DB or sending email):**
```bash
python run_search.py --dry-run
```

**Custom Time Window & Match Threshold:**
```bash
python run_search.py --max-age 48 --min-score 70
```

**Export Database Jobs to Excel Anytime:**
```bash
python export_excel.py
```

---

## 📊 Excel Spreadsheet Features (`.xlsx` & `.csv`)

Every run automatically updates the files in `reports/`:
- **`latest_job_matches.xlsx`** (Styled workbook with conditional formatting & auto-fit columns)
- **`latest_job_matches.csv`** (UTF-8 BOM formatted for instant CSV opening)
- **`latest_report.html`** (Glassmorphism web & email report)

### Workbook Structure:
1. **Sheet 1: `📋 All Jobs & Matches`**
   - **Direct Clickable Apply URL** in Column E
   - **Match Score (%)** with color-coded badges (🟢 80–90%+, 🟡 70–79%)
   - **Priority** (🔴 Apply Immediately, 🟠 Apply Today, 🟡 Consider)
   - **Source** tag (LinkedIn, JobSpy, Arbeitnow, Jobicy, RemoteOK, Himalayas, Remotive, Adzuna)
   - Job Title, Company, Location, Work Mode, Salary, Age
   - Matched Skills, Missing Skill Gaps, and Match Reasons
   - Built-in **Application Status Tracker** column (`To Apply`, `Applied`, `Interviewing`, `Rejected`)
2. **Sheet 2: `🎯 Top Matches (70%+)`**
   - High-priority matching roles scored $\ge 70\%$ for focused daily applications.

---

## ⏰ Automated Scheduling

### Option A: Windows Task Scheduler (Powershell)
Run every 4 hours:
```powershell
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\path\to\job-search-agent\run_search.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM -RepetitionInterval (New-TimeSpan -Hours 4)
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "JobSearchAgent"
```

### Option B: Linux / macOS Cron
Run every 4 hours during weekdays:
```bash
0 */4 * * 1-5 cd /path/to/job-search-agent && /path/to/venv/bin/python run_search.py >> run.log 2>&1
```

---

## 📄 License
MIT. Free for personal job-hunting and customization.
