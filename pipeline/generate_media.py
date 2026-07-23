# pipeline/generate_media.py
"""
media_map.json 생성 진입점 (stock-briefing-step1의 연합뉴스/KBS 검색 파이프라인
이식판). 사용법: python pipeline/generate_media.py [KO|ko|en]

step1은 개체명 추출 결과인 scene_plan.json을 입력으로 쓰지만, 이 레포
(report_update)는 스크립트 구조가 훨씬 단순하다 — 오프닝/증권사 리포트
브리핑/클로징 3섹션뿐이고, 리포트 브리핑의 items[]가 이미 "종목명(또는 섹터
테마)": "분석 텍스트" 형태로 정리돼 있다. 그래서 별도 개체명 추출 없이
script.json의 briefing.items를 바로 검색 키워드로 써서, 같은
AssetSearchService(연합뉴스/KBS/naver_discovery 검색 → 점수화 → 권리 분류)를
그대로 재사용하는 얇은 어댑터만 이 파일에 둔다.

MEDIA_MOCK=1 환경변수(또는 config/media.yml의 mock_mode: true)를 설정하면
실제 네트워크 요청 없이 MockProvider로 동작한다.
"""
import os
import re
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config_media
from assets.asset_search_service import AssetSearchService

# 리포트 아이템 이름에 붙는 장식 접두어(오늘의 픽/섹터 이모지 등)를 검색
# 키워드에서 제거한다 — "💎 오늘의 픽 — 삼성전자"가 아니라 "삼성전자"로 검색해야
# 실제 뉴스 이미지가 나온다.
_NAME_PREFIX_RE = re.compile(r"^[🎯💎]\s*(?:오늘의\s*픽\s*[—-]\s*)?")


def _clean_keyword(name: str) -> str:
    name = _NAME_PREFIX_RE.sub("", (name or "").strip())
    return name.strip()


def build_scene_sections(script: dict) -> list:
    """script.json → media_pipeline이 기대하는 최소 scene_plan 섹션 리스트.
    각 섹션은 {id, visual_keywords, preferredSources}만 채운다(개체명 추출
    파이프라인이 만드는 needsDataReview/assetRequirements 같은 고급 필드는
    이 레포 범위에서 항상 기본값으로 취급됨)."""
    sections_out = []

    opening = next((s for s in script.get("sections", []) if s.get("id") == "opening"), {})
    opening_keywords = [_clean_keyword(k) for k in (opening.get("keywords") or [])]
    opening_keywords = [k for k in opening_keywords if k] or ["코스피"]
    sections_out.append({
        "id": "opening",
        "visual_keywords": opening_keywords,
        "preferredSources": ["YONHAP", "KBS_WEBSITE"],
    })

    briefing = next((s for s in script.get("sections", []) if s.get("id") == "briefing"), {})
    for i, item in enumerate(briefing.get("items", []) or []):
        name = _clean_keyword(item.get("name", "") if isinstance(item, dict) else "")
        if not name:
            continue
        sections_out.append({
            "id": f"briefing_item_{i}",
            "visual_keywords": [name],
            "preferredSources": ["YONHAP", "KBS_WEBSITE"],
        })

    return sections_out


def run(lang: str = "KO"):
    lang = lang.upper()
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")
    img_dir = os.path.join(root, "output", lang, "media")
    map_path = os.path.join(img_dir, "media_map.json")
    manifest_path = os.path.join(img_dir, "asset_manifest.json")
    log_path = os.path.join(root, "data", "media", "license_log.csv")

    if not os.path.isfile(script_path):
        print(f"❌ script.json을 찾을 수 없습니다: {script_path}")
        sys.exit(1)

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    scene_plan = {"sections": build_scene_sections(script)}
    print(f"  [media] 검색 대상 섹션 {len(scene_plan['sections'])}개 "
          f"(오프닝 1 + 리포트 종목/테마 {len(scene_plan['sections']) - 1}개)")

    service = AssetSearchService(config_media.PROVIDER_NAMES, mock_mode=config_media.MOCK_MODE)
    if config_media.MOCK_MODE:
        print("  [media] MOCK_MODE=on → MockProvider만 사용")
    media_map, asset_manifest = service.build_for_scene_plan(
        scene_plan, img_dir, log_path,
        cache_dir=config_media.ASSET_CACHE_DIR,
        dedup_window_days=config_media.DEDUP_WINDOW_DAYS,
        dedup_threshold=config_media.DEDUP_HAMMING_THRESHOLD,
        max_candidates=config_media.MAX_CANDIDATES_PER_SECTION,
    )

    os.makedirs(img_dir, exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(media_map, f, ensure_ascii=False, indent=2)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(asset_manifest, f, ensure_ascii=False, indent=2)

    resolved = sum(1 for v in media_map.values() if v.get("source") != "fallback")
    fallback = len(media_map) - resolved
    print(f"✅ media_map 생성 완료! 총 {len(media_map)}개 섹션 (검색 성공 {resolved} / 폴백 {fallback}) → {map_path}")
    return media_map


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
