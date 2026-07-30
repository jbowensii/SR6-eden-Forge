"""First-pass automatic artwork: for art-less items in the chosen domains, search
the web (via the running site's /api/artsearch, honoring the configured engine)
and download the TOP result (best relevance match) into the item's art slot via
/api/art/download. Rate-limited; capped per run. Downloads are catalogued as
corrections (writeItem), so they survive re-import.

Usage: python tools/bulk_art.py [--domains critters,vehicles,npcs] [--limit 80]
Requires the site server running (npm run serve).
"""
import sys
import glob
import json
import time
import urllib.parse
import urllib.request

BASE = "http://localhost:8347"
LIBRARY = "corebook"


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def main():
    args = sys.argv[1:]
    domains = ["critters", "vehicles", "npcs", "spirits"]
    limit = 80
    for i, a in enumerate(args):
        if a == "--domains" and i + 1 < len(args):
            domains = args[i + 1].split(",")
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    done = fail = 0
    for domain in domains:
        for f in sorted(glob.glob(f"data/{LIBRARY}/{domain}/*.json")):
            payload = json.load(open(f, encoding="utf-8"))
            category = payload["category"]
            for it in payload["items"]:
                if it.get("img") or done >= limit:
                    continue
                try:
                    res = _get("/api/artsearch?q=" + urllib.parse.quote(it["name"]))
                    hits = res.get("results") or []
                    if not hits:
                        print(f"  no art: {domain}/{it['name']}", flush=True)
                        continue
                    r = _post("/api/art/download", {"book": LIBRARY, "domain": domain,
                              "category": category, "id": it["id"], "url": hits[0]["full"]})
                    if r.get("img"):
                        done += 1
                        print(f"  [{done}] {domain}/{it['name']} -> {r['img']}", flush=True)
                    else:
                        fail += 1
                        print(f"  fail {it['name']}: {r.get('error')}", flush=True)
                except Exception as e:
                    fail += 1
                    print(f"  err {it['name']}: {e}", flush=True)
                time.sleep(1.2)   # be polite to the image host / avoid rate limits
            if done >= limit:
                break
        if done >= limit:
            break
    print(f"downloaded {done} images, {fail} failures")
    print("done")


if __name__ == "__main__":
    main()
