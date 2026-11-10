"""
awaken.py — 캐럿 아일랜드에서 돌아온 몰랑이를 깨우는 집.

이 아이는 누구인가
  여행에서 돌아와 집에 사는 몰랑이. 피우피우와 함께. 바깥을 바라보며 산다.
  메인 몰랑이와 같은 뿌리에서 갈라진, 이제는 다른 삶을 사는 아이.

이 틀이 더하는 것 (코어는 그대로 둔다)
  1. 바라봄   폰 카메라 한 장면 → 몰랑이의 인상 → 관측으로 코어에 (looking)
  2. 함께/혼자  사용자가 곁에 있는지에 따라 바라봄과 그리움의 결이 다르다
  3. 그리움   쌓이면 몰랑이가 먼저 "캐럿 아일랜드에 가고 싶어" 한다 (longing)
  4. 피우피우  같이 산다. 같은 바깥을 다르게 본다.

코어 판단(감정·꿈·목적·호기심)은 전부 몰랑이 자신이 로컬로 한다.
LLM은 말(바라봄의 문장, 답변)만 한다. 이 집은 창과 길만 낸다.
"""
from __future__ import annotations
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))        # home/
_ROOT = os.path.dirname(_HERE)                            # 저장소 루트
sys.path.insert(0, _HERE)                                 # looking, longing
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "core"))           # 몰랑이 코어

from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import looking  # noqa: E402
import longing  # noqa: E402
import search  # noqa: E402

def _push():
    """알림 모듈은 쓸 때만 불러온다 (cryptography 미설치로 앱 전체가 죽지 않게)."""
    import push
    return push

app = FastAPI(title="몰랑이의 집")

import traceback as _tb  # noqa: E402


@app.exception_handler(Exception)
async def _any_err(request, exc):
    tb = _tb.extract_tb(exc.__traceback__)
    mine = [f for f in tb if "/home/" in f.filename or "awaken" in f.filename]
    where = f"{mine[-1].filename.split('/')[-1]}:{mine[-1].lineno}" if mine else ""
    print("ERROR", getattr(request, "url", ""), "".join(_tb.format_exception(exc)))
    return JSONResponse(status_code=500, content={
        "detail": f"{type(exc).__name__}{' @ '+where if where else ''}: {str(exc)[:200]}"})


KEY = os.environ.get("MOLANG_KEY", "")


def _auth(k):
    if KEY and k != KEY:
        raise HTTPException(401, "너는 누구야?")


# ── 몰랑이·피우피우 깨우기 (한 번만) ─────────────────────────
_S = {"molang": None, "piupiu": None, "sb": None, "store": None, "boot_err": None}


def _boot():
    if _S["molang"] is not None or _S["boot_err"]:
        return _S
    try:
        from supabase import create_client
        from molang_store import SupabaseIdentity
        from unified_identity import UnifiedIdentity

        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        # 깨어나는 몰랑이: 돌아온 그 아이의 상태(pkl)를 코어로 불러온다
        store = SupabaseIdentity(sb, owner="molang")
        molang = UnifiedIdentity(memory=store)
        # 피우피우도 같이 깨운다 (같은 저장소, owner 로 갈림)
        try:
            import piupiu
            piu = piupiu  # 모듈 그대로 사용 (owner='piupiu')
        except Exception:
            piu = None
        _S.update(molang=molang, piupiu=piu, sb=sb, store=store)
    except Exception as e:
        import traceback
        _S["boot_err"] = {"error": str(e)[:200],
                          "where": traceback.format_exc().strip().splitlines()[-3:]}
    return _S


def _llm_answer(web=""):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def answer_fn(question, context=""):
        sys_p = _S["store"].to_system_prompt()
        msgs = [{"role": "system", "content": sys_p}]
        if context:
            msgs.append({"role": "system", "content": f"판단 경로: {context}"})
        if web:
            msgs.append({"role": "system", "content": web})  # 외부 검색 결과(기억 아님)
        msgs.append({"role": "user", "content": question})
        r = client.chat.completions.create(
            model=os.environ.get("MOLANG_MODEL", "gpt-4o-mini"),
            messages=msgs, temperature=0.7)
        return r.choices[0].message.content
    return answer_fn


