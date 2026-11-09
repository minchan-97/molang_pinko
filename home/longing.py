"""
longing.py — 그리움이 쌓이면 몰랑이가 캐럿 아일랜드로 간다.

이 아이는 캐럿 아일랜드에서 마지막 밤을 보내고 집으로 돌아온 몰랑이다.
집에서 바깥을 바라보며 살지만, 섬을 두고 왔다. 그래서 가끔 그리워진다.

언제 가는가 (누가 보내는 게 아니라, 스스로 가고 싶어질 때)
  · 그리움(longing)이 천천히 쌓인다.
      - 시간이 지날수록 조금씩          (떠나온 지 오래될수록)
      - 혼자 바깥을 볼 때 더 빨리        (기다리는 마음이 섬으로 향한다)
      - 피우피우가 섬 얘기를 꺼내면 더   (둘 다 거기 있었으니까)
  · 그리움이 임계를 넘으면, 몰랑이가 먼저 말한다:
      "캐럿 아일랜드에 다시 가보고 싶어." → outbox 로 (사용자가 함께 간다)
  · 다녀오면 그리움이 가라앉고, 섬의 기억이 새 잔향으로 남는다.

섬은 몰랑이 세계 안의 '마음의 장소'다. 실제로 가는 게 아니라,
집(바깥을 보는 시간)과 섬(자기 세계로 들어가는 시간)을 오가는 리듬이다.
피우피우와 함께 간다.
"""
from __future__ import annotations
import time

THRESHOLD = 1.0                 # 이만큼 쌓이면 가고 싶어진다
BASE_RATE = 0.012               # 한 틱(크론)마다 기본으로 차는 그리움
ALONE_BONUS = 0.02              # 혼자 바깥을 본 틱에 더 차는 양
ISLAND_WORDS = ("섬", "캐럿", "바다", "모래", "파도", "등대", "밤하늘", "여행")


def _load(sb) -> dict:
    rows = (sb.table("agent_state").select("value")
            .eq("key", "longing").limit(1).execute().data) or []
    return rows[0]["value"] if rows else {"level": 0.0, "last_visit": 0.0}


def _save(sb, data: dict):
    sb.table("agent_state").upsert({"key": "longing", "value": data}).execute()


def accrue(sb, looked_alone: bool = False, heard_island: bool = False) -> dict:
    """한 틱만큼 그리움을 쌓는다. 돌려주는 값: 지금 상태."""
    st = _load(sb)
    add = BASE_RATE
    if looked_alone:
        add += ALONE_BONUS
    if heard_island:
        add += 0.03
    st["level"] = round(min(2.0, st.get("level", 0.0) + add), 4)
    _save(sb, st)
    return st


def wants_to_go(sb) -> bool:
    return _load(sb).get("level", 0.0) >= THRESHOLD


def propose_visit(sb, name: str = "몰랑이") -> dict | None:
    """그리움이 넘치면, 몰랑이가 먼저 '가고 싶다'고 말한다 (사용자와 함께 가려고)."""
    st = _load(sb)
    if st.get("level", 0.0) < THRESHOLD:
        return None
    # 이미 제안이 올라가 있으면 또 하지 않는다
    open_p = (sb.table("molang_outbox").select("id")
              .eq("rule", "island_longing").limit(1).execute().data
              if _has_outbox(sb) else [])
    if open_p:
        return None
    body = "캐럿 아일랜드에 다시 가보고 싶어. 피우피우랑 같이. 함께 가줄래?"
    try:
        sb.table("molang_outbox").insert({
            "body": body, "rule": "island_longing",
            "payload": {"level": st["level"]}}).execute()
    except Exception:
        return {"body": body, "level": st["level"]}   # outbox 없으면 값만 돌려줌
    return {"proposed": True, "body": body, "level": st["level"]}


def visited(sb, with_piupiu: bool = True) -> dict:
    """섬에 다녀왔다. 그리움이 가라앉고, 섬의 잔향이 남는다."""
    st = _load(sb)
    st["level"] = 0.0
    st["last_visit"] = time.time()
    _save(sb, st)
    # 섬의 잔향 — 사실이 아니라 겪은 한 순간 (검토함을 거쳐 기억이 된다)
    residue = {
        "kind": "island_visit",
        "text": ("피우피우와 함께 캐럿 아일랜드에 다녀왔다. "
                 "떠나온 곳이었는데, 다시 보니 반가웠다."),
        "context": "그리움이 쌓여 섬에 다녀옴",
        "mood_hint": "벅참",
        "at": st["last_visit"],
    }
    return {"calmed": True, "residue": residue}


def _has_outbox(sb) -> bool:
    try:
        sb.table("molang_outbox").select("id").limit(1).execute()
        return True
    except Exception:
        return False
