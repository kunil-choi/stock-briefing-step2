# pipeline/generate_metadata.py
"""
YouTube 업로드 메타데이터(제목/썸네일/설명문/태그) + output/YYYY-MM-DD/metadata.json 생성.

script.json + config/schedule.yml(briefing_type)을 입력으로 받아 결정적
템플릿으로 제목/설명/태그를 만든다(LLM 호출 없음). 썸네일은
pipeline/assets/builders.build_thumbnail()로 렌더링한다.

재설계: video_format(shorts/mid/full) 티어를 폐기하고 고정 미드폼 단일
템플릿으로 통일했다.

fallback: script.json이 없거나 비어있으면 status="failed"로 최소한의
metadata.json만 남기고 종료한다(빈 배포 폴더가 아예 없는 것보다, 왜 실패했는지
알 수 있는 편이 낫다).
"""
import os
import re
import sys
import json
import shutil
import subprocess
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config_schedule import BRIEFING_TYPE

KST = timezone(timedelta(hours=9))

TITLE_TEMPLATE = "[증권사 리포트 브리핑] {date} 오늘 리포트 총정리 | KBS 머니올라"

BASE_TAGS = ["주식", "주식브리핑", "증시", "코스피", "코스닥", "KBS머니올라", "재테크", "증권사리포트"]


def _kdate_to_iso(date_str: str) -> str:
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str or "")
    if not m:
        return datetime.now(KST).strftime("%Y-%m-%d")
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def build_title(script: dict, date_iso: str) -> str:
    return TITLE_TEMPLATE.format(date=date_iso)


def _briefing_item_names(script: dict) -> list:
    sections = script.get("sections", [])
    briefing_sec = next((s for s in sections if s.get("id") == "briefing"), {})
    names = []
    for it in briefing_sec.get("items", []) or []:
        name = (it.get("name", "") if isinstance(it, dict) else str(it)).lstrip("🎯💎 —-").strip()
        if name:
            names.append(name)
    return names


def build_description(script: dict) -> str:
    sections = script.get("sections", [])
    briefing_sec = next((s for s in sections if s.get("id") == "briefing"), {})
    corner = briefing_sec.get("corner_summary", "")
    stock_names = _briefing_item_names(script)

    lines = []
    if corner:
        lines.append(corner)
    if stock_names:
        lines.append("")
        lines.append("오늘 다룬 종목/테마: " + ", ".join(stock_names[:10]))
    lines.append("")
    lines.append(
        "본 영상은 AI가 공개된 증권사 리포트·뉴스를 종합해 전달하는 참고용 정보입니다. "
        "특정 종목의 매수·매도 권유가 아니며, 투자 결정과 그 책임은 전적으로 투자자 본인에게 있습니다."
    )
    return "\n".join(lines)


def build_tags(script: dict) -> list:
    sections = script.get("sections", [])
    opening = next((s for s in sections if s.get("id") == "opening"), {})
    keywords = opening.get("keywords", []) or []
    stock_names = _briefing_item_names(script)

    tags = BASE_TAGS + keywords + stock_names[:10]
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:30]


def get_video_duration_seconds(video_path: str) -> float:
    if not os.path.exists(video_path):
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        return float(out)
    except Exception as e:
        print(f"⚠️ ffprobe 실패: {e}")
        return 0.0


def write_fallback_metadata(out_dir: str, status: str, warnings: list):
    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "briefing_type": BRIEFING_TYPE,
        "generated_at":  datetime.now(KST).isoformat(),
        "status":        status,
        "warnings":      warnings,
    }
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"⚠️ fallback metadata.json 작성 ({status}) → {out_dir}")


def run(lang: str = "KO"):
    root = os.path.join(_HERE, "..")
    script_path = os.path.join(root, "output", lang, "scripts", "script.json")

    if not os.path.exists(script_path):
        write_fallback_metadata(
            os.path.join(root, "output", datetime.now(KST).strftime("%Y-%m-%d")),
            status="failed", warnings=[f"{script_path} 없음"],
        )
        sys.exit(1)

    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    date_iso = _kdate_to_iso(script.get("date", ""))
    out_dir  = os.path.join(root, "output", date_iso)
    os.makedirs(out_dir, exist_ok=True)

    warnings = []
    title       = build_title(script, date_iso)
    description = build_description(script)
    tags        = build_tags(script)

    # media_map.json이 있으면 썸네일도 오프닝과 같은 배경 사진을 재사용한다.
    media_map = {}
    media_map_path = os.path.join(root, "output", lang, "media", "media_map.json")
    if os.path.isfile(media_map_path):
        with open(media_map_path, encoding="utf-8") as f:
            media_map = json.load(f)

    from assets.builders import build_thumbnail
    thumbnail_path = os.path.join(out_dir, "thumbnail.png")
    try:
        build_thumbnail(script, title, thumbnail_path, media_map=media_map)
    except Exception as e:
        print(f"⚠️ 썸네일 생성 실패: {e}")
        warnings.append(f"썸네일 생성 실패: {e}")
        thumbnail_path = None

    # 영상/스크립트 사본
    video_src = os.path.join(root, "output", lang, "video", "final.mp4")
    video_dst_rel = None
    duration_seconds = 0.0
    if os.path.exists(video_src):
        video_dst = os.path.join(out_dir, "final.mp4")
        shutil.copy2(video_src, video_dst)
        video_dst_rel = "final.mp4"
        duration_seconds = get_video_duration_seconds(video_src)
    else:
        warnings.append(f"{video_src} 없음 — video 단계가 아직 실행되지 않았을 수 있음")

    script_dst = os.path.join(out_dir, "script.json")
    shutil.copy2(script_path, script_dst)

    core_stock_count = len(_briefing_item_names(script))

    status = "success" if video_dst_rel else "partial"
    meta = {
        "briefing_type":   BRIEFING_TYPE,
        "briefing_date":   date_iso,
        "generated_at":    datetime.now(KST).isoformat(),
        "status":          status,
        "warnings":        warnings,
        "title":           title,
        "description":     description,
        "tags":            tags,
        "thumbnail_path":  "thumbnail.png" if thumbnail_path else None,
        "video_path":      video_dst_rel,
        "script_path":     "script.json",
        "duration_seconds": round(duration_seconds, 1),
        "core_stock_count": core_stock_count,
    }
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n✅ metadata.json 생성 완료 → {out_dir}/metadata.json (status={status})")
    return meta


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
