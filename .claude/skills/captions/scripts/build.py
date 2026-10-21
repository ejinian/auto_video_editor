#!/usr/bin/env python3
"""Merge raw harvests into captions.jsonl (one row per post) with a style label and a
per-author 'multiple' (views / that author's median views, when the author has >=5 posts).
Run from the skill folder:  python3 scripts/build.py"""
import json, re, csv, statistics, collections, datetime, pathlib, sys
K = pathlib.Path(__file__).resolve().parent.parent
raw = K / "raw"; rows = {}
TAG = re.compile(r"#\S+"); EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")
CTA = re.compile(r"\b(comment|link in (my )?bio|in my bio|follow (me|for)|part ?2|pt\.? ?2|save this|dm me|free|ebook|tutorial|guide|setup|step[- ]by[- ]step|sign up|join (my|the)|waitlist|subscribe|full (video|list|guide)|here('s| is) how|how to|wait (until|till|for) the end|you need|must[- ]have|game[- ]?chang\w+|changed how|just dropped|tools?|hacks?|tips?|prompts?|plugins?|skills?|automation|workflow|tutorial|scam|legit|hiring|apply|\d+/10|\$\$)\b", re.I)
GURU_AUTHORS = {"justyn.ai","benkimball.ai","sarutalksai","taki.gpt","nathanhodgson.ai","petethetechguy","usamasboard","smart.easy","yury.ai","milesreevesai","insiderforce","mac_sidehustle","jaredrhod","matt_thecoder","velixai0","nocode.joshua","haejuicyy","allsense01","sophia.designsthings"}
CLICKBAIT_EMOJI = re.compile("[\U0001F92F\U0001F525\U0001F680\u26A0\U0001F4A5\U0001F449\U0001F447]")
ES = re.compile(r"\b(que|para|como|los|las|una|esto|está|aquí|hoy|con|por|del|vous|pour|est|les|trop|avec|dans|sur)\b", re.I)
NICHE = re.compile(r"(claude|anthropic|\bopus\b|\bsonnet\b|cursor|vibe ?cod\w*|\bcod(e|ing|er|ers|ed|es)\b|program(mer|mers|ming)|\bdevs?\b|developer|software|engineer\w*|\bswe\b|comp ?sci|computer science|\bcs ?major|\bsaas\b|github|\bapi\b|api keys?|laptop|macbook|terminal|chatgpt|openai|\bllms?\b|\bgpt|replit|lovable|techbro|tech bro|\binterns?(hip)?\b|faang|big tech|layoffs?|laid off|unemploy\w*|junior|senior eng|pull requests?|\bprs?\b|hackathon|y ?combinator|\bmrr\b|\bai\b|a\.i\.|machine learning|hello world|stack ?overflow|print statement|debug\w*|prod\b|git commit|deploy\w*|\bship(ped|ping)\b)", re.I)
def non_latin_share(c):
    letters = [ch for ch in c if ch.isalpha()]
    if not letters: return 0.0
    return sum(1 for ch in letters if ord(ch) > 0x24F) / len(letters)
def clean(t): return re.sub(r"\s+", " ", TAG.sub("", t or "")).strip()
def style(text, author=None):
    c = clean(text); w = c.split()
    if not w: return "tagsonly"
    if len(ES.findall(c)) >= 3 or non_latin_share(c) > 0.3: return "non-english"
    if (author or "").lower() in GURU_AUTHORS: return "guru"
    if CTA.search(c) or CLICKBAIT_EMOJI.search(c) or len(w) > 28: return "guru"
    if len(w) <= 16: return "meme"
    return "other"
def put(r):
    i = str(r["id"]); 
    if i in rows: return
    text = r.get("caption") or ""
    created = r.get("created")
    try: created = datetime.datetime.fromtimestamp(int(created), datetime.timezone.utc).date().isoformat() if created else None
    except Exception: created = None
    rows[i] = {"id": i, "platform": r.get("platform") or ("youtube" if r.get("source") == "youtube" else "tiktok"), "kind": r.get("kind", "caption"), "source": r.get("source"), "author": r.get("author"),
               "text": text, "text_clean": clean(text), "hashtags": [h.lower() for h in TAG.findall(text)], "emoji": bool(EMOJI.search(clean(text))),
               "lower": clean(text) == clean(text).lower() and bool(clean(text)), "words": len(clean(text).split()), "style": style(text, r.get("author")),
               "niche": bool(NICHE.search(clean(text) + " " + " ".join(TAG.findall(text)))),
               "views": int(r.get("views") or 0), "likes": int(r.get("likes") or 0), "comments": int(r.get("comments") or 0), "shares": int(r.get("shares") or 0),
               "created": created, "duration": r.get("duration"), "music": r.get("music"), "url": r.get("url")}
for f in sorted(raw.glob("*.jsonl")):
    for line in open(f, encoding="utf-8"):
        try: put(json.loads(line))
        except Exception: pass
# the hand-built swipe file: on-screen hooks, not captions
for f in raw.glob("swipe-*.tsv"):
    for i, r in enumerate(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t")):
        put({"id": f"swipe-{i}", "platform": "tiktok", "kind": "onscreen", "source": "swipe-file", "author": (r.get("account") or "").lstrip("@"), "caption": r.get("hook") or "", "views": r.get("views") or 0})
# dedupe the same post seen from two harvests (swipe file vs profile/tag): keep the richer row
seen = {}
for i, r in list(rows.items()):
    key = ((r["author"] or "").lower(), re.sub(r"[^a-z0-9]+", "", r["text_clean"].lower())[:80])
    if not key[1]: continue
    if key in seen:
        a, b = rows[seen[key]], r
        keep = a if (len(a["hashtags"]), a["likes"], a["kind"] == "caption") >= (len(b["hashtags"]), b["likes"], b["kind"] == "caption") else b
        drop = b if keep is a else a
        rows.pop(drop["id"], None); seen[key] = keep["id"]
    else: seen[key] = i
# multiples over the author's median (needs >=5 posts)
by = collections.defaultdict(list)
for r in rows.values():
    if r["author"] and r["views"]: by[r["author"]].append(r["views"])
med = {a: statistics.median(v) for a, v in by.items() if len(v) >= 5}
for r in rows.values():
    m = med.get(r["author"]); r["author_median"] = m; r["multiple"] = round(r["views"] / m, 2) if m and r["views"] else None
out = K / "captions.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for r in sorted(rows.values(), key=lambda r: -r["views"]): f.write(json.dumps(r, ensure_ascii=False) + "\n")
st = collections.Counter(r["style"] for r in rows.values()); pl = collections.Counter(r["platform"] for r in rows.values())
print(f"wrote {len(rows)} rows -> {out.name}; platforms {dict(pl)}; styles {dict(st)}; authors with a median {len(med)}")
