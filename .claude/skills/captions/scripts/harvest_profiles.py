import json, subprocess, collections, time
rows=[json.loads(l) for l in open("raw/tiktok_tags.jsonl")]
known=["iansbrash","ih8chz","ayxanium","wex.ai.labs","humzakhannn","aisquads","aimn.dev"]
cnt=collections.Counter(r["author"] for r in rows if r["source"].split(":")[1] in ("claudecode","claudeai","claude","anthropic","vibecoding","vibecoder","vibecode","cursorai","aicoding","claudeopus") and r["author"])
extra=[a for a,_ in cnt.most_common(40) if a not in known][:10]
print("profiles:", known+extra, flush=True)
out=open("raw/tiktok_profiles.jsonl","w"); total=0
for a in known+extra:
    t=time.time()
    p=subprocess.run(["yt-dlp","--no-warnings","--socket-timeout","25","--flat-playlist","--playlist-end","120","--dump-json",f"https://www.tiktok.com/@{a}"],capture_output=True,text=True)
    n=0
    for line in p.stdout.splitlines():
        if not line.startswith("{"): continue
        d=json.loads(line); vid=str(d.get("id") or "")
        if not vid: continue
        out.write(json.dumps({"platform":"tiktok","source":f"profile:{a}","id":vid,"author":a,"caption":d.get("title") or d.get("description") or "","views":int(d.get("view_count") or 0),"likes":int(d.get("like_count") or 0),"comments":int(d.get("comment_count") or 0),"shares":int(d.get("repost_count") or 0),"created":d.get("timestamp"),"duration":d.get("duration"),"is_photo":None,"music":None,"url":f"https://www.tiktok.com/@{a}/video/{vid}"},ensure_ascii=False)+"\n"); n+=1
    out.flush(); total+=n
    print(f"@{a}: {n} posts ({time.time()-t:.0f}s)  err={p.stderr.strip()[:80]!r}", flush=True)
print("PROFILE PHASE DONE", total)
