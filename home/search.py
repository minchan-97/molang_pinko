"""
molang_search.py — Brave Search 연동.

격리 원칙: 검색 결과는 답변 생성 컨텍스트로만 쓰인다.
absorb()에 절대 전달하지 않는다. 웹 문장이 '찬기에 대한 사실'로
굳으면 되돌리기 어렵다.
"""
import json as _json
import urllib.parse
import urllib.request

BRAVE_ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'


def brave_search(api_key: str, query: str, count: int = 5) -> list[dict]:
    qs = urllib.parse.urlencode({'q': query, 'count': count,
                                 'country': 'KR', 'search_lang': 'ko'})
    req = urllib.request.Request(
        BRAVE_ENDPOINT + '?' + qs,
        headers={'Accept': 'application/json',
                 'X-Subscription-Token': api_key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = _json.loads(resp.read().decode())
    results = data.get('web', {}).get('results', [])
    return [{
        'title': x.get('title', ''),
        'url': x.get('url', ''),
        'snippet': x.get('description', ''),
        'age': x.get('age', ''),
    } for x in results]


def to_context(results: list[dict]) -> str:
    """LLM에 넘길 블록. '외부 정보'라고 명시적으로 표시한다."""
    if not results:
        return ''
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}\n{r['snippet']}\n출처: {r['url']}")
    return (
        "[외부 검색 결과 — 이것은 네 기억이 아니다]\n"
        "아래는 방금 웹에서 가져온 정보다. 전달할 때 반드시 출처를 함께 말하고,\n"
        "네가 원래 알던 것처럼 말하지 마라. 이 내용은 기억에 저장되지 않는다.\n\n"
        + "\n\n".join(lines)
    )


import os


def available() -> bool:
    return bool(os.environ.get("BRAVE_API_KEY"))


def search_ctx(query: str, count: int = 4) -> str:
    """검색해서 바로 'LLM에 줄 맥락'으로. 키 없거나 실패하면 빈 문자열."""
    key = os.environ.get("BRAVE_API_KEY", "")
    if not key or not query.strip():
        return ""
    try:
        return to_context(brave_search(key, query.strip(), count))
    except Exception:
        return ""
