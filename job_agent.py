import os
import json
import re
import html
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urlencode

START_DATE = date(2026, 10, 18)
END_DATE = date(2027, 10, 18)
MAX_DAILY_ALERTS = 15
SEEN_FILE = "seen_jobs.json"

SKILLS = [
    "python", "machine learning", "deep learning",
    "natural language processing", "nlp", "pytorch",
    "tensorflow", "scikit-learn", "pandas", "numpy",
    "data structures", "algorithms", "computer vision"
]

AI_TERMS = [
    "machine learning", "artificial intelligence",
    "deep learning", "natural language processing",
    "computer vision", "data science", " ml intern",
    " ai intern", "nlp", "generative ai"
]


def fetch_json(url):
    request = Request(
        url,
        headers={"User-Agent": "PersonalInternshipAlert/1.0",
                 "Accept": "application/json"}
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))



def clean(value):
    if value is None:
        return ""

    # Some job APIs return lists instead of strings.
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item is not None)
    elif not isinstance(value, str):
        value = str(value)

    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()



def normalize(source, job):
    """Convert each source's job fields into one common format."""

    if source == "Remotive":
        return {
            "id": str(job.get("id") or job.get("url") or ""),
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("candidate_required_location", "Remote"),
            "description": job.get("description", ""),
            "url": job.get("url", ""),
            "type": job.get("job_type", ""),
        }

    if source == "Jobicy":
        return {
            "id": str(job.get("id") or job.get("url") or ""),
            "title": job.get("jobTitle", ""),
            "company": job.get("companyName", ""),
            "location": job.get("jobGeo", "Remote"),
            "description": job.get("jobDescription", ""),
            "url": job.get("url", ""),
            "type": job.get("jobType", ""),
        }

    if source == "Arbeitnow":
        return {
            "id": str(job.get("slug") or job.get("url") or ""),
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("location", ""),
            "description": job.get("description", ""),
            "url": job.get("url", ""),
            "type": " ".join(job.get("job_types", []) or []),
            "remote": job.get("remote", False),
        }

    if source == "Adzuna":
        location = job.get("location") or {}
        company = job.get("company") or {}
        return {
            "id": str(job.get("id") or job.get("redirect_url") or ""),
            "title": job.get("title", ""),
            "company": company.get("display_name", ""),
            "location": location.get("display_name", "India"),
            "description": job.get("description", ""),
            "url": job.get("redirect_url", ""),
            "type": "",
        }

    return {}


def get_sources():
    results = []

    # Source 1: Remotive
    try:
        data = fetch_json("https://remotive.com/api/remote-jobs")
        for job in data.get("jobs", []):
            results.append(("Remotive", normalize("Remotive", job)))
        print(f"Remotive: {len(data.get('jobs', []))} listings")
    except Exception as error:
        print(f"Remotive unavailable: {error}")

    # Source 2: Jobicy, public API
    try:
        data = fetch_json(
            "https://jobicy.com/api/v2/remote-jobs?count=200"
        )
        jobs = data.get("jobs", [])
        for job in jobs:
            results.append(("Jobicy", normalize("Jobicy", job)))
        print(f"Jobicy: {len(jobs)} listings")
    except Exception as error:
        print(f"Jobicy unavailable: {error}")

    # Source 3: Arbeitnow public job board API
    try:
        data = fetch_json("https://www.arbeitnow.com/api/job-board-api")
        jobs = data.get("data", [])
        for job in jobs:
            results.append(("Arbeitnow", normalize("Arbeitnow", job)))
        print(f"Arbeitnow: {len(jobs)} listings")
    except Exception as error:
        print(f"Arbeitnow unavailable: {error}")

    # Source 4: Adzuna, optional API credentials
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()

    if app_id and app_key:
        for query in [
            "machine learning intern",
            "artificial intelligence intern",
            "data science intern",
            "python intern"
        ]:
            try:
                params = urlencode({
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "what": query,
                    "content-type": "application/json"
                })
                url = (
                    "https://api.adzuna.com/v1/api/jobs/in/search/1?"
                    + params
                )
                data = fetch_json(url)
                jobs = data.get("results", [])
                for job in jobs:
                    results.append(("Adzuna", normalize("Adzuna", job)))
                print(f"Adzuna ({query}): {len(jobs)} listings")
            except Exception as error:
                print(f"Adzuna query failed ({query}): {error}")
    else:
        print("Adzuna skipped: API credentials not configured.")

    return results


def is_internship(job):
    title = clean(job.get("title", "")).lower()
    job_type = clean(job.get("type", "")).lower()
    return "intern" in title or "internship" in job_type


def is_ai_role(job):
    title = clean(job.get("title", "")).lower()
    description = clean(job.get("description", "")).lower()
    title_match = any(term in title for term in AI_TERMS)
    description_match = any(term in description for term in AI_TERMS)
    return title_match or description_match


def location_matches(job):
    location = clean(job.get("location", "")).lower()
    source = job.get("source", "")

    remote = bool(job.get("remote", False)) or any(term in location for term in [
        "remote", "worldwide", "anywhere", "all countries",
        "india", "apac", "asia"
    ])

    # Adzuna uses the India country endpoint; its locations are Indian.
    if source == "Adzuna":
        return True

    return remote


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(seen, file, indent=2)


def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true"
    }).encode()

    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST"
    )

    with urlopen(request, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError("Telegram delivery failed")


def main():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    if today < START_DATE:
        print("Agent has not reached its start date.")
        return

    if today >= END_DATE:
        print("One-year period ended. No alerts sent.")
        return

    seen = load_seen()
    candidates = get_sources()
    selected = []
    known_this_run = set()

    for source, job in candidates:
        job["source"] = source
        job["title"] = clean(job.get("title", ""))
        job["company"] = clean(job.get("company", "Not listed"))
        job["location"] = clean(job.get("location", "Not specified"))
        job["url"] = job.get("url", "").strip()

        if not job["id"] or not job["url"]:
            continue

        if not is_internship(job) or not is_ai_role(job):
            continue

        if not location_matches(job):
            continue

        description = clean(job.get("description", "")).lower()
        searchable = f"{job['title'].lower()} {description}"
        matched = [skill for skill in SKILLS if skill in searchable]

        if not matched:
            continue

        # Use the canonical URL to deduplicate across sources.
        key = re.sub(r"[?#].*$", "", job["url"].rstrip("/")).lower()

        if key in seen or key in known_this_run:
            continue

        known_this_run.add(key)
        selected.append((source, job, matched, key))

    selected = selected[:MAX_DAILY_ALERTS]

    if not selected:
        send_telegram(
            f"AI/ML Internship Agent — {today}\n\n"
            f"Sources checked: {len(candidates)} listings collected.\n"
            "No new listings passed the current filters.\n"
            "I'll check again tomorrow."
        )
        print("No new matches.")
        return

    for source, job, matched, key in selected:
        message = (
            f"🎯 AI/ML INTERNSHIP\n\n"
            f"Role: {job['title']}\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Matched skills: {', '.join(matched)}\n"
            f"Source: {source}\n"
            f"Apply / details: {job['url']}\n\n"
            "Verify the vacancy on the employer's official page "
            "before sharing personal information."
        )

        send_telegram(message)
        seen[key] = {
            "date": today.isoformat(),
            "title": job["title"],
            "source": source,
            "url": job["url"]
        }

    save_seen(seen)
    print(f"Sent {len(selected)} new internship alerts.")


if __name__ == "__main__":
    main()