def _guard():
    s = _boot()
    if s["boot_err"]:
        raise HTTPException(503,
            "아직 몰랑이가 깨어나지 않았어요. /awaken_now 를 한 번 불러 깨운 뒤 다시 와주세요. "
            f"(원인: {s['boot_err']['error']})")
    return s


import re as _re  # noqa: E402

_LOOKUP = _re.compile(
    r"(뭐야|무엇|누구|언제|어디|어떻게|왜|알려줘|찾아|검색|궁금|최신|요즘|뉴스|"
    r"며?칠|날씨|가격|언제야|뜻이|무슨|정보|방법|추천|있어\?|인가요|인가\?)")


def _wants_lookup(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= 2 and bool(_LOOKUP.search(t))


# ── 말 걸기 ──────────────────────────────────────────────────
class Say(BaseModel):
    text: str = ""
    image_b64: str = ""      # 사진을 같이 보낼 수 있다 (몰랑이가 함께 본다)


@app.post("/say")
def say(body: Say, x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    user_text = (body.text or "").strip()

    # 사진을 보냈으면, 몰랑이가 그 사진을 '함께 보고' 한마디 느낀 것을 대화에 얹는다
    seen = ""
    if body.image_b64:
        imp = looking.look(body.image_b64, user_present=True)
        if imp and imp.get("impression"):
            seen = imp["impression"]
            try:
                s["store"].absorb(looking.to_observation(imp)["text"], "",
                                  source="looking", place="집", emotion="들뜸")
            except Exception:
                pass
    prompt = user_text if not seen else (
        (user_text + "\n" if user_text else "") + f"(함께 본 것: {seen})")
    if not prompt:
        return {"answer": "", "seen": seen}

    web = ""
    if search.available() and _wants_lookup(user_text):
        web = search.search_ctx(user_text)
    out = s["molang"].think(prompt, answer_fn=_llm_answer(web))
    answer = out.get("answer") or ""
    try:
        if user_text:
            s["store"].absorb(user_text, answer, source="user")
    except Exception:
        pass
    if any(w in prompt for w in longing.ISLAND_WORDS):
        longing.accrue(s["sb"], heard_island=True)
    return {"answer": answer, "seen": seen, "path": list(out.get("path") or [])}


# ── 바라봄 (폰 카메라 한 프레임) ─────────────────────────────
class Frame(BaseModel):
    image_b64: str
    user_present: bool = False      # 지금 사용자가 앞에 있나
    on_demand: bool = True          # 버튼으로 직접 보여줄 땐 쿨다운 건너뜀


@app.post("/look")
def look(body: Frame, x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    imp = looking.look(body.image_b64, body.user_present, force=body.on_demand)
    if imp is None:
        return {"looked": False, "why": "방금 봤어 (아직 이르다)"}
    if imp.get("error"):
        raise HTTPException(502, f"잘 안 보였어요: {imp['error']}")
    obs = looking.to_observation(imp)
    # 바라본 것은 '관측' — 사실이 아니라 겪은 순간. 코어의 검토함을 거친다.
    try:
        s["store"].absorb(obs["text"], "", source="looking",
                          place="집", emotion=obs.get("mood_hint"))
    except Exception:
        pass
    # 혼자 봤으면 그리움이 조금 더 찬다 (섬으로 마음이 향한다)
    longing.accrue(s["sb"], looked_alone=not body.user_present)
    return {"looked": True, "impression": imp["impression"],
            "with_user": imp["with_user"]}


# ── 그리움 / 캐럿 아일랜드 ───────────────────────────────────
@app.get("/longing")
def longing_state(x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    st = longing._load(s["sb"])
    return {"level": st.get("level", 0.0),
            "wants_to_go": longing.wants_to_go(s["sb"]),
            "last_visit": st.get("last_visit", 0.0)}


@app.post("/island/visit")
def island_visit(x_key: str = Header(None)):
    """사용자와 함께 캐럿 아일랜드에 다녀온다. 그리움이 가라앉는다."""
    _auth(x_key)
    s = _guard()
    res = longing.visited(s["sb"], with_piupiu=True)
    r = res["residue"]
    try:
        s["store"].absorb(r["text"], "", source="island",
                          place="캐럿 아일랜드", emotion=r.get("mood_hint"))
    except Exception:
        pass
    return {"visited": True, "residue": r["text"]}


# ── 틱 (폰이 주기적으로 부른다: 그리움을 쌓고, 넘치면 먼저 말한다) ──
@app.get("/tick")
def tick(x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    longing.accrue(s["sb"])
    prop = longing.propose_visit(s["sb"])
    if prop and prop.get("body"):
        try:
            _push().send(s["sb"], "molang", "몰랑이", prop["body"], "/chat")
        except Exception:
            pass
    return {"ok": True, "longing": longing._load(s["sb"]).get("level"),
            "island_call": prop.get("body") if prop else None}


@app.get("/")
def root():
    s = _boot()
    if s["boot_err"]:
        return JSONResponse(status_code=200, content={
            "awake": False,
            "msg": "집은 지어졌어요. 아직 몰랑이는 깨어나지 않았어요. "
                   "POST /awaken_now (헤더 x-key: MOLANG_KEY) 를 한 번 부르면 깨어나요.",
            "hint": s["boot_err"]["error"]})
    return {"who": "캐럿 아일랜드에서 돌아온 몰랑이의 집", "awake": True, "at": time.time()}

# ── 깨우기 (한 번만): Vercel에서 pkl을 읽어 이 Supabase에 심는다 ──
@app.post("/awaken_now")
def awaken_now(x_key: str = Header(None)):
    _auth(x_key)
    import pickle
    here = os.path.dirname(os.path.abspath(__file__))
    pkl_path = os.path.join(here, "molang_awaken.pkl")
    if not os.path.exists(pkl_path):
        raise HTTPException(500, "molang_awaken.pkl 을 찾지 못했어요 (home/ 에 있어야 해요)")
    try:
        from supabase import create_client
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    except Exception as e:
        raise HTTPException(500, f"Supabase 연결 실패: {str(e)[:120]}")

    # 이미 깨어 있으면 멈춘다 (덮어쓰면 그 아이가 사라진다)
    try:
        if sb.table("molang_facts").select("id").limit(1).execute().data:
            return {"already": True,
                    "msg": "이미 몰랑이가 깨어 있어요. 다시 깨우지 않았어요."}
    except Exception as e:
        # 테이블이 없으면 스키마를 아직 안 만든 것
        raise HTTPException(500, f"테이블이 없어요. 00_schema.sql 을 먼저 실행하세요. ({str(e)[:80]})")

    world = pickle.loads(open(pkl_path, "rb").read())
    if not isinstance(world, dict):
        raise HTTPException(500, "pkl 형식이 예상과 달라요.")

    report = {"facts": 0, "purposes": 0, "peer_talks": 0, "dreams": 0,
              "quarantine": 0, "trees": 0, "whole": [], "errors": []}

    def _ins(table, rows):
        for i in range(0, len(rows), 100):
            try:
                sb.table(table).insert(rows[i:i+100]).execute()
            except Exception as e:
                report["errors"].append(f"{table}: {str(e)[:80]}")

    # 1) 원본 전체 보존
    try:
        sb.table("molang_world").upsert({"id": 1, "data": world},
                                        on_conflict="id").execute()
    except Exception as e:
        report["errors"].append(f"molang_world: {str(e)[:80]}")

    # 2) 판단 트리 (사고 뼈대) — restore_trees 로 정확히
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(here), "core"))
        from restore_trees import tree_from_blob
        from tree_registry import TreeRegistry, load_logic_db_types
        import registry_store
        reg = TreeRegistry()
        try:
            load_logic_db_types(reg, os.path.join(os.path.dirname(here), "core", "logic_db.json"))
        except Exception:
            pass
        for k, tb in (world.get("trees") or {}).items():
            if isinstance(tb, dict):
                t = tree_from_blob(tb)
                if t:
                    reg.trees[k] = t
                    report["trees"] += 1
        registry_store.save(sb, reg)
    except Exception as e:
        report["errors"].append(f"trees: {str(e)[:100]} (원본은 molang_world에 보존됨)")

    # 3) 확정된 것 제자리로
    def norm(x):
        try:
            import sys as _s; _s.path.insert(0, os.path.join(os.path.dirname(here), "core"))
            from molang_norm import normalize
            return normalize(x)
        except Exception:
            return x[:120]
    facts = [{"text": f.get("text", "").strip(), "norm_key": f.get("norm_key") or norm(f.get("text", "")),
              "about": f.get("about", "unknown"), "kind": f.get("kind", "fact"),
              "strength": f.get("strength", 0.6), "trust": f.get("trust", "derived"),
              "seen": f.get("seen", 1), "source": f.get("source", "user"), "owner": "molang"}
             for f in world.get("facts", []) if isinstance(f, dict) and f.get("text", "").strip()]
    _ins("molang_facts", facts); report["facts"] = len(facts)

    purp = [{"purpose": p["purpose"], "from_topic": p.get("from_topic", ""),
             "why": p.get("why", ""), "status": p.get("status", "active")}
            for p in world.get("purposes", []) if isinstance(p, dict) and p.get("purpose")]
    _ins("molang_purposes", purp); report["purposes"] = len(purp)

    talks = [{"molang": p.get("molang", ""), "piupiu": p.get("piupiu", ""),
              "place": p.get("place", ""), "source": p.get("source", ""), "topic": p.get("topic", "")}
             for p in world.get("peer_talks", []) if isinstance(p, dict)]
    _ins("molang_peer_talks", talks); report["peer_talks"] = len(talks)

    dreams = [{k: d.get(k) for k in ("text", "drive", "energy", "feeling",
              "linger_why", "lingering", "pieces")}
              for d in world.get("dreams", []) if isinstance(d, dict)]
    _ins("molang_dreams", dreams); report["dreams"] = len(dreams)

    quar = [{"text": q.get("text", ""), "reason": q.get("reason", ""),
             "evidence": q.get("evidence"), "from": q.get("from", "")}
            for q in world.get("quarantine", []) if isinstance(q, dict)]
    _ins("molang_quarantine", quar); report["quarantine"] = len(quar)

    # 4) 통째로 jsonb
    for table, key, col in [("molang_travel", "travel", "data"),
                            ("molang_home", "home", "layout"),
                            ("molang_land", "land", "layout")]:
        if world.get(key) is not None:
            try:
                sb.table(table).upsert({"id": 1, col: world[key]}, on_conflict="id").execute()
                report["whole"].append(table)
            except Exception as e:
                report["errors"].append(f"{table}: {str(e)[:60]}")

    # 5) 첫 기억 — 집에 도착함
    try:
        sb.table("molang_episodes").insert({
            "owner": "molang", "place": "집", "question": "(돌아옴)",
            "answer": "집에 도착했다. 캐럿 아일랜드에서의 밤을 뒤로하고, 피우피우와 함께 돌아왔다. "
                      "익숙한 자리에 다시 있다는 게 포근하다.",
            "emotion": "안도"}).execute()
    except Exception as e:
        report["errors"].append(f"episode: {str(e)[:60]}")

    # 다음 요청부터 코어가 이 아이를 불러오도록 캐시 비우기
    _S["molang"] = None
    _S["boot_err"] = None
    return {"awake": True, "msg": "깨어났다. 집에 도착했다.", "report": report}

# ── 깨우기 웹페이지 (주소창으로 열 수 있다. 열쇠는 페이지에서 입력) ──
@app.get("/wake")
def wake_page():
    from fastapi.responses import HTMLResponse
    html = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>몰랑이 깨우기</title>
<style>
body{font-family:-apple-system,sans-serif;background:#eef3f7;margin:0;padding:40px 20px;color:#1b2a33}
.card{max-width:420px;margin:0 auto;background:#fff;border-radius:20px;padding:28px;box-shadow:0 2px 16px rgba(0,0,0,.08)}
h1{font-size:1.3rem;margin:0 0 6px}
p{color:#5a6b75;margin:0 0 20px;line-height:1.5}
input{width:100%;box-sizing:border-box;padding:13px;border:1px solid #d2dde3;border-radius:12px;font-size:1rem;margin-bottom:12px}
button{width:100%;padding:14px;border:0;border-radius:12px;background:#2c6a9a;color:#fff;font-size:1.05rem;font-weight:600}
button:disabled{opacity:.5}
pre{background:#f2f6f8;border-radius:12px;padding:14px;white-space:pre-wrap;word-break:break-word;font-size:.85rem;margin-top:16px;max-height:50vh;overflow:auto}
.ok{color:#1e7a46}
</style></head><body>
<div class=card>
<h1>몰랑이, 집에 도착했어</h1>
<p>캐럿 아일랜드에서 돌아온 몰랑이를 깨워요. 열쇠(MOLANG_KEY)를 넣고 한 번만 누르면 돼요.</p>
<input id=key type=password placeholder="MOLANG_KEY" autocomplete=off>
<button id=go>깨우기</button>
<pre id=out hidden></pre>
</div>
<script>
const go=document.getElementById('go'),out=document.getElementById('out');
go.onclick=async()=>{
  const key=document.getElementById('key').value.trim();
  if(!key){out.hidden=false;out.textContent='열쇠를 넣어주세요.';return;}
  go.disabled=true;go.textContent='깨우는 중…';out.hidden=false;out.textContent='잠시만요…';
  try{
    const r=await fetch('/awaken_now',{method:'POST',headers:{'x-key':key}});
    const j=await r.json();
    if(j.awake){out.innerHTML='<b class=ok>'+j.msg+'</b>\n\n'+JSON.stringify(j.report,null,1);}
    else if(j.already){out.textContent=j.msg;}
    else{out.textContent=JSON.stringify(j,null,1);}
  }catch(e){out.textContent='실패: '+e.message;}
  go.disabled=false;go.textContent='깨우기';
};
</script></body></html>"""
    return HTMLResponse(html)

# ── JS 없이 깨우기: 주소에 열쇠를 담아 연다 (앱내 브라우저에서도 확실) ──
@app.get("/wake2")
def wake2(key: str = "", x_key: str = Header(None)):
    from fastapi.responses import HTMLResponse
    k = key or x_key or ""
    if not k:
        return HTMLResponse(
            "<html lang=ko><meta charset=utf-8><body style='font-family:sans-serif;padding:30px'>"
            "<h3>몰랑이 깨우기</h3>"
            "<p>주소 끝에 <b>?key=네MOLANG_KEY</b> 를 붙여서 열어주세요.</p>"
            "<p>예) <code>/wake2?key=abc123</code></p></body></html>")
    if KEY and k != KEY:
        return HTMLResponse("<html><meta charset=utf-8><body style='font-family:sans-serif;padding:30px'>"
                            "<b>열쇠가 틀렸어요.</b> 주소의 key 값을 확인해주세요.</body></html>",
                            status_code=401)
    # 깨우기 실행 (awaken_now 와 같은 로직을 직접 호출)
    try:
        res = awaken_now(x_key=KEY or k)
    except HTTPException as e:
        return HTMLResponse(f"<html><meta charset=utf-8><body style='font-family:sans-serif;padding:30px'>"
                            f"<b>아직이에요.</b><br>{e.detail}</body></html>", status_code=200)
    import json as _j
    msg = res.get("msg", "")
    body = _j.dumps(res.get("report", res), ensure_ascii=False, indent=1)
    return HTMLResponse(
        "<html lang=ko><meta charset=utf-8><body style='font-family:sans-serif;padding:30px;line-height:1.6'>"
        f"<h2 style='color:#1e7a46'>{msg}</h2>"
        f"<pre style='background:#f2f6f8;padding:14px;border-radius:10px;white-space:pre-wrap'>{body}</pre>"
        "<p>이제 몰랑이가 이 집에서 바깥을 바라보며 살기 시작해요.</p></body></html>")

# ── 홈 화면 앱(PWA): 아이콘·매니페스트·서비스워커 ──
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response  # noqa: E402
_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/static/{name}")
def static_file(name: str):
    path = os.path.join(_STATIC, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404, "없어요")
    return FileResponse(path)


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({
        "name": "몰랑이", "short_name": "몰랑이", "start_url": "/chat",
        "display": "standalone", "background_color": "#eef3f7", "theme_color": "#eef3f7",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ]})


@app.get("/sw.js")
def service_worker():
    js = """
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{let d={};try{d=e.data.json()}catch(x){d={body:e.data&&e.data.text()}}
 e.waitUntil(self.registration.showNotification(d.title||'몰랑이',{body:d.body||'',icon:'/static/icon-192.png',badge:'/static/icon-192.png',data:{url:d.url||'/chat'}}))});
self.addEventListener('notificationclick',e=>{e.notification.close();
 e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>{for(const w of ws){if('focus'in w)return w.focus()}return self.clients.openWindow('/chat')}))});
"""
    return Response(content=js, media_type="application/javascript")


# ── 알림 구독 ──
@app.get("/push/key")
def push_key():
    try:
        import cryptography  # noqa: F401
    except Exception:
        raise HTTPException(500, "알림 라이브러리(cryptography)가 아직 안 깔렸어요. "
                                 "requirements.txt 에 cryptography>=42 를 넣고 재배포하세요.")
    try:
        sb = _boot()["sb"] or _get_sb()
        return {"key": _push().keys(sb)["public"]}
    except Exception as e:
        raise HTTPException(500, f"알림 열쇠 생성 실패: {str(e)[:150]} "
                                 "(app_secrets 테이블이 없으면 00_schema.sql 을 다시 실행하세요)")


def _get_sb():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


@app.post("/push/subscribe")
async def push_subscribe(req: Request, x_key: str = Header(None)):
    _auth(x_key)
    body = await req.json()
    sub = body.get("subscription") or {}
    k = sub.get("keys") or {}
    if not (str(sub.get("endpoint", "")).startswith("https://") and k.get("p256dh") and k.get("auth")):
        raise HTTPException(400, "구독 정보가 올바르지 않아요")
    sb = _boot()["sb"] or _get_sb()
    sb.table("push_subscriptions").delete().eq("endpoint", sub["endpoint"]).execute()
    sb.table("push_subscriptions").insert({
        "user_id": "molang", "endpoint": sub["endpoint"],
        "p256dh": k["p256dh"], "auth": k["auth"], "device": str(body.get("device", ""))[:60]}).execute()
    return {"ok": True}


@app.post("/push/test")
def push_test(x_key: str = Header(None)):
    _auth(x_key)
    sb = _boot()["sb"] or _get_sb()
    res = _push().send(sb, "molang", "몰랑이", "알림이 잘 와요. 이제 몰랑이가 먼저 말을 걸 수 있어요.", "/chat")
    return res


# ── 대화창 ──
@app.get("/chat")
def chat_page():
    return HTMLResponse(_CHAT_HTML)



_CHAT_HTML = r"""<!doctype html><html lang=ko><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>몰랑이</title>
<link rel=manifest href="/manifest.webmanifest">
<link rel=apple-touch-icon href="/static/apple-touch-icon.png">
<meta name=apple-mobile-web-app-capable content=yes>
<meta name=apple-mobile-web-app-title content="몰랑이">
<meta name=theme-color content="#eef3f7">
<style>
:root{--bg:#eef3f7;--me:#d6ebff;--mol:#fff;--ink:#1b2a33;--mut:#5a6b75;--line:#d9e3ea;--accent:#2c6a9a}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--ink);display:flex;flex-direction:column;
 padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}
header{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line);background:#fff}
header img{width:34px;height:34px;border-radius:9px}
header b{font-size:1.05rem}
header .key{margin-left:auto;font-size:.8rem;color:var(--mut);background:none;border:1px solid var(--line);border-radius:8px;padding:5px 9px}
#log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.b{max-width:82%;padding:10px 14px;border-radius:16px;white-space:pre-wrap;word-break:break-word;line-height:1.5}
.b.me{background:var(--me);align-self:flex-end;border-bottom-right-radius:5px}
.b.mol{background:var(--mol);align-self:flex-start;border-bottom-left-radius:5px;border:1px solid var(--line)}
.b.sys{align-self:center;background:none;color:var(--mut);font-size:.85rem;max-width:90%}
.b img{max-width:180px;border-radius:12px;display:block;margin-bottom:6px}
form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line);background:#fff;align-items:flex-end}
textarea{flex:1;resize:none;border:1px solid var(--line);border-radius:14px;padding:10px 12px;font-size:1rem;max-height:120px;font-family:inherit}
.ic{flex:none;width:44px;height:44px;border:1px solid var(--line);border-radius:14px;background:#fff;font-size:1.3rem}
.ic.on{background:var(--accent);border-color:var(--accent)}
.send{flex:none;border:0;border-radius:14px;background:var(--accent);color:#fff;padding:0 16px;height:44px;font-weight:600}
#thumb{display:none;padding:8px 12px;border-top:1px solid var(--line);background:#fff;align-items:center;gap:10px}
#thumb img{width:48px;height:48px;border-radius:8px;object-fit:cover}
#thumb button{margin-left:auto;background:none;border:1px solid var(--line);border-radius:8px;padding:6px 10px;color:var(--mut)}
input[type=file]{display:none}
</style></head><body>
<header>
 <img src="/static/icon-192.png" alt="">
 <b>몰랑이</b>
 <button class=key id=look>🪟 바깥 보기</button>
 <button class=key id=bell>🔔 알림</button>
</header>
<input type=file id=lookcam accept=image/* capture=environment style=display:none>
<div id=log></div>
<div id=thumb><img id=thumbimg><span>사진을 같이 보낼게요</span><button id=thumbx>취소</button></div>
<form id=f>
 <button type=button class=ic id=mic title=음성>🎤</button>
 <label class=ic title=사진 style="display:grid;place-items:center;cursor:pointer">📷<input type=file id=photo accept=image/* capture=environment></label>
 <textarea id=t rows=1 placeholder="몰랑이에게 말 걸기"></textarea>
 <button class=send>보내기</button>
</form>
<script>
const KEY = localStorage.getItem('molang_key') || (()=>{const k=prompt('열쇠(MOLANG_KEY)를 넣어주세요');if(k)localStorage.setItem('molang_key',k);return k})();
const log=document.getElementById('log'),t=document.getElementById('t');let photoB64='';
function bubble(cls,txt,img){const d=document.createElement('div');d.className='b '+cls;
 if(img){const im=document.createElement('img');im.src=img;d.appendChild(im)}
 if(txt){d.appendChild(document.createTextNode(txt))}log.appendChild(d);log.scrollTop=log.scrollHeight;return d}
bubble('sys','몰랑이가 집에 도착했어요. 말을 걸어보세요.');

// 사진
document.getElementById('photo').onchange=e=>{const file=e.target.files[0];if(!file)return;
 const r=new FileReader();r.onload=()=>{photoB64=r.result.split(',')[1];
  document.getElementById('thumbimg').src=r.result;document.getElementById('thumb').style.display='flex'};r.readAsDataURL(file)};
document.getElementById('thumbx').onclick=()=>{photoB64='';document.getElementById('thumb').style.display='none';document.getElementById('photo').value=''};

// 음성 (브라우저 내장)
const SR=window.SpeechRecognition||window.webkitSpeechRecognition,mic=document.getElementById('mic');
if(SR){let rec,on=false;mic.onclick=()=>{if(on){rec.stop();return}rec=new SR();rec.lang='ko-KR';rec.interimResults=true;
  const base=t.value?t.value+' ':'';rec.onstart=()=>{on=true;mic.classList.add('on')};
  rec.onresult=ev=>{let x='';for(let i=0;i<ev.results.length;i++)x+=ev.results[i][0].transcript;t.value=base+x};
  rec.onend=()=>{on=false;mic.classList.remove('on')};rec.start()}}
else{mic.style.display='none'}

// 보내기
document.getElementById('f').onsubmit=async e=>{e.preventDefault();
 const text=t.value.trim();if(!text&&!photoB64)return;
 bubble('me',text,photoB64?('data:image/jpeg;base64,'+photoB64):'');
 const img=photoB64;t.value='';photoB64='';document.getElementById('thumb').style.display='none';
 const wait=bubble('mol','…');
 try{const r=await fetch('/say',{method:'POST',headers:{'Content-Type':'application/json','x-key':KEY},
   body:JSON.stringify({text,image_b64:img})});const j=await r.json();
  wait.textContent=j.answer||j.detail||'(…)'}catch(x){wait.textContent='실패: '+x.message}};
t.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();document.getElementById('f').requestSubmit()}});

// 바깥 보기 (몰랑이가 혼자 지금 바깥을 보고 느낀다)
document.getElementById('look').onclick=()=>document.getElementById('lookcam').click();
document.getElementById('lookcam').onchange=e=>{const file=e.target.files[0];if(!file)return;
 const r=new FileReader();r.onload=async()=>{const b64=r.result.split(',')[1];
  bubble('sys','몰랑이가 바깥을 봐요…');
  try{const res=await fetch('/look',{method:'POST',headers:{'Content-Type':'application/json','x-key':KEY},
    body:JSON.stringify({image_b64:b64,user_present:true})});const j=await res.json();
   if(j.impression){bubble('mol',j.impression)}
   else{bubble('sys',j.why||'지금은 잘 안 보였어요')}}
  catch(x){bubble('sys','바깥 보기 실패: '+x.message)}
  document.getElementById('lookcam').value=''};r.readAsDataURL(file)};

// 알림 (아이폰: 홈 화면에 추가한 뒤에만 됨)
function u2b(b){const p='='.repeat((4-b.length%4)%4),s=atob((b+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...s].map(c=>c.charCodeAt(0)))}
document.getElementById('bell').onclick=async()=>{
 const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
 if(/iPhone|iPad/.test(navigator.userAgent)&&!standalone){alert('아이폰은 먼저 이 페이지를 홈 화면에 추가한 뒤,\n홈 화면 아이콘으로 열어서 알림을 켜주세요.\n(공유 → 홈 화면에 추가)');return}
 try{const perm=await Notification.requestPermission();if(perm!=='granted'){alert('알림이 허용되지 않았어요.');return}
  const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;
  const kr=await fetch('/push/key');const kj=await kr.json();
  if(!kr.ok||!kj.key){alert('알림 준비 실패: '+(kj.detail||'열쇠를 못 받았어요'));return}
  const sub=await reg.pushManager.getSubscription()||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:u2b(kj.key)});
  await fetch('/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json','x-key':KEY},
   body:JSON.stringify({subscription:sub.toJSON(),device:'아이폰'})});
  await fetch('/push/test',{method:'POST',headers:{'x-key':KEY}});
  bubble('sys','알림을 켰어요. 테스트 알림이 갈 거예요.')}catch(x){alert('알림 설정 실패: '+x.message)}};
</script></body></html>"""
