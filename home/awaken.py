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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import looking  # noqa: E402
import longing  # noqa: E402

app = FastAPI(title="몰랑이의 집")

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


def _llm_answer():
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def answer_fn(question, context=""):
        sys_p = _S["store"].to_system_prompt()
        msgs = [{"role": "system", "content": sys_p}]
        if context:
            msgs.append({"role": "system", "content": f"판단 경로: {context}"})
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


# ── 말 걸기 ──────────────────────────────────────────────────
class Say(BaseModel):
    text: str


@app.post("/say")
def say(body: Say, x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    out = s["molang"].think(body.text.strip(), answer_fn=_llm_answer())
    answer = out.get("answer") or ""
    try:
        s["store"].absorb(body.text, answer, source="user")
    except Exception:
        pass
    # 섬 얘기가 나오면 그리움이 조금 더 찬다
    heard = any(w in body.text for w in longing.ISLAND_WORDS)
    if heard:
        longing.accrue(s["sb"], heard_island=True)
    return {"answer": answer, "path": list(out.get("path") or [])}


# ── 바라봄 (폰 카메라 한 프레임) ─────────────────────────────
class Frame(BaseModel):
    image_b64: str
    user_present: bool = False      # 지금 사용자가 앞에 있나


@app.post("/look")
def look(body: Frame, x_key: str = Header(None)):
    _auth(x_key)
    s = _guard()
    imp = looking.look(body.image_b64, body.user_present)
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
