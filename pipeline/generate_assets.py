# pipeline/generate_assets.py
"""
AI 주식 브리핑 — 에셋 생성 진입점
사용법: python pipeline/generate_assets.py [KO|ko|en]
"""
import os, re, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from assets.builders import (
    build_opening,
    build_shorts_highlight,
    build_recap,
    build_reaction,
    build_report_briefing,
    build_ai_strategy,
    build_closing,
)
from assets.render import close_renderer
from assets.html_theme import set_briefing_date


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
    img_dir = os.path.join(root, "output", lang, "images")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    sections = data.get("sections", [])
    print(f"📂 script.json 로드 완료 (섹션 수: {len(sections)})")

    # 모든 슬라이드 상단바 날짜를 실제 브리핑 날짜로 고정 (렌더링 시점의 시스템
    # 날짜로 폴백하면 워크플로우가 전날 데이터로 실행됐을 때 날짜가 어긋난다)
    briefing_date = _kdate_to_dotted(data.get("date", ""))
    if briefing_date:
        set_briefing_date(briefing_date)
        print(f"📅 슬라이드 날짜 고정: {briefing_date}")

    video_format = data.get("video_format", "shorts")
    asset_map = {"frames": [], "lang": lang}

    try:
        asset_map["frames"].append(build_opening(data, out_dir))

        if video_format == "shorts":
            # 핵심종목 5개 미만일 때 — generate_shorts_script()가 만든 3섹션
            # (opening/highlight/closing)짜리 축소 스크립트를 그대로 렌더링한다.
            frame = build_shorts_highlight(data, out_dir)
            if frame:
                asset_map["frames"].append(frame)
        else:
            # mid/full — STEP-1과 각자 완결된 재브리핑이 아니라 "2부"로 설계됐으므로
            # 시장요약/섹터/종목카드를 처음부터 다시 만들지 않는다. STEP-1 리캡 →
            # 오전장 반응 업데이트 → 증권사 리포트 브리핑 순으로만 구성한다.
            for builder in (build_recap, build_reaction, build_report_briefing):
                frame = builder(data, out_dir)
                if frame:
                    asset_map["frames"].append(frame)

            # AI전략 업데이트는 full 티어에만 있을 수 있음(mid는 짧게 생략되거나
            # 1줄로 축약돼 섹션 자체가 없을 수 있음) — 섹션 존재 여부로 판단.
            if any(s.get("id") == "ai_strategy" for s in sections):
                asset_map["frames"].append(build_ai_strategy(data, out_dir))

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
