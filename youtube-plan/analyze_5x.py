#!/usr/bin/env python3
"""登録者数の5倍以上再生された動画を抽出する。

使い方:
  export YT_API_KEY=<YouTube Data API v3 のキー>
  python3 youtube-plan/analyze_5x.py youtube-plan/channels.txt out.csv [--ratio 5] [--months 24]

channels.txt には1行1チャンネルで @ハンドル か UC から始まるチャンネルIDを書く。
# で始まる行は無視。標準ライブラリのみで動く。
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/youtube/v3/"


def call(endpoint, **params):
    params["key"] = os.environ["YT_API_KEY"]
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def resolve_channel(ref):
    part = "snippet,statistics,contentDetails"
    if ref.startswith("UC"):
        data = call("channels", part=part, id=ref)
    else:
        data = call("channels", part=part, forHandle=ref.lstrip("@"))
    items = data.get("items", [])
    return items[0] if items else None


def uploads(playlist_id, since):
    page = None
    while True:
        params = dict(part="contentDetails", playlistId=playlist_id, maxResults=50)
        if page:
            params["pageToken"] = page
        data = call("playlistItems", **params)
        for it in data.get("items", []):
            published = it["contentDetails"].get("videoPublishedAt", "")
            if published and published < since:
                return
            yield it["contentDetails"]["videoId"]
        page = data.get("nextPageToken")
        if not page:
            return


def iso_seconds(d):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d)
    h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channels")
    ap.add_argument("out")
    ap.add_argument("--ratio", type=float, default=5.0)
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args()

    if "YT_API_KEY" not in os.environ:
        sys.exit("YT_API_KEY が未設定です")

    since = (dt.datetime.utcnow() - dt.timedelta(days=30 * args.months)).strftime("%Y-%m-%dT%H:%M:%SZ")
    refs = [l.strip() for l in open(args.channels, encoding="utf-8") if l.strip() and not l.startswith("#")]

    rows = []
    for ref in refs:
        ch = resolve_channel(ref)
        if not ch:
            print(f"見つからない: {ref}", file=sys.stderr)
            continue
        stats = ch["statistics"]
        if stats.get("hiddenSubscriberCount"):
            print(f"登録者数非公開: {ref}", file=sys.stderr)
            continue
        subs = int(stats.get("subscriberCount", 0))
        if subs == 0:
            continue
        ids = list(uploads(ch["contentDetails"]["relatedPlaylists"]["uploads"], since))
        for i in range(0, len(ids), 50):
            data = call("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
            for v in data.get("items", []):
                views = int(v["statistics"].get("viewCount", 0))
                ratio = views / subs
                if ratio < args.ratio:
                    continue
                sec = iso_seconds(v["contentDetails"]["duration"])
                rows.append({
                    "チャンネル": ch["snippet"]["title"],
                    "登録者数": subs,
                    "タイトル": v["snippet"]["title"],
                    "URL": f"https://www.youtube.com/watch?v={v['id']}",
                    "投稿日": v["snippet"]["publishedAt"][:10],
                    "再生数": views,
                    "倍率": round(ratio, 1),
                    "尺(秒)": sec,
                    "ショート候補": "Y" if sec <= 180 else "N",
                    "タイトルの型": "", "サムネ": "", "冒頭30秒": "", "テーマ": "", "メモ": "",
                })

    rows.sort(key=lambda r: r["倍率"], reverse=True)
    fields = list(rows[0].keys()) if rows else ["チャンネル"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} 本を {args.out} に出力しました")


if __name__ == "__main__":
    main()
