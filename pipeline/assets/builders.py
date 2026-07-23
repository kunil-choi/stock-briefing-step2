# pipeline/assets/builders.py
"""
KBS 머니올라 — 방송 비주얼 빌더 (HTML/CSS 슬라이드 + Playwright 렌더링)
"동영상"이 아니라 "PPT 슬라이드를 만들어서 화면으로 쓴다"는 관점으로 설계.
generate_assets.py가 기대하는 함수 시그니처/반환값/출력 파일명은 기존과 동일하게 유지한다.

재설계: 이 레포는 이제 증권사 리포트 종합만 다루므로(opening/briefing/closing
3섹션 고정), 리캡/오전장반응/AI전략 업데이트/shorts 하이라이트용 빌더는 전부
제거했다. 대신 pipeline/generate_media.py가 만드는 media_map.json(연합뉴스/
KBS 검색 결과)을 오프닝 배경 사진과 리포트 종목 카드 썸네일에 실제로
소비하도록 새로 연결했다 — 텍스트만 나열되던 이전 레이아웃 대신 방송사
그래픽에 가까운 사진 기반 구성으로 바꾼 부분.
"""
import os

from .config import W, H
from .render import render_html_to_png
from .html_theme import (
    esc, file_uri, shell, centered_shell, kbs_badge, text_plate,
    point_card, point_card_img, bullet_column, PALETTE, _ACCENT_CYCLE,
)


def _find_section(sections, id_prefix):
    for s in sections:
        if s.get("id", "").startswith(id_prefix):
            return s
    return {}


def _media_entry(media_map: dict, key: str) -> dict:
    if not media_map:
        return {}
    entry = media_map.get(key) or {}
    image_path = entry.get("image_path")
    if not image_path or not os.path.isfile(image_path):
        return {}
    return entry


# ── 오프닝 ─────────────────────────────────────────────────────────────────

def build_opening(data, out_dir, media_map=None):
    """오프닝 훅 화면. generate_script.py의 hook_narration이 오늘 리포트에서
    가장 눈에 띄는 사실로 바로 시작하도록 설계됐고(주목도), 여기서는 그 훅에
    등장한 종목의 연합뉴스/KBS 사진을 전체화면 배경으로 깔아 "방송사가 만든
    콘텐츠"라는 인상을 첫 화면부터 준다. 사진을 못 찾은 날에는 기존의
    그라디언트 원형 배경으로 자연스럽게 폴백한다(레이아웃 깨짐 없음)."""
    sec      = _find_section(data.get("sections", []), "opening")
    keywords = sec.get("keywords", [])[:4]
    date_str = data.get("date", "")

    media = _media_entry(media_map, "opening")
    bg_path = media.get("image_path")
    credit  = media.get("credit", "")

    kw_html = "".join(
        f'<span class="pill" style="background:{c}1a;color:{c};border:2px solid {c};'
        f'font-size:26px;">{esc(k)}</span>'
        for k, c in zip(keywords, _ACCENT_CYCLE)
    )
    date_html = (
        f'<div class="pill" style="background:{PALETTE["accent_soft"]};'
        f'color:{PALETTE["accent"]};font-size:26px;">{esc(date_str)}</div>'
        if date_str else ""
    )

    if bg_path:
        # 사진 배경일 때는 은은한 원형 그라디언트 대신 text_plate로 헤드라인
        # 가독성을 확보한다(어떤 사진이든 항상 대비가 보장됨).
        headline = text_plate(
            '<div style="font-size:30px;font-weight:700;color:#ffe066;letter-spacing:.01em;">'
            '증권사가 주목한 오늘의 리포트</div>'
            '<div style="font-size:78px;font-weight:800;line-height:1.25;color:#fff;margin-top:8px;">'
            'KBS 머니올라<br>증권사 리포트 브리핑</div>'
        )
        content = f"""
{headline}
{date_html}
<div style="display:flex;gap:16px;margin-top:20px;">{kw_html}</div>
"""
    else:
        content = f"""
<div style="position:absolute;z-index:-1;width:900px;height:900px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-260px;left:50%;transform:translateX(-50%);"></div>
<div style="font-size:32px;font-weight:700;color:{PALETTE['accent']};letter-spacing:.01em;">증권사가 주목한 오늘의 리포트</div>
<div style="font-size:88px;font-weight:800;line-height:1.25;">KBS 머니올라<br>증권사 리포트 브리핑</div>
{date_html}
<div style="display:flex;gap:16px;margin-top:12px;">{kw_html}</div>
"""

    html = centered_shell(content, background_image=bg_path, credit=credit)
    return render_html_to_png(html, os.path.join(out_dir, "00_opening.png"))


# ── 증권사 리포트 브리핑 (핵심 콘텐츠) ───────────────────────────────────────

