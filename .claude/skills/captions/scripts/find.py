#!/usr/bin/env python3
"""Retrieve real captions. Examples (run from the skill folder, or anywhere with the path):
  python3 scripts/find.py claude tennis laptop            # keyword search (BM25-ish), meme style by default
  python3 scripts/find.py --top 40 --by multiple          # what overperformed its own account the most
  python3 scripts/find.py --top 40 --by views --style any # biggest posts, any style
  python3 scripts/find.py --author iansbrash              # one creator, newest first
  python3 scripts/find.py --sample 30                     # random meme captions for few-shot flavour
  python3 scripts/find.py --style meme --kind onscreen laid off
Filters: --all (off-niche too) --style meme|guru|other|any (default meme) --kind caption|onscreen|any --platform tiktok|youtube|any
         --min-views N --min-words N --max-words N --n N (default 25) --json"""
import json, re, math, sys, argparse, random, pathlib, collections
K = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(); ap.add_argument("query", nargs="*"); ap.add_argument("--style", default="meme"); ap.add_argument("--kind", default="any"); ap.add_argument("--platform", default="tiktok")
ap.add_argument("--author"); ap.add_argument("--top", type=int); ap.add_argument("--by", default="multiple", choices=["multiple", "views", "likes", "shares", "created"]); ap.add_argument("--sample", type=int)
ap.add_argument("--all", action="store_true", help="include off-niche posts (default: niche only)"); ap.add_argument("--min-views", type=int, default=0); ap.add_argument("--min-words", type=int, default=1); ap.add_argument("--max-words", type=int, default=999); ap.add_argument("--n", type=int, default=25); ap.add_argument("--json", action="store_true")
a = ap.parse_args()
rows = [json.loads(l) for l in open(K / "captions.jsonl", encoding="utf-8")]
def ok(r):
    if a.style != "any" and r["style"] != a.style: return False
    if a.kind != "any" and r["kind"] != a.kind: return False
    if a.platform != "any" and r["platform"] != a.platform: return False
    if a.author and (r["author"] or "").lower() != a.author.lower(): return False
    if not a.all and not r.get("niche"): return False
    if r["views"] < a.min_views or not (a.min_words <= r["words"] <= a.max_words): return False
    return bool(r["text_clean"])
rows = [r for r in rows if ok(r)]
tok = lambda s: re.findall(r"[a-z0-9']+", s.lower())
if a.query:
    q = tok(" ".join(a.query)); N = len(rows); df = collections.Counter()
    docs = [tok(r["text_clean"] + " " + " ".join(r["hashtags"])) for r in rows]
    for d in docs: df.update(set(d))
    avg = sum(len(d) for d in docs) / max(1, N)
    def score(d):
        tf = collections.Counter(d); s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)); s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        return s
    scored = sorted(zip((score(d) for d in docs), rows), key=lambda x: (-x[0], -(x[1]["multiple"] or 0)))
    rows = [r for s, r in scored if s > 0][: a.n]
elif a.sample:
    random.shuffle(rows); rows = rows[: a.sample]
else:
    key = (lambda r: -(r[a.by] or 0)) if a.by != "created" else (lambda r: r["created"] or "")
    rows = sorted(rows, key=key, reverse=(a.by == "created"))[: (a.top or a.n)]
if a.json: print(json.dumps(rows, ensure_ascii=False, indent=1)); sys.exit()
for r in rows:
    m = f"{r['multiple']:.1f}x" if r.get("multiple") else "  -  "
    print(f"{r['views']:>9} {m:>6} @{(r['author'] or '?')[:16]:16} {r['text_clean'][:110]}  {'#'+' #'.join(h.lstrip('#') for h in r['hashtags'][:4]) if r['hashtags'] else ''}")
