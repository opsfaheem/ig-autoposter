#!/usr/bin/env python3
"""Publish due rows from queue.csv to Instagram via the Graph API.

Supports IMAGE, REELS and CAROUSEL posts. Publish times are UTC.
Env vars: IG_USER_ID, IG_ACCESS_TOKEN (required unless DRY_RUN=1)
Optional: QUEUE_FILE, GRAPH_VERSION, MAX_PER_RUN, DRY_RUN
"""
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v21.0")
API = f"https://graph.facebook.com/{GRAPH_VERSION}"
QUEUE_FILE = os.getenv("QUEUE_FILE", "queue.csv")
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "2"))
DRY_RUN = os.getenv("DRY_RUN") == "1"

IG_USER_ID = os.environ.get("IG_USER_ID", "")
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")

FIELDS = ["id", "type", "media_urls", "caption", "hashtags",
          "publish_at", "status", "post_id", "error"]


def call(method, path, **params):
    params["access_token"] = TOKEN
    r = requests.request(method, f"{API}/{path}",
                         data=params if method == "POST" else None,
                         params=params if method == "GET" else None,
                         timeout=60)
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise RuntimeError(f"{err.get('message', r.text)} (code {err.get('code')})")
    return data


def wait_for_container(container_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        status = call("GET", container_id, fields="status_code,status")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {code}: {status.get('status')}")
        time.sleep(10)
    raise TimeoutError("Timed out waiting for media processing")


def build_caption(row):
    caption = (row.get("caption") or "").strip()
    tags = (row.get("hashtags") or "").strip()
    return f"{caption}\n\n{tags}".strip() if tags else caption


def is_video(url):
    return url.lower().split("?")[0].endswith((".mp4", ".mov"))


def create_container(row):
    kind = row["type"].strip().upper()
    urls = [u.strip() for u in row["media_urls"].split("|") if u.strip()]
    caption = build_caption(row)
    if not urls:
        raise ValueError("media_urls is empty")

    if kind == "IMAGE":
        return call("POST", f"{IG_USER_ID}/media",
                    image_url=urls[0], caption=caption)["id"]

    if kind == "REELS":
        return call("POST", f"{IG_USER_ID}/media", media_type="REELS",
                    video_url=urls[0], caption=caption,
                    share_to_feed="true")["id"]

    if kind == "CAROUSEL":
        if not 2 <= len(urls) <= 10:
            raise ValueError("Carousel needs 2-10 media URLs")
        children = []
        for u in urls:
            if is_video(u):
                cid = call("POST", f"{IG_USER_ID}/media", media_type="VIDEO",
                           video_url=u, is_carousel_item="true")["id"]
                wait_for_container(cid)
            else:
                cid = call("POST", f"{IG_USER_ID}/media", image_url=u,
                           is_carousel_item="true")["id"]
            children.append(cid)
        return call("POST", f"{IG_USER_ID}/media", media_type="CAROUSEL",
                    children=",".join(children), caption=caption)["id"]

    raise ValueError(f"Unknown type '{kind}' (use IMAGE, REELS or CAROUSEL)")


def publish(row):
    container_id = create_container(row)
    wait_for_container(container_id)
    return call("POST", f"{IG_USER_ID}/media_publish",
                creation_id=container_id)["id"]


def is_due(row, now):
    if (row.get("status") or "").strip():
        return False
    try:
        when = datetime.fromisoformat(row["publish_at"].strip().replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= now


def main():
    if not DRY_RUN and not (IG_USER_ID and TOKEN):
        sys.exit("IG_USER_ID and IG_ACCESS_TOKEN must be set")

    with open(QUEUE_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    now = datetime.now(timezone.utc)
    due = [r for r in rows if is_due(r, now)][:MAX_PER_RUN]
    print(f"{len(due)} post(s) due")
    failed = False

    for row in due:
        label = f"{row['id']} ({row['type']})"
        if DRY_RUN:
            print(f"[dry run] would publish {label}")
            continue
        try:
            row["post_id"] = publish(row)
            row["status"] = "posted"
            row["error"] = ""
            print(f"Posted {label} -> {row['post_id']}")
        except Exception as e:  # keep going so one bad row doesn't block the rest
            row["status"] = "error"
            row["error"] = str(e)[:300]
            failed = True
            print(f"FAILED {label}: {e}", file=sys.stderr)

    if not DRY_RUN:
        with open(QUEUE_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