def build_report_briefing(data, out_dir, media_map=None):
    """리포트 items(종목/섹터테마)를 카드로 나열하되, media_map에 해당 종목의
    연합뉴스/KBS 사진이 있으면 point_card_img()로 썸네일을 얹는다. 검색에
    실패한 항목만 텍스트 전용 point_card()로 자연스럽게 폴백한다(레이아웃은
    항상 유지)."""
    sec = _find_section(data.get("sections", []), "briefing")
    if not sec:
        return None

    corner_summary = sec.get("corner_summary", "")
    corner_html = (
        f'<div class="corner-summary">{esc(corner_summary)}</div>' if corner_summary else ""
    )

    items = sec.get("items", [])
    if items:
        cards = ""
        for i, it in enumerate(items):
            if isinstance(it, dict):
                name = (it.get("name") or "").strip()
                text = (it.get("text") or "").strip()
            else:
                name, text = "", str(it)
            color = _ACCENT_CYCLE[i % len(_ACCENT_CYCLE)]
            media = _media_entry(media_map, f"briefing_item_{i}")
            image_path = media.get("image_path")
            if image_path:
                cards += point_card_img(i + 1, name, text, color, image_uri=file_uri(image_path))
            elif name:
                cards += point_card(i + 1, f"{name}: {text}", color)
            else:
                cards += point_card(i + 1, text, color)
        layout = "grid;grid-template-columns:1fr 1fr" if len(items) > 5 else "flex;flex-direction:column"
        body_html = f'<div style="display:{layout};gap:14px;">{cards}</div>'
    else:
        body_html = ""

    content = f"{corner_html}{body_html}"
    html = shell("증권사 리포트 브리핑", content)
    return render_html_to_png(html, os.path.join(out_dir, "01_briefing.png"))


# ── 클로징 ─────────────────────────────────────────────────────────────────

def build_closing(data, out_dir):
    content = f"""
{kbs_badge()}
<div style="font-size:96px;font-weight:800;">감사합니다</div>
<div style="font-size:38px;font-weight:600;color:{PALETTE['accent']};">성공적인 투자 되시길 바랍니다</div>
<div class="card" style="border:2px solid {PALETTE['up']}55;background:#fff6f6;
  padding:28px 36px;max-width:1400px;margin-top:12px;">
  <div style="font-size:28px;font-weight:800;color:{PALETTE['up']};margin-bottom:14px;">투자 유의사항</div>
  <div style="font-size:22px;line-height:1.7;color:#5c3a3a;text-align:left;">
    본 브리핑은 AI가 공개 데이터를 분석한 참고용 정보입니다.<br>
    특정 종목의 매수·매도 권유가 아니며, 수익을 보장하지 않습니다.<br>
    주식 투자는 원금 손실 위험이 있으며, 최종 투자 결정과<br>
    모든 책임은 전적으로 투자자 본인에게 있습니다.
  </div>
</div>
"""
    html = centered_shell(content)
    return render_html_to_png(html, os.path.join(out_dir, "99_closing.png"))


# ── 썸네일 (YouTube 업로드용, pipeline/generate_metadata.py에서 호출) ──────

def build_thumbnail(data: dict, title: str, out_path: str, media_map=None) -> str:
    """script.json + generate_metadata.py가 만든 title로 1920x1080(16:9,
    YouTube 썸네일 권장 규격 이상) PNG 1장을 만든다. media_map에 오프닝
    배경 사진이 있으면 썸네일에도 재사용해 방송 화면과 통일감을 준다."""
    sections     = data.get("sections", [])
    briefing_sec = _find_section(sections, "briefing")
    leader_item  = (briefing_sec.get("items") or [{}])[0] if briefing_sec else {}
    leader_name  = (leader_item.get("name", "") if isinstance(leader_item, dict) else "").lstrip("🎯💎 ")
    date_str     = data.get("date", "")

    media = _media_entry(media_map, "opening")
    bg_path = media.get("image_path")
    credit  = media.get("credit", "")

    stock_html = (
        f'<div class="pill" style="background:#fff2;color:#fff;'
        f'border:3px solid #fff;font-size:40px;font-weight:800;">'
        f'{esc(leader_name)}</div>'
        if leader_name else ""
    )

    if bg_path:
        title_html = text_plate(
            f'<div style="font-size:96px;font-weight:800;line-height:1.2;max-width:1600px;color:#fff;">{esc(title)}</div>'
        )
        content = f"""
{kbs_badge()}
{title_html}
<div class="pill" style="background:#fff2;color:#fff;font-size:30px;">{esc(date_str)}</div>
{stock_html}
"""
    else:
        content = f"""
<div style="position:absolute;z-index:-1;width:1100px;height:1100px;border-radius:50%;
  background:radial-gradient(circle,{PALETTE['accent_soft']} 0%,transparent 70%);
  top:-320px;left:50%;transform:translateX(-50%);"></div>
{kbs_badge()}
<div style="font-size:104px;font-weight:800;line-height:1.2;max-width:1600px;">{esc(title)}</div>
<div class="pill" style="background:{PALETTE['accent_soft']};color:{PALETTE['accent']};
  font-size:30px;">{esc(date_str)}</div>
{stock_html}
"""

    html = centered_shell(content, background_image=bg_path, credit=credit)
    return render_html_to_png(html, out_path)
