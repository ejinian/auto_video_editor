import json, time, urllib.request, urllib.parse, subprocess, sys, re, collections
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
OUT="raw/tiktok_tags.jsonl"; rows={}
def get(u, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40) as f: return json.load(f)
        except Exception as e:
            err=e; time.sleep(2+2*i)
    print("   failed", u[:80], err); return {}
def add(v, source):
    vid=str(v.get("video_id") or v.get("id") or "")
    if not vid or vid in rows: return 0
    au=v.get("author") or {}
    rows[vid]={"platform":"tiktok","source":source,"id":vid,"author":au.get("unique_id"),"caption":v.get("title") or "","views":int(v.get("play_count") or 0),"likes":int(v.get("digg_count") or 0),"comments":int(v.get("comment_count") or 0),"shares":int(v.get("share_count") or 0),"created":v.get("create_time"),"duration":v.get("duration"),"is_photo":bool(v.get("images")),"music":(v.get("music_info") or {}).get("title"),"url":f"https://www.tiktok.com/@{au.get('unique_id')}/video/{vid}"}
    return 1
TAGS=["claudecode","claudeai","claude","anthropic","vibecoding","vibecoder","vibecode","cursorai","cursor","codingmemes","programmerhumor","programmermemes","softwareengineer","softwareengineering","softwaredeveloper","techtok","buildinpublic","saas","indiehacker","codinglife","developerlife","coding","programming","computerscience","aicoding","opus","claudeopus","techbro","startup","founder"]
for tag in TAGS:
    info=get(f"https://www.tikwm.com/api/challenge/info?challenge_name={tag}"); time.sleep(1.1)
    cid=((info.get("data") or {}).get("id"))
    if not cid: print(f"#{tag}: no id"); continue
    n=0; cursor=0
    for page in range(4):
        d=get(f"https://www.tikwm.com/api/challenge/posts?challenge_id={cid}&count=50&cursor={cursor}"); time.sleep(1.2)
        data=d.get("data") or {}; vids=data.get("videos") or []
        n+=sum(add(v,f"tag:{tag}") for v in vids)
        if not data.get("hasMore") or not vids: break
        cursor=data.get("cursor") or cursor
    print(f"#{tag}: +{n} (total {len(rows)})", flush=True)
    with open(OUT,"w") as f:
        for r in rows.values(): f.write(json.dumps(r, ensure_ascii=False)+"\n")
print("TAG PHASE DONE", len(rows))
