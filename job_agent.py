import os
import json
import re
import html
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

# Active for one year: 18 Oct 2026 through 17 Oct 2027.
START_DATE = date(2026, 10, 18)
END_DATE = date(2027, 10, 18)  # Alerts stop on this date.
MAX_DAILY_ALERTS = 15
SEEN_FILE = "seen_jobs.json"

# Match relevant internship titles, plus related skills in descriptions.
ROLE_TERMS = [
    "machine learning", "artificial intelligence", "ai intern", "ml intern",
    "data science", "data scientist intern", "deep learning",
    "natural language processing", "nlp intern", "computer vision",
    "generative ai", "llm intern", "python intern", "research intern",
    "software engineer intern", "software developer intern"
]
SKILLS = [
    "python", "machine learning", "deep learning",
    "artificial intelligence", "natural language processing", "nlp",
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy",
    "computer vision", "generative ai", "large language model", "llm",
    "data science", "data analysis", "neural network"
]
AI_TERMS = [
    "machine learning", "artificial intelligence", "deep learning",
    "natural language processing", "computer vision", "data science",
    "generative ai", "large language model", "neural network",
    "pytorch", "tensorflow", "scikit-learn", "nlp"
]


def fetch_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "PersonalInternshipAlert/1.0",
            "Accept": "application/json"
        }
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def clean(value):
    """Convert API fields of different types to safe plain text."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item is not None)
    elif isinstance(value, dict):
        value = " ".join(str(item) for item in value.values() if item is not None)
    elif not isinstance(value, str):
        value = str(value)

    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize(source, job):
    """Convert different public job-feed formats into one format."""
    if source == "Remotive":
        return {
            "id": str(job.get("id") or job.get("url") or ""),
            "title": clean(job.get("title")),
            "company": clean(job.get("company_name")),
            "location": clean(job.get("candidate_required_location") or "Remote"),
            "description": clean(job.get("description")),
            "url": clean(job.get("url")),
            "type": clean(job.get("job_type")),
            "remote": True
        }

    if source == "Jobicy":
        return {
            "id": str(job.get("id") or job.get("url") or ""),
            "title": clean(job.get("jobTitle")),
            "company": clean(job.get("companyName")),
            "location": clean(job.get("jobGeo") or "Remote"),
            "description": clean(job.get("jobDescription")),
            "url": clean(job.get("url")),
            "type": clean(job.get("jobType")),
            "remote": True
        }

    if source == "Arbeitnow":
        return {
            "id": str(job.get("slug") or job.get("url") or ""),
            "title": clean(job.get("title")),
            "company": clean(job.get("company_name")),
            "location": clean(job.get("location")),
            "description": clean(job.get("description")),
            "url": clean(job.get("url")),
            "type": clean(job.get("job_types")),
            "remote": bool(job.get("remote", False))
        }

    return {}


def get_sources():
    results = []

    sources = [
        ("Remotive", "https://remotive.com/api/remote-jobs", "jobs"),
        ("Jobicy", "https://jobicy.com/api/v2/remote-jobs?count=200", "jobs"),
        ("Arbeitnow", "https://www.arbeitnow.com/api/job-board-api", "data")
    ]

    for source, url, list_key in sources:
        try:
            data = fetch_json(url)
            jobs = data.get(list_key, [])
            if not isinstance(jobs, list):
                print(f"{source}: unexpected API response format")
                continue
            for job in jobs:
                if isinstance(job, dict):
                    normalized = normalize(source, job)
                    if normalized:
                        results.append((source, normalized))
            print(f"{source}: {len(jobs)} listings")
        except Exception as error:
            print(f"{source} unavailable: {error}")

    print("Adzuna skipped: optional API credentials are not configured.")
    return results


def is_internship(job):
    title = clean(job.get("title")).lower()
    job_type = clean(job.get("type")).lower()
    return (
        "intern" in title
        or "internship" in title
        or "intern" in job_type
        or "internship" in job_type
    )


def is_ai_role(job):
    title = clean(job.get("title")).lower()
    description = clean(job.get("description")).lower()
    # A clear relevant title is sufficient; otherwise require AI-related
    # terms in the description to reduce irrelevant results.
    if any(term in title for term in ROLE_TERMS):
        return True
    return any(term in f"{title} {description}" for term in AI_TERMS)


def location_matches(job):
    location = clean(job.get("location")).lower()
    source = job.get("source", "")

    india_terms = ["india", "bengaluru", "bangalore", "hyderabad",
                   "chennai", "mumbai", "pune", "delhi", "noida",
                   "gurugram", "gurgaon", "kolkata"]
    remote_terms = ["remote", "worldwide", "anywhere", "all countries",
                    "asia", "apac"]

    if source in ("Remotive", "Jobicy"):
        # These are remote-job feeds. The listing still needs to match
        # the internship and AI/ML filters above.
        return True

    if job.get("remote", False):
        return True

    return any(term in location for term in india_terms + remote_terms)


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(seen, file, indent=2, ensure_ascii=False)


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub secret."
        )

    from urllib.parse import urlencode
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
        raise RuntimeError("Telegram delivery failed: " + str(result))


def main():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    if today < START_DATE:
        print("Agent has not reached its start date.")
        return
    if today >= END_DATE:
        print("One-year period ended. No alerts sent.")
        return

    candidates = get_sources()
    seen = load_seen()
    selected = []
    known_this_run = set()

    for source, job in candidates:
        job["source"] = source
        job["title"] = clean(job.get("title"))
        job["company"] = clean(job.get("company")) or "Not listed"
        job["location"] = clean(job.get("location")) or "Not specified"
        job["url"] = clean(job.get("url"))

        if not job["url"] or not job["title"]:
            continue
        if not is_internship(job):
            continue
        if not is_ai_role(job):
            continue
        if not location_matches(job):
            continue

        searchable = (job["title"] + " " + clean(job.get("description"))).lower()
        matched = [skill for skill in SKILLS if skill in searchable]
        if not matched:
            matched = ["Relevant internship title"]

        # Remove URL tracking/query fragments for deduplication.
        key = re.sub(r"[?#].*$", "", job["url"].rstrip("/")).lower()
        if key in seen or key in known_this_run:
            continue

        known_this_run.add(key)
        selected.append((source, job, matched, key))

    selected = selected[:MAX_DAILY_ALERTS]

    if not selected:
        message = (
            f"AI/ML Internship Agent — {today}\n\n"
            f"Sources checked: {len(candidates)} listings collected.\n"
            "No new listings passed the current filters today.\n"
            "I'll check again tomorrow."
        )
        send_telegram(message)
        print("No new matches.")
        return

    # Save after each successful Telegram delivery so a later failure
    # doesn't cause all already-sent messages to repeat next time.
    sent_count = 0
    for source, job, matched, key in selected:
        message = (
            f"🎯 AI/ML INTERNSHIP\n\n"
            f"Role: {job['title']}\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Matched skills: {', '.join(matched[:8])}\n"
            f"Source: {source}\n"
            f"Apply / details: {job['url']}\n\n"
            "Please verify the vacancy on the employer's official page "
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
        sent_count += 1

    print(f"Sent {sent_count} new internship alerts.")


if __name__ == "__main__":
    main()
