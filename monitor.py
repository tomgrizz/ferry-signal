#!/usr/bin/env python3
"""Glenora ferry monitor.

Polls the Ontario 511 API (the same MTO system that powers the @511Ontario
tweets and the 511on.ca website) for the Glenora ferry's service status,
and sends a push notification via ntfy.sh whenever the status changes
(out of service, reduced service, back in service).

Designed to run from a GitHub Actions cron job. State between runs is kept
in state/status.json, which the workflow commits back to the repo.

Environment variables:
  NTFY_TOPIC   (required to notify) ntfy.sh topic to publish to.
  NTFY_SERVER  ntfy server base URL, default https://ntfy.sh
  FERRY_MATCH  substring to match against terminal names, default "glenora"
  STATE_FILE   path to the state file, default state/status.json
  TEST_NOTIFY  if set to "1", just send a test notification and exit.

No third-party dependencies: Python 3.9+ standard library only.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://511on.ca/api/v2/get/ferryterminals?format=json"
USER_AGENT = "ferry-signal/1.0 (personal Glenora ferry status monitor)"

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
FERRY_MATCH = os.environ.get("FERRY_MATCH", "glenora").lower()
STATE_FILE = os.environ.get("STATE_FILE", "state/status.json")

IN_SERVICE = "in service"


def fetch_terminals(retries: int = 3, backoff: float = 5.0) -> list:
    """Fetch all ferry terminals from Ontario 511, with retries."""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if not isinstance(data, list):
                raise ValueError(f"unexpected API response type: {type(data)}")
            return data
        except (urllib.error.URLError, ValueError, json.JSONDecodeError) as err:
            last_err = err
            print(f"API fetch attempt {attempt + 1}/{retries} failed: {err}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise SystemExit(f"Ontario 511 API unreachable after {retries} attempts: {last_err}")


def matching_terminals(terminals: list) -> list:
    """Return terminals whose name/description mentions the target ferry."""
    matches = []
    for t in terminals:
        haystack = " ".join(
            str(t.get(key, "")) for key in ("Id", "LocationDescription")
        ).lower()
        if FERRY_MATCH in haystack:
            matches.append(t)
    return matches


def summarize(terminals: list) -> dict:
    """Reduce matched terminal entries to the fields we care about."""
    entries = {}
    for t in terminals:
        key = str(t.get("Id") or t.get("LocationDescription") or "unknown")
        entries[key] = {
            "name": t.get("LocationDescription") or key,
            "status": (t.get("Status") or "Unknown").strip(),
            "details": (t.get("Details") or "").strip(),
            "return_time": t.get("EstimatedReturnToServiceTime"),
        }
    return entries


def is_down(entry: dict) -> bool:
    return entry["status"].lower() != IN_SERVICE


def notify(title: str, message: str, priority: str, tags: str) -> None:
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set; skipping notification. Would have sent:", file=sys.stderr)
        print(f"  [{priority}] {title}: {message}", file=sys.stderr)
        return
    req = urllib.request.Request(
        f"{NTFY_SERVER}/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Title": title,
            "Priority": priority,
            "Tags": tags,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
    print(f"Notification sent: {title}")


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(entries: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, sort_keys=True)
        f.write("\n")


def main() -> None:
    if os.environ.get("TEST_NOTIFY") == "1":
        notify(
            "Ferry monitor test",
            "Test notification from ferry-signal. If you can read this, "
            "your phone is hooked up correctly.",
            priority="default",
            tags="ferry,white_check_mark",
        )
        return

    previous = load_state()
    current = summarize(matching_terminals(fetch_terminals()))

    if not current:
        # The ferry vanished from the feed entirely — worth knowing about,
        # but only say it once, not on every run.
        if previous.get("_feed_missing") != True:  # noqa: E712
            notify(
                "Ferry monitor: no data",
                f"No terminal matching '{FERRY_MATCH}' found in the Ontario 511 "
                "feed. The API may have changed; check 511on.ca.",
                priority="default",
                tags="ferry,warning",
            )
        save_state({"_feed_missing": True})
        return

    first_run = not previous or previous.get("_feed_missing")
    for key, entry in current.items():
        prev = previous.get(key)
        status_changed = prev is not None and prev.get("status") != entry["status"]
        details = entry["details"] or "No further details from Ontario 511."

        if is_down(entry) and (status_changed or (first_run and prev is None)):
            eta = entry.get("return_time")
            eta_line = f"\nEstimated return to service: {eta}" if eta else ""
            notify(
                f"{entry['name']}: {entry['status']}",
                f"{details}{eta_line}",
                priority="high",
                tags="ferry,rotating_light",
            )
        elif status_changed and not is_down(entry):
            notify(
                f"{entry['name']}: back in service",
                details,
                priority="default",
                tags="ferry,white_check_mark",
            )
        else:
            print(f"{entry['name']}: {entry['status']} (no change)")

    save_state(current)


if __name__ == "__main__":
    main()
