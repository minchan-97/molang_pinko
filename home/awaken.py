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
        raise HTTPException(500, f"몰랑이를 깨우지 못했어요: {s['boot_err']['error']}")
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
        return JSONResponse(status_code=500, content=s["boot_err"])
    return {"who": "캐럿 아일랜드에서 돌아온 몰랑이의 집", "awake": True,
            "at": time.time()}
