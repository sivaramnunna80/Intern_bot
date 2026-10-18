
import os
import json
import re
import html
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# Active for one year: update these dates if needed.
START_DATE = date(2026, 10, 18)
END_DATE = date(2027, 10, 18)

API_URL = "https://remotive.com/api/remote-jobs?limit=500"
SEEN_FILE = "seen_jobs.json"
MAX_DAILY_ALERTS = 10

SKILLS = [
    "python", "machine learning", "deep learning",
    "natural language processing", "nlp", "pytorch",
    "tensorflow", "scikit-learn", "pandas", "numpy",
    "data structures", "algorithms"
]

AI_ROLES = [
    "machine learning", "artificial intelligence",
    "deep learning", "nlp", "natural language processing",
    "computer vision", "ai intern", "ml intern",
    "data science", "research intern"
]


def get_json(url, data=None):
    request = Request(
        url,
        data=data,
        headers={"User-Agent": "InternshipAlertBot/1.0"}
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true"
    }).encode()

    result = get_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data
    )

    if not result.get("ok"):
        raise RuntimeError("Telegram message could not be sent")


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(seen, file, indent=2)


def is_relevant(job):
    title = clean(job.get("title", "")).lower()
    description = clean(job.get("description", "")).lower()
    job_type = (job.get("job_type") or "").lower()

    # Require an internship title or internship job type.
    if "intern" not in title and job_type != "internship":
        return False

    text = f"{title} {description}"

    # Avoid broad matches on the letters "ai" alone.
    return any(role in text for role in AI_ROLES)


def location_matches(job):
    location = clean(
        job.get("candidate_required_location", "")
    ).lower()

    # Remotive is a remote-jobs source. Check geographic eligibility.
    return any(term in location for term in [
        "india", "worldwide", "anywhere", "all countries"
    ])


def main():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    if today < START_DATE:
        print("Agent has not reached its start date.")
        return

    if today >= END_DATE:
        print("One-year period ended. No alerts sent.")
        return

    jobs = get_json(API_URL).get("jobs", [])
    seen = load_seen()
    matches = []

    for job in jobs:
        job_id = str(job.get("id") or job.get("url") or "")
        if not job_id or job_id in seen:
            continue

        if not is_relevant(job) or not location_matches(job):
            continue

        title = clean(job.get("title", "Internship"))
        company = clean(job.get("company_name", "Not listed"))
        description = clean(job.get("description", "")).lower()
        text = f"{title.lower()} {description}"

        matched_skills = [
            skill for skill in SKILLS if skill in text
        ]

        # Require at least one of your target skills.
        if not matched_skills:
            continue

        matches.append((job, job_id, matched_skills))

    matches = matches[:MAX_DAILY_ALERTS]

    if not matches:
        send_telegram(
            f"AI/ML Internship Agent — {today}\n\n"
            "No new matching remote internships found today.\n"
            "I'll check again tomorrow."
        )
        print("No new matches.")
        return

    for job, job_id, skills in matches:
        title = clean(job.get("title", "Internship"))
        company = clean(job.get("company_name", "Not listed"))
        location = clean(
            job.get("candidate_required_location", "Remote")
        )
        url = job.get("url", "")

        message = (
            f"🎯 AI/ML INTERNSHIP\n\n"
            f"Role: {title}\n"
            f"Company: {company}\n"
            f"Eligible location: {location}\n"
            f"Matching skills: {', '.join(skills)}\n"
            f"Source: Remotive\n"
            f"Listing: {url}\n\n"
            "Check the employer's official application page "
            "before sharing personal information."
        )

        send_telegram(message)
        seen[job_id] = today.isoformat()

    save_seen(seen)
    print(f"Sent {len(matches)} internship alerts.")


if __name__ == "__main__":
    main()
