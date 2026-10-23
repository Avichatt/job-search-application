"""Resume parser — extracts text and skills from PDF/DOCX/TXT resumes."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF file using pdfminer."""
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path)
    except ImportError:
        print("[WARN] pdfminer.six not installed. Cannot parse PDF resume.")
        return ""
    except Exception as e:
        print(f"[WARN] Failed to extract text from PDF: {e}")
        return ""


def extract_text_from_docx(path: str) -> str:
    """Extract text from a DOCX file."""
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        print("[WARN] python-docx not installed. Cannot parse DOCX resume.")
        return ""
    except Exception as e:
        print(f"[WARN] Failed to extract text from DOCX: {e}")
        return ""


def extract_text_from_txt(path: str) -> str:
    """Read plain text resume."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[WARN] Failed to read TXT file: {e}")
        return ""


def load_resume_text(resume_dir: str) -> str:
    """
    Find and extract text from the first resume file in the given directory.
    Supports PDF, DOCX, and TXT formats.
    """
    if not resume_dir or not str(resume_dir).strip():
        return ""

    resume_path = Path(resume_dir)

    if not resume_path.exists():
        print(f"[WARN] Resume directory not found: {resume_dir}")
        return ""

    # If it's a file, parse it directly
    if resume_path.is_file():
        return _extract_from_file(str(resume_path))

    # If it's a directory, find the first resume file
    extensions = [".pdf", ".docx", ".doc", ".txt", ".md"]
    for ext in extensions:
        files = list(resume_path.glob(f"*{ext}"))
        if files:
            print(f"[INFO] Using resume: {files[0].name}")
            return _extract_from_file(str(files[0]))

    print(f"[WARN] No resume file found in {resume_dir}")
    return ""


def _extract_from_file(path: str) -> str:
    """Extract text from a file based on its extension."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(path)
    elif ext in (".txt", ".md"):
        return extract_text_from_txt(path)
    else:
        print(f"[WARN] Unsupported resume format: {ext}")
        return ""


# ── Skill Extraction ───────────────────────────────────────────

# Comprehensive skill/technology dictionary for matching
TECH_SKILLS = {
    # Programming languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl",
    "bash", "shell", "powershell", "sql", "nosql", "haskell", "elixir", "dart",
    "lua", "groovy", "objective-c", "cobol", "fortran",

    # Frontend
    "react", "reactjs", "react.js", "angular", "angularjs", "vue", "vuejs",
    "vue.js", "svelte", "next.js", "nextjs", "nuxt", "nuxtjs", "gatsby",
    "html", "html5", "css", "css3", "sass", "scss", "less", "tailwind",
    "tailwindcss", "bootstrap", "material-ui", "mui", "chakra", "webpack",
    "vite", "rollup", "babel", "jquery",

    # Backend / Frameworks
    "node.js", "nodejs", "express", "express.js", "django", "flask", "fastapi",
    "spring", "spring boot", "springboot", ".net", "asp.net", "rails",
    "ruby on rails", "laravel", "symfony", "gin", "fiber", "actix",
    "nest.js", "nestjs", "koa", "hapi",

    # Data / ML / AI
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn", "pandas",
    "numpy", "scipy", "matplotlib", "seaborn", "plotly", "dbt", "airflow",
    "apache spark", "spark", "hadoop", "kafka", "flink", "beam",
    "machine learning", "deep learning", "nlp", "computer vision",
    "data science", "data engineering", "data analysis", "etl",
    "power bi", "powerbi", "tableau", "looker", "qlik", "metabase",
    "jupyter", "databricks", "snowflake",

    # Databases
    "postgresql", "postgres", "mysql", "mariadb", "oracle", "sql server",
    "mssql", "sqlite", "mongodb", "dynamodb", "cassandra", "redis",
    "elasticsearch", "neo4j", "couchdb", "firestore", "firebase",
    "supabase", "cockroachdb", "influxdb", "timescaledb",

    # Cloud / DevOps
    "aws", "amazon web services", "azure", "microsoft azure", "gcp",
    "google cloud", "google cloud platform", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "puppet", "chef", "jenkins", "gitlab ci",
    "github actions", "circleci", "travis ci", "ci/cd", "cicd",
    "linux", "unix", "nginx", "apache", "cloudflare",
    "serverless", "lambda", "ecs", "eks", "fargate", "ec2", "s3",
    "cloudformation", "pulumi", "helm", "istio", "prometheus",
    "grafana", "datadog", "new relic", "splunk", "elk",

    # APIs / Protocols
    "rest", "rest api", "restful", "graphql", "grpc", "websocket",
    "soap", "openapi", "swagger", "protobuf",

    # Tools / Practices
    "git", "github", "gitlab", "bitbucket", "jira", "confluence",
    "slack", "figma", "sketch", "adobe xd", "postman",
    "agile", "scrum", "kanban", "tdd", "bdd", "pair programming",
    "microservices", "monorepo", "design patterns", "solid",
    "oauth", "jwt", "sso", "saml", "ldap",

    # Soft skills (selectively)
    "stakeholder management", "project management", "team leadership",
    "mentoring", "cross-functional", "communication",
}

# Multi-word skills to check as phrases
MULTI_WORD_SKILLS = {s for s in TECH_SKILLS if " " in s or "." in s}
SINGLE_WORD_SKILLS = {s for s in TECH_SKILLS if " " not in s and "." not in s}


def extract_skills_from_text(text: str | list | dict) -> set[str]:
    """Extract recognized skills/technologies from text."""
    if not text:
        return set()

    if isinstance(text, (list, tuple, set)):
        text = " ".join(str(item) for item in text)
    elif isinstance(text, dict):
        text = " ".join(f"{k} {v}" for k, v in text.items())
    elif not isinstance(text, str):
        text = str(text)

    text_lower = text.lower()
    found = set()

    # Check multi-word skills first (phrase matching)
    for skill in MULTI_WORD_SKILLS:
        if skill in text_lower:
            found.add(skill)

    # Check single-word skills (word-boundary matching)
    words = set(re.findall(r'\b[\w#+.]+\b', text_lower))
    for skill in SINGLE_WORD_SKILLS:
        if skill in words:
            found.add(skill)

    return found


def extract_years_of_experience(text: str) -> Optional[int]:
    """Try to extract total years of experience from resume text."""
    if not text:
        return None

    patterns = [
        r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)',
        r'(?:experience|exp)\s*[:]\s*(\d+)\+?\s*years?',
        r'(\d+)\+?\s*yrs?\s*(?:of\s+)?(?:experience|exp)',
    ]

    max_years = 0
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            years = int(m)
            if 0 < years < 50:  # sanity check
                max_years = max(max_years, years)

    return max_years if max_years > 0 else None


class ResumeData:
    """Parsed resume data."""

    def __init__(self, resume_dir: str):
        self.raw_text = load_resume_text(resume_dir)
        self.skills = extract_skills_from_text(self.raw_text)
        self.years_experience = extract_years_of_experience(self.raw_text)
        self.text_lower = self.raw_text.lower()

    @property
    def is_loaded(self) -> bool:
        return bool(self.raw_text.strip())

    def has_skill(self, skill: str) -> bool:
        """Check if the resume mentions a specific skill."""
        return skill.lower() in self.skills or skill.lower() in self.text_lower

    def skill_overlap(self, required_skills: list[str]) -> tuple[list[str], list[str]]:
        """
        Compare required skills against resume.
        Returns (matched, missing).
        """
        matched = []
        missing = []
        for skill in required_skills:
            if self.has_skill(skill):
                matched.append(skill)
            else:
                missing.append(skill)
        return matched, missing
