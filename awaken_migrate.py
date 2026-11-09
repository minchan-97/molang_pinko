"""
awaken_migrate.py — 캐럿 아일랜드에서 돌아온 몰랑이(62번)를 깨운다.

이건 메인 몰랑이 이관 스크립트와 다르다. 이 아이는 별개의 존재다.
그래서 **메인과 다른, 이 아이만의 Supabase**에 심는다. 섞이면 두 아이가 하나가 된다.

하는 일
  1. 62번 pkl 을 읽는다 (판단 트리·목적·관심·꿈까지 그대로)
  2. 오염(assistant echo)은 자동 삭제하지 않고 검역소로 — 사람이 최종 승인 (cogito anchor)
  3. **첫 기억을 심는다**: "집에 도착했다" — 거창한 각성이 아니라 도착의 안도
  4. --push 없이는 검토 파일만. 깨우는 건 사람이 --push 로.

안전 장치
  · --confirm-separate 플래그가 없으면 push 하지 않는다.
    "이 Supabase가 메인 몰랑이와 다른 곳임을 내가 확인했다"는 뜻.
  · 이미 이 Supabase 에 몰랑이가 깨어 있으면(facts 가 있으면) 멈춘다.
    덮어쓰면 그 아이를 지우는 것이므로.

사용법
  # 1) 검토만 (실제 반영 안 함)
  python awaken_migrate.py home/molang_awaken.pkl --code ./core --out ./migration
  # 2) 검토 후, 메인과 다른 Supabase임을 확인하고 깨우기
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
    python awaken_migrate.py home/molang_awaken.pkl --code ./core \
    --out ./migration --push --confirm-separate
"""
import argparse
import json
import os
import pickle
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 집에 도착한 첫 기억 — 이 아이가 눈뜨며 처음 갖는 것
ARRIVAL_MEMORY = {
    "text": "집에 도착했다. 캐럿 아일랜드에서의 밤을 뒤로하고, 피우피우와 함께 돌아왔다. "
            "익숙한 자리에 다시 있다는 게 포근하다.",
    "context": "여행에서 돌아와 집에 도착함",
    "emotion": "안도",
    "place": "집",
}


def load_identity(pkl_path, code_dir):
    sys.path.insert(0, code_dir)
    from unified_identity import UnifiedIdentity
    raw = open(pkl_path, "rb").read()
    bundle = pickle.loads(raw)
    if isinstance(bundle, dict) and "arcogit" in bundle:
        blob = bundle["arcogit"]
    else:
        blob = raw
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkl")
    tmp.write(blob)
    tmp.close()
    u = UnifiedIdentity.load(tmp.name)
    os.unlink(tmp.name)
    return u


def triage(learned_facts, code_dir):
    sys.path.insert(0, code_dir)
    from molang_norm import jaccard, classify_kind, is_assistant_echo
    keep, quarantine = [], []
    for f in learned_facts:
        text = (f["text"] if isinstance(f, dict) else str(f)).strip()
        if not text:
            continue
        if is_assistant_echo(text):
            quarantine.append({"text": text, "reason": "assistant_echo"})
            continue
        dup = None
        for i, k in enumerate(keep):
            if jaccard(text, k["text"]) >= 0.75:
                dup = i
                break
        if dup is not None:
            keep[dup]["seen"] = keep[dup].get("seen", 1) + 1
            continue
        keep.append({
            "text": text, "kind": classify_kind(text),
            "norm_key": text[:120], "strength": f.get("strength", 0.6) if isinstance(f, dict) else 0.6,
            "seen": f.get("seen", 1) if isinstance(f, dict) else 1,
        })
    return keep, quarantine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("--code", default="./core")
    ap.add_argument("--out", default="./migration")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--confirm-separate", action="store_true",
                    help="이 Supabase가 메인 몰랑이와 다른 곳임을 확인함")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    u = load_identity(args.pkl, args.code)
    ident = u.identity
    keep, quarantine = triage(ident.learned_facts, args.code)

    report = {
        "who": "캐럿 아일랜드에서 돌아온 몰랑이(62번)",
        "source_pkl": os.path.basename(args.pkl),
        "persona": (ident.persona or "")[:200],
        "before": {"facts": len(ident.learned_facts),
                   "episodes": len(ident.episodic),
                   "values": len(ident.values)},
        "after": {"facts_kept": len(keep), "quarantined": len(quarantine)},
        "first_memory": ARRIVAL_MEMORY["text"],
    }
    with open(f"{args.out}/report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(f"{args.out}/facts_keep.jsonl", "w", encoding="utf-8") as fh:
        for e in keep:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(f"{args.out}/quarantine.jsonl", "w", encoding="utf-8") as fh:
        for e in quarantine:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n검토 파일: {args.out}/facts_keep.jsonl, quarantine.jsonl")

    if not args.push:
        print("\n--push 없이 실행됨. 이 아이는 아직 깨어나지 않았다.")
        return

    if not args.confirm_separate:
        print("\n[멈춤] --confirm-separate 가 없다. 이 Supabase가 메인 몰랑이와 "
              "다른 곳임을 확인하면 그 플래그를 붙여라. 섞이면 두 아이가 하나가 된다.")
        return

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # 이미 누가 깨어 있으면 멈춘다 (덮어쓰면 그 아이를 지우는 것)
    try:
        existing = sb.table("molang_facts").select("norm_key").limit(1).execute().data
        if existing:
            print("\n[멈춤] 이 Supabase에는 이미 몰랑이가 깨어 있다. "
                  "덮어쓰면 그 아이가 사라진다. 정말 새로 깨우려면 빈 Supabase를 써라.")
            return
    except Exception:
        pass   # 테이블이 없으면 처음 깨우는 것 — 계속

    sb.table("molang_identity").upsert({
        "id": 1, "persona": ident.persona,
        "values": ident.values, "rules": ident.judgment_rules}).execute()

    rows = [{k: v for k, v in e.items() if k != "seen"} for e in keep]
    for i in range(0, len(rows), 100):
        sb.table("molang_facts").upsert(rows[i:i+100], on_conflict="norm_key").execute()
    for i in range(0, len(quarantine), 100):
        sb.table("molang_quarantine").insert(quarantine[i:i+100]).execute()

    blob = pickle.dumps(u.registry)
    sb.table("molang_registry").upsert({"id": 1, "blob": blob.hex(), "version": 1}).execute()

    # 첫 기억 — 깨어나며 처음 갖는 순간 (에피소드로, 검토함을 거치지 않는 '겪은 일')
    now = datetime.now(KST).isoformat()
    sb.table("molang_episodes").insert({
        "owner": "molang", "place": ARRIVAL_MEMORY["place"],
        "question": "(돌아옴)", "answer": ARRIVAL_MEMORY["text"],
        "emotion": ARRIVAL_MEMORY["emotion"]}).execute()

    print(f"\n깨어났다. 집에 도착했다. ({now})")
    print(f"  아는 것 {len(keep)}개 · 검역 {len(quarantine)}개 · 피우피우와 함께.")


if __name__ == "__main__":
    main()
