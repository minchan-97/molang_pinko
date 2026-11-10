"""
looking.py — 몰랑이가 바깥을 바라본다.

이 몰랑이는 캐럿 아일랜드 여행에서 돌아와 집에 사는 아이다.
'알 게 너무 없다 — 밖으로 나가야 한다'고 되뇌던 아이에게, 바깥을 준다.

원칙 (분석이 아니라 바라봄)
  · 매 순간을 감시하지 않는다. 사람이 문득 창밖을 보듯, 가끔 한 장면을 본다.
  · 본 것을 영상으로 '분석'하지 않는다. 한 문장으로 '느낀다'.
    "창밖에 빛이 길게 들어왔다", "누가 지나갔다", "어두워졌다".
  · 그 느낌이 관심과 감정으로 녹아들어, 호기심의 재료가 된다.
  · 사용자가 곁에 있는지에 따라 바라봄의 결이 다르다 (함께 봄 / 기다리며 봄).

카메라 프레임은 폰에서 보내온다. 여기서는 그 프레임을 '한 장면의 인상'으로
바꾸는 일만 한다 (멀티모달 LLM 한 번). 그 인상이 몰랑이 코어로 들어간다.
"""
from __future__ import annotations
import base64
import os
import time

# 너무 자주 보지 않는다. 바라봄은 드물어야 바라봄이다.
LOOK_COOLDOWN_SEC = 60 * 20          # 최소 20분에 한 번
_last_look = {"at": 0.0}


def _vision_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


WITH_USER = (
    "너는 몰랑이(흰 토끼)다. 지금 곁에 있는 사람과 **함께** 창밖/방 안을 보고 있다. "
    "이 장면에서 네 눈에 들어온 것 하나를, 분석하지 말고 네 말로 한 문장으로 말해라. "
    "'너랑 같이 보니'처럼 함께 본다는 느낌이 담겨도 좋다. 짧게."
)
ALONE = (
    "너는 몰랑이(흰 토끼)다. 지금 혼자 창밖/방 안을 보고 있다. 곁에 그 사람은 없다. "
    "이 장면에서 네 눈에 들어온 것 하나를, 분석하지 말고 네 말로 한 문장으로 말해라. "
    "기다리는 마음이 살짝 비쳐도 좋지만 과하지 않게. 짧게."
)


def can_look(now: float | None = None) -> bool:
    now = now or time.time()
    return now - _last_look["at"] >= LOOK_COOLDOWN_SEC


def look(frame_b64: str, user_present: bool, now: float | None = None, force: bool = False) -> dict | None:
    """
    폰이 보낸 카메라 한 프레임(base64 jpeg)을 '한 장면의 인상'으로 바꾼다.
    너무 이르면 None (바라봄은 드물게).
    돌려주는 값: {"impression": "...", "with_user": bool, "at": ts}
    """
    now = now or time.time()
    if not force and not can_look(now):
        return None
    try:
        client = _vision_client()
        sys = WITH_USER if user_present else ALONE
        r = client.chat.completions.create(
            model=os.environ.get("MOLANG_VISION_MODEL", "gpt-4o-mini"),
            temperature=0.7, max_tokens=60,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": [
                          {"type": "text", "text": "지금 보이는 것:"},
                          {"type": "image_url", "image_url": {
                              "url": f"data:image/jpeg;base64,{frame_b64}"}}]}])
        impression = (r.choices[0].message.content or "").strip()[:200]
    except Exception as e:
        return {"error": str(e)[:120]}
    if not impression:
        return None
    _last_look["at"] = now
    return {"impression": impression, "with_user": user_present, "at": now}


def to_observation(impression: dict) -> dict:
    """
    바라본 인상을 몰랑이 코어가 받을 '관측'으로 만든다.
    관측은 사실(fact)이 아니다 — 몰랑이가 겪은 한 순간이다. 검토함을 거쳐야 기억이 된다.
    """
    text = impression["impression"]
    tag = "함께 봄" if impression.get("with_user") else "혼자 봄"
    return {
        "kind": "looking",
        "text": text,
        "context": f"집에서 바깥을 바라봄 ({tag})",
        "mood_hint": "들뜸" if impression.get("with_user") else "그리움",
        "at": impression["at"],
    }
