# pipeline/generate_assets.py
"""
AI 주식 브리핑 — 에셋 생성 진입점
사용법: python pipeline/generate_assets.py [KO|ko|en]

재설계: script.json이 opening/briefing/closing 3섹션으로 고정됐으므로
video_format 분기를 제거했다. output/{lang}/media/media_map.json이 있으면
(pipeline/generate_media.py가 미리 만들어둠) 오프닝 배경 사진과 리포트 종목
카드 썸네일에 연결한다 — 없으면(네트워크 실패 등) 빈 dict로 취급해 기존
텍스트 전용 레이아웃으로 안전하게 폴백한다.
"""
import os, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.builders import build_opening, build_report_briefing, build_closing
from assets.render import close_renderer
from assets.html_theme import set_briefing_date

import re


def _kdate_to_dotted(date_str: str) -> str:
    """'2026년 07월 08일' → '2026.07.08'. 매칭 실패 시 빈 문자열."""
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}.{int(mo):02d}.{int(d):02d}"


def run(lang: str = "KO"):
    lang = lang.upper()

    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")
    out_dir = os.path.join(root, "output", lang, "frames")
    media_map_path = os.path.join(root, "output", lang, "media", "media_map.json")

    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    sections = data.get("sections", [])
    print(f"📂 script.json 로드 완료 (섹션 수: {len(sections)})")

    media_map = {}
    if os.path.isfile(media_map_path):
        with open(media_map_path, encoding="utf-8") as f:
            media_map = json.load(f)
        resolved = sum(1 for v in media_map.values() if v.get("source") != "fallback")
        print(f"🖼️ media_map.json 로드 완료 ({resolved}/{len(media_map)}개 실사진 확보)")
    else:
        print("⚠️ media_map.json 없음 — 사진 없이 텍스트 전용 레이아웃으로 진행")

    # 모든 슬라이드 상단바 날짜를 실제 브리핑 날짜로 고정 (렌더링 시점의 시스템
    # 날짜로 폴백하면 워크플로우가 전날 데이터로 실행됐을 때 날짜가 어긋난다)
    briefing_date = _kdate_to_dotted(data.get("date", ""))
    if briefing_date:
        set_briefing_date(briefing_date)
        print(f"📅 슬라이드 날짜 고정: {briefing_date}")

    asset_map = {"frames": [], "lang": lang}

    try:
        asset_map["frames"].append(build_opening(data, out_dir, media_map=media_map))
        frame = build_report_briefing(data, out_dir, media_map=media_map)
        if frame:
            asset_map["frames"].append(frame)
        asset_map["frames"].append(build_closing(data, out_dir))
    finally:
        close_renderer()

    map_path = os.path.join(root, "output", lang, "asset_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(asset_map, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료: {len(asset_map['frames'])}개 프레임 → {out_dir}")
    return asset_map


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
