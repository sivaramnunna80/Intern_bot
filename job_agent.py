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
