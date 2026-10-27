# ferry-signal

Free, autonomous phone notifications when the **Glenora ferry** (Glenora ⇄
Adolphustown, Prince Edward County, Ontario) goes out of service — and when
it comes back.

## How it works

```
GitHub Actions (cron, every 15 min)
        │
        ▼
Ontario 511 API  ──  https://511on.ca/api/v2/get/ferryterminals
(MTO's official traveller-info system — the same source that
 powers the @511Ontario tweets and the 511on.ca website)
        │
        ▼
monitor.py  ──  compares against last known status (state/status.json)
        │
        ▼  only when the status CHANGES
ntfy.sh  ──  push notification to the ntfy app on your phone
```

Everything in this stack is free:

- **Ontario 511 API** — free public API; requires a free developer key.
- **GitHub Actions** — free unlimited minutes on public repos. (On a
  *private* repo the free tier is 2,000 min/month and each run bills a
  1-minute minimum, so drop the cron to `*/30` to stay comfortably free.)
- **ntfy.sh** — free push notifications, no account required.

### Why not monitor Twitter/X directly?

Twitter's free API tier no longer allows *reading* tweets, so free
autonomous tweet monitoring isn't viable. Happily it isn't needed: the
@511Ontario ferry tweets ("#ONFerry Glenora Ferry Service: ...") are
generated from the same Ontario 511 system this monitor polls, so the API
gives you the same information, usually structured better and just as fast.

## Setup (one time, ~5 minutes)

1. **Install the ntfy app** on your phone
   ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) /
   [iOS](https://apps.apple.com/us/app/ntfy/id1625396347)).

2. **Pick a secret topic name.** Anyone who knows the topic name can send
   you notifications, so make it unguessable, e.g.
   `glenora-ferry-x7k2mq9v`. In the app: *Subscribe to topic* → enter your
   topic name (server: default `ntfy.sh`).

3. **Get an Ontario 511 developer key.** Sign up for an account at
   [511on.ca](https://511on.ca), then request a key on the
   [developer page](https://511on.ca/developers/help).

4. **Add both as repo secrets.** In this GitHub repo:
   *Settings → Secrets and variables → Actions → New repository secret*:
   - `NTFY_TOPIC` — your topic name.
   - `ONTARIO_511_KEY` — your developer key.

5. **Test it.** *Actions → Ferry monitor → Run workflow*, tick
   "Send a test notification", and run. A test message should hit your
   phone within seconds.

That's it. The schedule takes over from there.

## What you'll be notified about

- 🚨 **High-priority** notification when the Glenora ferry's status is
  anything other than "In Service" (out of service, reduced service, ...),
  including MTO's details and estimated return time when provided.
- ✅ **Normal** notification when it returns to service.
- ⚠️ A one-time warning if the ferry disappears from the 511 feed
  (i.e. the API changed and the monitor needs fixing).

No repeated nagging: a notification fires only when the status *changes*.
The last-seen status lives in `state/status.json`, committed by the
workflow after each change.

## Caveats

- **Latency:** worst case is one cron interval (~15 min) plus however long
  MTO takes to update Ontario 511 — in practice they update it promptly,
  since it drives their own site, app, and tweets.
- **Scheduled-workflow auto-disable:** GitHub disables cron workflows in
  repos with no activity for 60 days. The state commits the workflow makes
  when the status changes count as activity, but if GitHub ever emails you
  that the workflow was disabled, one click re-enables it.
- **Tuning:** `FERRY_MATCH` (default `glenora`) can be changed in the
  workflow env to watch a different Ontario ferry (e.g. `amherst` or
  `wolfe`), and `NTFY_SERVER` supports self-hosted ntfy.
