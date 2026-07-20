# pipeline/generate_script.py
"""
AI 주식 브리핑 — report_update(STEP-2) 스크립트 생성 모듈

설계 원칙(재설계): STEP-1과 STEP-2는 "각자 완결된 브리핑"이 아니라 "하루짜리
연속 시리즈의 1부/2부"다. stock-briefing-v3-2가 이미 STEP-1 결과물 위에
새 정보(오전장 반응/증권사 리포트 심화분석/AI전략 업데이트)만 얹어서
data/briefing_data.json으로 내려주므로, 이 모듈은 그 내용을 처음부터
재분석하지 않고 방송 나레이션/자막으로 변환하기만 한다.

- 데이터 소스: stock-briefing-v3-2의 data/briefing_data.json
  (raw.githubusercontent.com)
- 목표 영상 길이: length_tier에 비례한 가변 길이
  (shorts 30~50초 / mid 5~8분 / full 8~15분) — 고정 15분 목표는 폐기.
- 오프닝: 'KBS 머니올라' 멘트, STEP-1을 다시 설명하지 않고 이어지는 톤
- 발음 교정 / 나레이션·자막 완전 분리
- 목소리 관리: pipeline/voice_config.py 에서 통합 관리
"""

import os
import re
import sys
import json
import urllib.request
from datetime import datetime
from openai import OpenAI

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# SCRIPT_MOCK=1: OpenAI를 실제로 호출하지 않고 구조만 맞는 더미 데이터로
# 대체한다 — 실제 영상 생성 전에 파이프라인 전체(에셋/오디오/영상/자막/
# quality_gate)를 토큰 소비 없이 로컬에서 먼저 검증하기 위함
# (stock-briefing-step1과 동일한 드라이런 스위치).
SCRIPT_MOCK = os.environ.get("SCRIPT_MOCK") == "1"

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key and not SCRIPT_MOCK:
    raise EnvironmentError("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
client = OpenAI(api_key=_api_key or "sk-mock-dry-run")

# report_update는 stock-briefing-v3-2(증권사 리포트+오전장 반영 스냅샷)를 소비한다.
UPSTREAM_REPO = "kunil-choi/stock-briefing-v3-2"

TODAY       = datetime.now().strftime("%Y년 %m월 %d일")
TODAY_MONTH = datetime.now().strftime("%-m")
TODAY_DAY   = datetime.now().strftime("%-d")

# ─────────────────────────────────────────────────────────────────────────────
# 오프닝 / 클로징 멘트
# ─────────────────────────────────────────────────────────────────────────────

# report_update 재설계(1부/2부 연속 시리즈) — 아침 브리핑을 다시 설명하지
# 않고 "이어서" 들어가는 오프닝으로 교체.
OPENING_NARRATION = (
    "오늘 아침 머니올라 브리핑, 잘 보셨나요? "
    "장이 시작된 지금, 그때 짚어드린 종목들이 실제로 어떻게 움직였는지, "
    "그리고 그 사이 증권사 리포트에서는 어떤 이야기가 나왔는지 업데이트해 드립니다."
)

OPENING_SUBTITLE = (
    "오늘 아침 머니올라 브리핑, 잘 보셨나요? "
    "장이 시작된 지금, 그때 짚어드린 종목들이 실제로 어떻게 움직였는지, "
    "그리고 그 사이 증권사 리포트에서는 어떤 이야기가 나왔는지 업데이트해 드립니다."
)

# ─────────────────────────────────────────────────────────────────────────────
# 투자 경고 클로징 (요구사항 8번: 경고문 강화)
# ─────────────────────────────────────────────────────────────────────────────

CLOSING_NARRATION = (
    "이상으로 케이비에스 머니올라의 오늘의 주식시장 브리핑을 마치겠습니다. "
    "오늘도 함께해 주셔서 감사합니다. "
    "마지막으로 꼭 당부드릴 말씀이 있습니다. "
    "본 브리핑은 에이아이가 뉴스, 유튜브, 증권사 리포트 등 공개 데이터를 분석하여 제작한 참고용 정보입니다. "
    "특정 종목의 매수 또는 매도를 권유하는 것이 아니며, 수익을 보장하지 않습니다. "
    "주식 투자는 원금 손실의 위험이 있으므로 반드시 본인의 판단과 책임 하에 신중하게 결정하시기 바랍니다. "
    "투자의 최종 결정과 그에 따른 모든 책임은 전적으로 투자자 본인에게 있습니다. "
    "구독과 좋아요는 저희에게 큰 힘이 됩니다. 내일도 유익한 브리핑으로 찾아뵙겠습니다. 감사합니다."
)

CLOSING_SUBTITLE = (
    "이상으로 KBS 머니올라의 오늘의 주식시장 브리핑을 마치겠습니다. "
    "오늘도 함께해 주셔서 감사합니다. "
    "마지막으로 꼭 당부드릴 말씀이 있습니다. "
    "본 브리핑은 AI가 뉴스, 유튜브, 증권사 리포트 등 공개 데이터를 분석하여 제작한 참고용 정보입니다. "
    "특정 종목의 매수 또는 매도를 권유하는 것이 아니며, 수익을 보장하지 않습니다. "
    "주식 투자는 원금 손실의 위험이 있으므로 반드시 본인의 판단과 책임 하에 신중하게 결정하시기 바랍니다. "
    "투자의 최종 결정과 그에 따른 모든 책임은 전적으로 투자자 본인에게 있습니다. "
    "구독과 좋아요는 저희에게 큰 힘이 됩니다. 내일도 유익한 브리핑으로 찾아뵙겠습니다. 감사합니다."
)

DISCLAIMER = (
    "⚠️ 투자 유의사항 | 본 브리핑은 AI 분석 참고자료이며 투자 권유가 아닙니다. "
    "주식 투자는 원금 손실 위험이 있습니다. 투자 책임은 전적으로 본인에게 있습니다."
)


# ─────────────────────────────────────────────────────────────────────────────
# 자막 표기 안전망 — narration용 한글 발음/숫자 표기가 subtitle 필드에 잘못
# 섞여 들어온 경우 자동으로 원래 표기(숫자/로마자)로 되돌립니다.
# LLM이 프롬프트 지시를 놓쳤을 때의 최종 방어선이며, narration 필드에는
# 절대 적용하지 않습니다.
# ─────────────────────────────────────────────────────────────────────────────

# narration에서만 쓰이는 필드 — 자막 안전망을 적용하지 않음
_NARRATION_ONLY_KEYS = {"narration", "narration_summary", "id", "title", "date"}

# 영문 약어의 한글 발음 표기 → 원래 로마자 표기 (긴 복합어 먼저)
_ACRONYM_SUBTITLE_FIXES = [
    ("에이치디현대중공업", "HD현대중공업"),
    ("에이치디현대일렉트릭", "HD현대일렉트릭"),
    ("에이치디현대", "HD현대"),
    ("에스케이하이닉스", "SK하이닉스"),
    ("엘지에너지솔루션", "LG에너지솔루션"),
    ("엘지화학", "LG화학"),
    ("케이비금융", "KB금융"),
    ("에이치비엠", "HBM"),
    ("에이아이", "AI"),
    ("이티에프", "ETF"),
    ("이에스에스", "ESS"),
    ("피씨이", "PCE"),
    ("디에스알", "DSR"),
    ("오티티", "OTT"),
    ("에이디알", "ADR"),
    ("엠오유", "MOU"),
    ("비피에스", "BPS"),
    ("이피에스", "EPS"),
    ("피이알", "PER"),
    ("알오이", "ROE"),
    ("아이피오", "IPO"),
    ("엠앤에이", "M&A"),
    ("알앤디", "R&D"),
    ("와이오와이", "YoY"),
    ("큐오큐", "QoQ"),
    ("에스케이", "SK"),
    ("엘지", "LG"),
    ("케이비", "KB"),
]

_KR_DIGIT = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
             "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
_KR_SMALL_UNIT = {"십": 10, "백": 100, "천": 1000}
_KR_BIG_UNITS = "조억만"
_KR_NUM_CHARS = "".join(_KR_DIGIT) + "".join(_KR_SMALL_UNIT) + _KR_BIG_UNITS


def _parse_kr_number_group(chars: str):
    """4자리 미만 그룹(예: '이천사백')을 정수로 변환. 실패하면 None."""
    if not chars:
        return 0
    total = 0
    pending = None
    for ch in chars:
        if ch in _KR_DIGIT:
            pending = _KR_DIGIT[ch]
        elif ch in _KR_SMALL_UNIT:
            total += (pending if pending is not None else 1) * _KR_SMALL_UNIT[ch]
            pending = None
        else:
            return None
    if pending is not None:
        total += pending
    return total


def _korean_number_run_to_digits(run: str):
    """'십이조이천사백억' → '12조2400억' 처럼 조/억/만 단위는 유지한 채 각 자릿수
    구간만 아라비아 숫자로 변환합니다. 파싱 실패 시 None을 반환합니다."""
    parts = re.split(r"([조억만])", run)
    out, i = [], 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and parts[i + 1] in "조억만":
            val = _parse_kr_number_group(seg)
            if val is None:
                return None
            out.append(f"{val}{parts[i + 1]}")
            i += 2
        else:
            if seg:
                val = _parse_kr_number_group(seg)
                if val is None:
                    return None
                out.append(str(val))
            i += 1
    return "".join(out) if out else None


_DECIMAL_PERCENT_RE = re.compile(
    r"([영일이삼사오육륙칠팔구]+)쩜([영일이삼사오육륙칠팔구]+)퍼센트"
)


def _fix_decimal_percent(text: str) -> str:
    """'십이쩜오퍼센트' → '12.5%' / '영쩜팔퍼센트' → '0.8%'"""
    def repl(m):
        int_val = _parse_kr_number_group(m.group(1))
        dec_str = "".join(str(_KR_DIGIT[c]) for c in m.group(2))
        if int_val is None or not dec_str:
            return m.group(0)
        return f"{int_val}.{dec_str}%"
    return _DECIMAL_PERCENT_RE.sub(repl, text)


_PLAIN_NUMBER_RE = re.compile(
    f"([{_KR_NUM_CHARS}]+)(원|퍼센트|포인트|배)?"
)


# 숫자처럼 보이지만 실제로는 일반 어휘인 경우 (오탐 확인된 단어만 등록).
# 예: "구조"(9+조) → 구조적/구조원 등 실제 단어와 충돌하므로 절대 숫자로 변환하지 않음.
_NUMBER_RUN_DENYLIST = {"구조"}


def _fix_plain_numbers(text: str) -> str:
    """'삼천오백원' → '3500원' 처럼 뒤에 원/퍼센트/포인트/배 단위가 붙는 경우,
    또는 '십이조이천사백억'처럼 조/억/만 단위가 두 번 이상 나와 명백히 복합
    숫자 표기로 판단되는 경우만 변환합니다.

    한글에는 숫자 음절(일이삼사...구/십백천만억조)이 우연히 들어간 일반 단어가
    매우 많습니다 (구조, 오만, 천만에요, 구천 등). 그래서 "조/억/만으로 끝나기만
    하면 숫자"로 간주하던 이전 방식은 "구조적" → "9조적" 같은 오탐을 냈습니다.
    이제는 반드시 (1) 뒤에 명시적 단위 앵커가 붙거나 (2) 조/억/만이 한 런에서
    2회 이상 나타나 복합 숫자임이 명백한 경우에만 변환합니다.
    """
    def repl(m):
        run, trailing = m.group(1), m.group(2) or ""
        if len(run) < 2 or not any(c in "십백천만억조" for c in run):
            return m.group(0)
        if run in _NUMBER_RUN_DENYLIST:
            return m.group(0)
        big_unit_count = sum(run.count(u) for u in _KR_BIG_UNITS)
        if not trailing and big_unit_count < 2:
            return m.group(0)
        converted = _korean_number_run_to_digits(run)
        if converted is None:
            return m.group(0)
        trailing_out = "%" if trailing == "퍼센트" else trailing
        return converted + trailing_out
    return _PLAIN_NUMBER_RE.sub(repl, text)


def fix_subtitle_text(text: str) -> str:
    """자막(subtitle) 필드에 섞여 들어온 narration용 한글 발음/숫자 표기를
    원래의 숫자·로마자 표기로 되돌립니다. narration 필드에는 절대 호출하지 마세요."""
    if not text or not isinstance(text, str):
        return text
    try:
        fixed = text
        for src, dst in _ACRONYM_SUBTITLE_FIXES:
            fixed = fixed.replace(src, dst)
        fixed = _fix_decimal_percent(fixed)
        fixed = _fix_plain_numbers(fixed)
        return fixed
    except Exception:
        return text


def fix_subtitle_fields(obj, key: str = None):
    """script.json 트리를 순회하며 narration 계열이 아닌 모든 문자열 필드에
    fix_subtitle_text()를 적용합니다."""
    if isinstance(obj, dict):
        return {k: fix_subtitle_fields(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_subtitle_fields(v, key) for v in obj]
    if isinstance(obj, str):
        if key in _NARRATION_ONLY_KEYS:
            return obj
        return fix_subtitle_text(obj)
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# 브리핑 데이터 수집 (v3 URL)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_briefing_data() -> dict:
    """UPSTREAM_REPO(stock-briefing-v3-1/-2)의 data/briefing_data.json을 가져온다.
    이 레포는 공개 GitHub Pages 사이트가 없으므로(v3와 달리 데이터 전용 백엔드),
    기존의 Playwright 라이브 사이트 스크래핑을 raw.githubusercontent.com 직접
    소비로 대체했다."""
    url = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/data/briefing_data.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ {UPSTREAM_REPO} briefing_data.json 로드 실패: {e}")
        return {}
def _call_json(system_prompt: str, user_content: str, max_tokens: int,
               temperature: float = 0.7, retries: int = 1, mock: dict = None) -> dict:
    """OpenAI Chat Completions를 호출해 JSON 객체를 반환합니다. 실패 시 1회 재시도.
    SCRIPT_MOCK=1이고 mock이 주어지면 API를 호출하지 않고 그 값을 그대로 반환한다."""
    if SCRIPT_MOCK and mock is not None:
        return mock
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            last_err = e
            print(f"  ⚠️ API 호출 실패(시도 {attempt + 1}/{retries + 1}): {e}")
    print(f"  ❌ API 호출 최종 실패: {last_err}")
    return {}


_NARRATION_SUBTITLE_RULES = """
## ★ narration vs subtitle 핵심 차이 (반드시 준수)

### narration/subtitle 문장 수 일치 (자막 동기화를 위해 반드시 준수)
- narration과 subtitle(및 narration_summary/subtitle_summary 등 모든 쌍)은 반드시 문장
  수가 동일해야 하고, 같은 순서로 같은 내용을 담아야 합니다. 표기(숫자/영문)만 다를 뿐
  내용과 문장 경계는 1:1로 대응해야 자막이 나레이션과 정확히 동기화됩니다.
- 문장 수를 맞추기 위해 임의로 문장을 합치거나 쪼개지 말고, 애초에 같은 문장 구조로
  narration과 subtitle을 나란히 작성하세요.

### [narration — TTS 낭독용]
- 모든 숫자를 한글로 풀어서 읽습니다:
  · 6,700 → 육천칠백  |  133만 → 백삼십삼만  |  12조2400억 → 십이조 이천사백억
  · 85,400원 → 팔만오천사백원  |  +1.2% → 플러스 일쩜이퍼센트
- 소수점은 반드시 **"쩜"** (절대 "점" 금지):
  · 12.5% → 십이쩜오퍼센트  |  0.8% → 영쩜팔퍼센트
- 영문 약어를 한글 발음으로:
  · SK→에스케이 | LG→엘지 | KB→케이비 | AI→에이아이 | HBM→에이치비엠
  · ETF→이티에프 | ESS→이에스에스 | PCE→피씨이 | DSR→디에스알 | OTT→오티티
  · KOSPI→코스피 | KOSDAQ→코스닥 | MOU→엠오유 | ADR→에이디알
- 경음화 규칙:
  · 주가→주까 | 목표주가→목표주까 | 유가→유까 | 고유가→고유까
  · 실적→실쩍 | 적자→적짜 | 특징→특찡 | 격차→격짜
  · 국채→국째 | 역대→역때 | 발전→발쩐 | 결정→결쩡 | 절감→절깜
  · 신고가→신고까 | 최고가→최고까 | 할 것→할 껏 | 볼 수→볼 쑤
- 삼성전기 → "삼성 전기" (TTS 오독 방지, 자막은 원래대로)
- 숫자+단위 붙여 읽기: 170만원→백칠십만원 (절대 "백칠십만 원" 금지)

### [subtitle — 화면 자막용] — 절대 규칙 (narration을 그대로 베끼지 말 것)
- 숫자는 반드시 아라비아 숫자 그대로 표기:
  · 6,700 (❌ 육천칠백)  |  3,500원 (❌ 삼천오백원)  |  1.2% (❌ 일쩜이퍼센트)
  · 12조2400억 (❌ 십이조 이천사백억)
- 영문 약어·기업명은 반드시 원래 로마자 표기 그대로:
  · SK (❌ 에스케이)  |  AI (❌ 에이아이)  |  OTT (❌ 오티티)  |  LG (❌ 엘지)
  · KB (❌ 케이비)  |  HBM (❌ 에이치비엠)  |  ETF (❌ 이티에프)
- narration 필드를 작성한 뒤 숫자·영문 부분을 한글 발음으로 바꿔 놓았다면, subtitle
  필드에는 그 발음 표기를 절대 복사하지 말고 반드시 원래 숫자·로마자로 다시 바꿔서 쓰세요.
- 뜻이 생소한 용어는 **(뜻)** 을 괄호 안에 병기:
  · HBM(고대역폭 메모리) | PER(주가수익비율) | DSR(총부채원리금상환비율)
  · MOU(업무협약) | ADR(미국주식예탁증서) | PCE(개인소비지출) | ESS(에너지저장장치) | OTT(온라인 동영상 서비스)
"""


SHORTS_OPENING_NARRATION = "오늘 증권사 리포트에서 주목한 핵심 종목, 빠르게 정리해 드립니다."
SHORTS_OPENING_SUBTITLE  = "오늘 증권사 리포트에서 주목한 핵심 종목, 빠르게 정리해 드립니다."
SHORTS_CLOSING_NARRATION = "자세한 내용은 정규 브리핑에서 확인하세요. 투자의 책임은 본인에게 있습니다."
SHORTS_CLOSING_SUBTITLE  = "자세한 내용은 정규 브리핑에서 확인하세요. 투자의 책임은 본인에게 있습니다."


# ── mid/full: 업데이트 스크립트 ──────────────────────────────────────────

def _mock_update_response(v3_2_data: dict) -> dict:
    recap    = v3_2_data.get("step1_recap", {}) or {}
    leaders  = recap.get("market_leaders", [])
    reaction = v3_2_data.get("morning_reaction", []) or []
    stocks   = ((v3_2_data.get("analyst_briefing") or {}).get("stocks", []))
    return {
        "recap": {
            "narration": f"[MOCK] 오늘 아침 {', '.join(leaders) or '주요 종목'}을 짚어드렸는데요. " * 2,
            "subtitle":  f"[MOCK] 오늘 아침 {', '.join(leaders) or '주요 종목'}을 짚어드렸는데요. " * 2,
        },
        "reaction": {
            "narration": ("[MOCK] 오전장 반응 더미 문장입니다. " * 3) if reaction else "",
            "subtitle":  ("[MOCK] 오전장 반응 더미 문장입니다. " * 3) if reaction else "",
        },
        "briefing_narration": "[MOCK] 증권사 리포트 더미 브리핑입니다. " * max(len(stocks), 1) * 2,
        "briefing_subtitle":  "[MOCK] 증권사 리포트 더미 브리핑입니다. " * max(len(stocks), 1) * 2,
        "strategy_narration": "[MOCK] 전략 업데이트 더미 문장입니다. " * 3,
        "strategy_subtitle":  "[MOCK] 전략 업데이트 더미 문장입니다. " * 3,
    }


_UPDATE_SYSTEM_PROMPT = """
너는 KBS 머니올라 "장중 업데이트" 방송 대본 작성 전문가입니다. 이 영상은
오늘 아침에 이미 나간 브리핑의 "2부"입니다 — 시장 요약이나 종목 선정 이유를
처음부터 다시 설명하지 말고, 아래 제공된 이미 분석된 내용(리캡 재료/오전장
반응/리포트 분석/전략 업데이트)을 방송 나레이션으로 자연스럽게 바꾸는 것이
당신의 역할입니다. 새로운 분석이나 숫자를 지어내지 마세요.

{rules}

## 섹션별 지침
1. recap: 30~40초 분량(narration 100~150자). "오늘 아침 브리핑에서 [종목명]을
   짚어드렸는데요" 식으로 맥락만 짚고, 내용을 다시 설명하지 마세요.
2. reaction: 오전장 반응 데이터가 있으면 2~3분 분량(narration 300~450자)으로
   "그때 이후 실제로 어떻게 움직였는지"를 서술하세요. 데이터가 없으면 빈
   문자열로 두세요.
3. briefing: 증권사 리포트 심화분석/섹터테마를 나레이션으로 재구성하세요.
   섹터 테마가 있으면 먼저 테마로 도입한 뒤 종목별로 이어가세요. 제공된
   analysis 내용 외의 사실을 새로 지어내지 마세요.
4. strategy: 아침 전략을 처음부터 다시 쓰지 말고 "무엇이 보강됐는지"
   중심으로 3~5문장으로 작성하세요.

## 출력 JSON 구조
{{
  "recap": {{"narration": "...", "subtitle": "..."}},
  "reaction": {{"narration": "...", "subtitle": "..."}},
  "briefing_narration": "...", "briefing_subtitle": "...",
  "strategy_narration": "...", "strategy_subtitle": "..."
}}
""".format(rules=_NARRATION_SUBTITLE_RULES)


def generate_update_script(v3_2_data: dict, length_tier: str) -> dict:
    """mid/full 티어 스크립트 생성 — STEP-1 위에 얹은 새 정보를 나레이션으로
    변환하는 단일 호출. V3_2가 이미 분석을 끝내놨으므로(리캡/반응/리포트
    심화분석/전략업데이트), 옛 generate_script()처럼 여러 번 나눠 호출하며
    처음부터 분석할 필요가 없다."""
    recap        = v3_2_data.get("step1_recap", {}) or {}
    reaction     = v3_2_data.get("morning_reaction", []) or []
    briefing     = v3_2_data.get("analyst_briefing", {}) or {}
    strategy_upd = v3_2_data.get("ai_strategy_update", "") or ""

    user_content = (
        f"## 길이 티어: {length_tier} (mid=5~8분, full=8~15분)\n\n"
        f"## STEP-1 리캡 재료\n{json.dumps(recap, ensure_ascii=False, indent=2)}\n\n"
        f"## 오전장 반응 데이터\n{json.dumps(reaction, ensure_ascii=False, indent=2)}\n\n"
        f"## 증권사 리포트 분석\n{json.dumps(briefing, ensure_ascii=False, indent=2)}\n\n"
        f"## AI전략 업데이트 원문\n{strategy_upd}\n"
    )

    data = _call_json(
        _UPDATE_SYSTEM_PROMPT, user_content, max_tokens=6000,
        mock=_mock_update_response(v3_2_data) if SCRIPT_MOCK else None,
    ) or {}

    sections = [{
        "id": "opening", "label": "오프닝",
        "narration": OPENING_NARRATION, "subtitle": OPENING_SUBTITLE,
        "keywords": recap.get("market_leaders", [])[:4],
    }]

    recap_data = data.get("recap", {}) or {}
    if recap_data.get("narration"):
        items = []
        for label, names in (
            ("대형주도주", recap.get("market_leaders", [])),
            ("관심종목",   recap.get("stocks", [])),
            ("오늘의 픽",  recap.get("hidden_picks", [])),
        ):
            if names:
                items.append({"name": label, "text": ", ".join(names)})
        sections.append({
            "id": "recap", "label": "리캡",
            "corner_summary": "오늘 아침 브리핑 리캡",
            "narration": recap_data.get("narration", ""),
            "subtitle":  recap_data.get("subtitle", recap_data.get("narration", "")),
            "items": items,
        })

    reaction_data = data.get("reaction", {}) or {}
    if reaction and reaction_data.get("narration"):
        items = [
            {
                "name": r.get("name", ""),
                "text": (
                    f"{r.get('step1_price', 0):,}원({r.get('step1_change_pct', 0):+.2f}%) → "
                    f"{r.get('morning_price', 0):,}원({r.get('morning_change_pct', 0):+.2f}%)"
                ),
            }
            for r in reaction
        ]
        sections.append({
            "id": "reaction", "label": "오전장 반응",
            "corner_summary": "오전장 반응 업데이트",
            "narration": reaction_data.get("narration", ""),
            "subtitle":  reaction_data.get("subtitle", reaction_data.get("narration", "")),
            "items": items,
        })

    briefing_narration = data.get("briefing_narration", "")
    if briefing_narration:
        items = []
        for t in briefing.get("sector_themes", []) or []:
            items.append({"name": f"🎯 {t.get('sector', '')}", "text": t.get("narrative", "")})
        for s in briefing.get("stocks", []) or []:
            brokers = s.get("brokers", [])
            brokers_str = ", ".join(brokers) if isinstance(brokers, list) else str(brokers)
            items.append({"name": s.get("name", ""), "text": f"({brokers_str}) {s.get('analysis', '')}"})
        sections.append({
            "id": "briefing", "label": "증권사 리포트 브리핑",
            "corner_summary": "오늘의 증권사 리포트",
            "narration": briefing_narration,
            "subtitle":  data.get("briefing_subtitle", briefing_narration),
            "items": items,
        })

    strategy_narration = data.get("strategy_narration", "")
    strategy_subtitle  = data.get("strategy_subtitle", strategy_narration)
    if strategy_narration:
        if length_tier == "full":
            sections.append({
                "id": "ai_strategy", "label": "AI전략 업데이트",
                "corner_summary": "오늘 아침 전략, 이렇게 업데이트합니다",
                "narration": strategy_narration,
                "subtitle":  strategy_subtitle,
                "bullet_points": [strategy_narration],
            })
        else:
            # mid 티어는 전략 업데이트를 한 문장으로 축약해 짧게 유지한다
            # ("길이 전략" 설계 결정 — mid는 리캡+반응+리포트가 핵심, 전략은 요약만).
            first_sentence = strategy_narration.split(". ")[0].strip()
            if first_sentence and not first_sentence.endswith("."):
                first_sentence += "."
            first_subtitle_sentence = strategy_subtitle.split(". ")[0].strip()
            if first_subtitle_sentence and not first_subtitle_sentence.endswith("."):
                first_subtitle_sentence += "."
            sections.append({
                "id": "ai_strategy", "label": "AI전략 업데이트",
                "corner_summary": "전략 업데이트 한 줄",
                "narration": first_sentence,
                "subtitle":  first_subtitle_sentence or first_sentence,
                "bullet_points": [first_sentence],
            })

    sections.append({
        "id": "closing", "label": "클로징",
        "narration": CLOSING_NARRATION, "subtitle": CLOSING_SUBTITLE,
        "disclaimer": DISCLAIMER,
    })

    result = {
        "title": f"{TODAY} 장중 업데이트",
        "date": TODAY,
        "video_format": length_tier,
        "sections": sections,
    }
    result = fix_subtitle_fields(result)

    total_chars = sum(len(s.get("narration", "") or "") for s in sections)
    print(f"\n📏 장중 업데이트 나레이션 글자 수 합계: {total_chars:,}자 (티어: {length_tier})")
    return result


# ── shorts: 리포트 하이라이트만 ──────────────────────────────────────────

def _mock_shorts_v2(briefing: dict) -> dict:
    names = [s.get("name", "") for s in (briefing.get("stocks") or [])][:2] or ["[MOCK]종목"]
    narration = "증권사 리포트에서는 " + ", ".join(names) + "에 대한 더미 하이라이트를 다룹니다."
    return {"narration": narration, "subtitle": narration}


_SHORTS_SYSTEM_PROMPT = """
너는 KBS 머니올라 주식 쇼츠 스크립트 작성 전문가입니다. 30~50초 분량의 짧은
쇼츠 영상에 들어갈 "오늘 증권사 리포트 하이라이트" 문단 하나만 작성하세요.
작성일: {today}

{rules}

## ★ 분량 요구사항
- narration 150~220자 내외(공백 포함). "증권사 리포트에서는"으로 자연스럽게
  시작하고, 오늘 리포트에 나온 핵심 종목·의견·목표주가 중 가장 눈에 띄는
  내용 1~2개만 짧고 임팩트 있게 전달하세요. 나열하지 말고 임팩트 있는
  핵심 한두 가지에 집중하세요.

## 출력 JSON 구조
{{"narration": "...", "subtitle": "..."}}
"""


def generate_shorts_script(v3_2_data: dict) -> dict:
    """길이티어 "shorts"용 — 리포트 핵심종목이 적을 때(5개 미만) 30~50초
    하이라이트 하나만 만든다."""
    briefing = v3_2_data.get("analyst_briefing", {}) or {}

    system_prompt = _SHORTS_SYSTEM_PROMPT.format(today=TODAY, rules=_NARRATION_SUBTITLE_RULES)
    user_content = f"## 오늘 증권사 리포트 심화분석\n{json.dumps(briefing, ensure_ascii=False, indent=2)}"

    data = _call_json(
        system_prompt, user_content, max_tokens=1500,
        mock=_mock_shorts_v2(briefing) if SCRIPT_MOCK else None,
    ) or {}
    highlight_narration = data.get("narration", "").strip()
    highlight_subtitle  = data.get("subtitle", highlight_narration).strip()

    sections = [
        {"id": "opening", "label": "오프닝",
         "narration": SHORTS_OPENING_NARRATION, "subtitle": SHORTS_OPENING_SUBTITLE, "keywords": []},
        {"id": "highlight", "label": "증권사 리포트 하이라이트",
         "corner_summary": "오늘의 증권사 리포트 하이라이트",
         "narration": highlight_narration, "subtitle": highlight_subtitle},
        {"id": "closing", "label": "클로징",
         "narration": SHORTS_CLOSING_NARRATION, "subtitle": SHORTS_CLOSING_SUBTITLE,
         "disclaimer": DISCLAIMER},
    ]
    result = {"title": f"{TODAY} 증권사 리포트 속보", "date": TODAY, "video_format": "shorts", "sections": sections}
    result = fix_subtitle_fields(result)

    total_chars = len(highlight_narration)
    print(f"\n📏 shorts 하이라이트 글자 수: {total_chars:,}자 (목표: 150~220자, 약 30~50초)")
    return result


# ─────────────────────────────────────────────────────────────────────────────

def run(lang: str = "KO"):
    global TODAY
    lang = lang.upper()

    v3_2_data = fetch_briefing_data()
    if not v3_2_data:
        print(f"❌ {UPSTREAM_REPO}의 briefing_data.json을 가져오지 못했습니다. 종료합니다.")
        sys.exit(1)

    briefing_date_str = v3_2_data.get("briefing_date", "")
    if briefing_date_str:
        # 시스템 실행 시각(TODAY) 대신 실제 브리핑이 다루는 날짜를 사용 — 워크플로우가
        # 조기 실행되어 전날 데이터로 생성되더라도 영상에는 데이터 기준 날짜가 정확히 표시된다.
        TODAY = briefing_date_str
        print(f"📅 브리핑 날짜: {TODAY} (V3_2 데이터 기준)")

    length_tier = v3_2_data.get("length_tier", "shorts")
    print(f"🎯 길이 티어: {length_tier} (V3_2가 이미 결정 — 여기서 재계산하지 않음)")

    if length_tier == "shorts":
        script = generate_shorts_script(v3_2_data)
    else:
        script = generate_update_script(v3_2_data, length_tier)

    root     = os.path.join(_HERE, "..")
    out_dir  = os.path.join(root, "output", lang, "scripts")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "script.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    sections = script.get("sections", [])
    print(f"\n✅ 스크립트 생성 완료! 섹션 수: {len(sections)}개 → {out_path}")
    return script


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "KO"
    run(lang)
