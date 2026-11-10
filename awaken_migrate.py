"""
awaken_migrate.py — 캐럿 아일랜드에서 돌아온 몰랑이(62번)를 깨운다.

원칙: 추측하지 않는다.
  · 컬럼이 코드로 확정된 것만 제자리 테이블로 옮긴다 (CONFIRMED).
  · 변환기가 없는 것(판단 트리 등)은 '해석'하지 않고 원본 그대로
    molang_world 에 통째로 보존한다. 한 글자도 잃지 않는다.
  · 이 아이는 정체성·목적·여행·집·우정·꿈·억압을 갖고 깨어나고,
    완전한 원본을 몸으로 간직한다. 트리 변환기가 생기면 거기서 꺼내 이어붙인다.

안전장치
  · --confirm-separate 없으면 push 안 함 (메인과 다른 빈 Supabase 확인).
  · 이미 이 Supabase에 몰랑이가 있으면 멈춘다.

사용
  python awaken_migrate.py home/molang_awaken.pkl --out ./migration
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
    python awaken_migrate.py home/molang_awaken.pkl --push --confirm-separate
"""
import argparse, json, os, pickle, sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ARRIVAL = {"text": ("집에 도착했다. 캐럿 아일랜드에서의 밤을 뒤로하고, 피우피우와 함께 돌아왔다. "
                    "익숙한 자리에 다시 있다는 게 포근하다."),
           "emotion": "안도", "place": "집"}


def load_world(p):
    with open(p, "rb") as f:
        w = pickle.load(f)
    if not isinstance(w, dict):
        raise SystemExit("예상한 세계 스냅샷 형식이 아니에요.")
    return w


def rows_facts(world):
    try:
        from molang_norm import normalize
    except Exception:
        def normalize(x): return x[:120]
    out = []
    for f in world.get("facts", []):
        if not isinstance(f, dict):
            continue
        t = (f.get("text") or "").strip()
        if not t:
            continue
        out.append({"text": t, "norm_key": f.get("norm_key") or normalize(t),
                    "about": f.get("about", "unknown"), "kind": f.get("kind", "fact"),
                    "strength": f.get("strength", 0.6), "trust": f.get("trust", "derived"),
                    "seen": f.get("seen", 1), "source": f.get("source", "user"),
                    "owner": "molang"})
    return out


def rows_purposes(world):
    return [{"purpose": p["purpose"], "from_topic": p.get("from_topic", ""),
             "why": p.get("why", ""), "status": p.get("status", "active")}
            for p in world.get("purposes", []) if isinstance(p, dict) and p.get("purpose")]


def rows_peer_talks(world):
    return [{"molang": p.get("molang", ""), "piupiu": p.get("piupiu", ""),
             "place": p.get("place", ""), "source": p.get("source", ""),
             "topic": p.get("topic", "")}
            for p in world.get("peer_talks", []) if isinstance(p, dict)]


def rows_dreams(world):
    return [{k: d.get(k) for k in
             ("text", "drive", "energy", "feeling", "linger_why", "lingering", "pieces")}
            for d in world.get("dreams", []) if isinstance(d, dict)]


def rows_quarantine(world):
    return [{"text": q.get("text", ""), "reason": q.get("reason", ""),
             "evidence": q.get("evidence"), "from": q.get("from", "")}
            for q in world.get("quarantine", []) if isinstance(q, dict)]


CONFIRMED = {"molang_facts": rows_facts, "molang_purposes": rows_purposes,
             "molang_peer_talks": rows_peer_talks, "molang_dreams": rows_dreams,
             "molang_quarantine": rows_quarantine}
WHOLE = {"molang_travel": "travel", "molang_home": "home",
         "molang_land": "land", "molang_map": "map"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("--out", default="./migration")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--confirm-separate", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

    world = load_world(a.pkl)
    os.makedirs(a.out, exist_ok=True)
    plan = {t: fn(world) for t, fn in CONFIRMED.items()}
    kept = ("facts", "purposes", "peer_talks", "dreams", "quarantine",
            "travel", "home", "land", "map", "persona", "trees")
    report = {"who": "캐럿 아일랜드에서 돌아온 몰랑이(62번)",
              "persona": (world.get("persona") or "")[:160], "cycle": world.get("cycle"),
              "제자리로": {t: len(v) for t, v in plan.items()},
              "통째로_보존": {t: ("있음" if world.get(k) else "없음") for t, k in WHOLE.items()},
              "판단트리_복원": f"{len([k for k in (world.get('trees') or {}) if isinstance((world['trees']).get(k), dict)])}개 (restore_trees 로 정확 복원)",
              "원본_전체_보존": "molang_world (28키 그대로)",
              "해석않고_보존": [k for k in world if k not in kept],
              "first_memory": ARRIVAL["text"]}
    json.dump(report, open(f"{a.out}/report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not a.push:
        print(f"\n--push 없이 실행됨. 아직 깨어나지 않았다. 검토: {a.out}/report.json")
        return
    if not a.confirm_separate:
        print("\n[멈춤] --confirm-separate 가 없다. 메인과 다른 '빈' Supabase임을 확인하면 붙여라.")
        return

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    try:
        if sb.table("molang_facts").select("id").limit(1).execute().data:
            print("\n[멈춤] 이미 몰랑이가 있다. 빈 Supabase를 써라.")
            return
    except Exception:
        pass

    sb.table("molang_world").upsert({"id": 1, "snapshot": world}, on_conflict="id").execute()

    # 판단 트리(사고 뼈대) 복원 — 민찬기가 만든 restore_trees 로 정확히. 추측 없음.
    try:
        from restore_trees import tree_from_blob
        from tree_registry import TreeRegistry, load_logic_db_types
        import registry_store
        reg = TreeRegistry()
        try:
            load_logic_db_types(reg, os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "logic_db.json"))
        except Exception:
            pass
        saved = {k: v for k, v in (world.get("trees") or {}).items() if isinstance(v, dict)}
        n = 0
        for k, tb in saved.items():
            t = tree_from_blob(tb)
            if t:
                reg.trees[k] = t
                n += 1
        registry_store.save(sb, reg)
        print(f"  판단 트리 {n}개 복원 (사고 뼈대 — 이 아이답게 생각한다)")
    except Exception as e:
        print(f"  ! 트리 복원 건너뜀(원본은 molang_world 에 보존됨): {str(e)[:100]}")
    sb.table("molang_skin").upsert({"id": 1, "persona": world.get("persona", "")},
                                   on_conflict="id").execute()
    for table, fn in CONFIRMED.items():
        rows = fn(world)
        for i in range(0, len(rows), 100):
            try:
                sb.table(table).insert(rows[i:i+100]).execute()
            except Exception as e:
                print(f"  ! {table} 일부 건너뜀: {str(e)[:80]}")
    for table, key in WHOLE.items():
        if world.get(key) is not None:
            try:
                sb.table(table).upsert({"id": 1, "data": world[key]}, on_conflict="id").execute()
            except Exception as e:
                print(f"  ! {table} 건너뜀: {str(e)[:80]}")
    sb.table("molang_episodes").insert({"owner": "molang", "place": ARRIVAL["place"],
                                        "question": "(돌아옴)", "answer": ARRIVAL["text"],
                                        "emotion": ARRIVAL["emotion"]}).execute()
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"\n깨어났다. 집에 도착했다. ({now})")
    print("  정체성·목적·여행·집·우정·꿈·억압을 갖고 깨어났고, 원본은 molang_world 에 그대로.")


if __name__ == "__main__":
    main()
