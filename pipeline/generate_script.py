# pipeline/generate_script.py
"""
AI 주식 브리핑 — report_update(STEP-2) 스크립트 생성 모듈

재설계(2차): 이 레포는 이제 "증권사 리포트 종합"만 다루는 고정 길이
미드폼이다. 예전 재설계("1부/2부 연속 시리즈")에서 남아있던 리캡/오전장
반응/AI전략 업데이트 섹션은 전부 제거했다 — 이유:
  1) 콘텐츠 범위를 증권사 리포트 종합 하나로 좁혀 STEP-1(관심종목)과 명확히
     구분되는 콘텐츠 축을 만든다(둘 다 "종합 브리핑"이면 시청 포인트가
     겹친다).
  2) "AI전략 업데이트"(AI가 종목별로 자체 판단한 투자 전략을 제안하는 형식)는
     한국 자본시장법상 유사투자자문업 소지가 있어 제거했다 — 이 레포가 하는
     일은 "누가 뭐라고 말했는지 사실을 종합·전달"하는 것으로 한정한다.
  3) 리포트 핵심종목 수에 따라 30초~15분을 오가던 3단계 가변 길이 티어를
     폐기하고 5~8분 고정 미드폼으로 통일했다 — 매일 길이가 들쭉날쭉하면
     유튜브 알고리즘의 시청자 습관 학습(추천 신호)과 시청자의 "이 정도면
     보겠다"는 사전 판단이 둘 다 흐려진다.

- 데이터 소스: stock-briefing-v3-2의 data/briefing_data.json
  (raw.githubusercontent.com) — 이 중 증권사 리포트 분석(analyst_briefing)만
  사용한다. step1_recap/morning_reaction/ai_strategy_update는 더 이상 읽지
  않는다.
- 목표 영상 길이: 5~8분 고정(config/schedule.yml의 duration)
- 오프닝: 정적 인사말이 아니라, 오늘 리포트에서 가장 눈에 띄는 사실 하나로
  바로 치고 들어가는 데이터 기반 훅(주목도를 높이기 위한 설계 — 유튜브는
  처음 몇 초 이탈률이 노출에 직접 영향을 준다).
- 발음 교정 / 나레이션·자막 완전 분리
- 목소리 관리: pipeline/voice_config.py 에서 통합 관리 (ElevenLabs 클론
  음성 — pipeline/generate_voice.py가 provider 폴백 체인으로 합성)
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
# quality_gate)를 토큰 소비 없이 로컬에서 먼저 검증하기 위함.
SCRIPT_MOCK = os.environ.get("SCRIPT_MOCK") == "1"

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key and not SCRIPT_MOCK:
    raise EnvironmentError("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
client = OpenAI(api_key=_api_key or "sk-mock-dry-run")

# report_update는 stock-briefing-v3-2(증권사 리포트+오전장 반영 스냅샷)를 소비한다.
UPSTREAM_REPO = "kunil-choi/stock-briefing-v3-2"

TODAY       = datetime.now().strftime("%Y년 %m월 %d일")

# ─────────────────────────────────────────────────────────────────────────────
# 클로징 멘트 (투자 경고 고정 문구 — 창작 요소 없이 항상 동일하게 유지)
# ─────────────────────────────────────────────────────────────────────────────

CLOSING_NARRATION = (
    "이상으로 케이비에스 머니올라의 증권사 리포트 브리핑을 마치겠습니다. "
    "오늘도 함께해 주셔서 감사합니다. "
    "마지막으로 꼭 당부드릴 말씀이 있습니다. "
    "본 브리핑은 에이아이가 뉴스, 유튜브, 증권사 리포트 등 공개 데이터를 분석하여 제작한 참고용 정보입니다. "
    "특정 종목의 매수 또는 매도를 권유하는 것이 아니며, 수익을 보장하지 않습니다. "
    "주식 투자는 원금 손실의 위험이 있으므로 반드시 본인의 판단과 책임 하에 신중하게 결정하시기 바랍니다. "
    "투자의 최종 결정과 그에 따른 모든 책임은 전적으로 투자자 본인에게 있습니다. "
    "구독과 좋아요는 저희에게 큰 힘이 됩니다. 내일도 유익한 브리핑으로 찾아뵙겠습니다. 감사합니다."
)

CLOSING_SUBTITLE = (
    "이상으로 KBS 머니올라의 증권사 리포트 브리핑을 마치겠습니다. "
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
# ─────────────────────────────────────────────────────────────────────────────

_NARRATION_ONLY_KEYS = {"narration", "narration_summary", "id", "title", "date"}

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

_NUMBER_RUN_DENYLIST = {"구조"}


def _fix_plain_numbers(text: str) -> str:
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
# 브리핑 데이터 수집 (v3-2 URL)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_briefing_data() -> dict:
    """UPSTREAM_REPO(stock-briefing-v3-2)의 data/briefing_data.json을 가져온다."""
    url = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/data/briefing_data.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ {UPSTREAM_REPO} briefing_data.json 로드 실패: {e}")
        return {}


def _call_json(system_prompt: str, user_content: str, max_tokens: int,
               temperature: float = 0.7, retries: int = 1, mock: dict = None) -> dict:
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
- narration과 subtitle은 반드시 문장 수가 동일해야 하고, 같은 순서로 같은
  내용을 담아야 합니다. 표기(숫자/영문)만 다를 뿐 내용과 문장 경계는 1:1로
  대응해야 자막이 나레이션과 정확히 동기화됩니다.

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


# ── 증권사 리포트 종합 (고정 미드폼, 단일 호출) ──────────────────────────

def _mock_report_response(briefing: dict) -> dict:
    stocks = briefing.get("stocks", []) or []
    names = [s.get("name", "") for s in stocks][:3] or ["[MOCK]종목"]
    hook = f"[MOCK] 오늘 증권사 리포트에서 가장 주목받은 종목은 {names[0]}였습니다."
    body = "[MOCK] 증권사 리포트 종합 더미 브리핑입니다. " * max(len(stocks), 1) * 3
    return {
        "hook_narration": hook, "hook_subtitle": hook,
        "briefing_narration": body, "briefing_subtitle": body,
    }


_REPORT_SYSTEM_PROMPT = """
너는 KBS 머니올라 "증권사 리포트 브리핑" 방송 대본 작성 전문가입니다. 이
영상은 오늘 나온 증권사 리포트를 종합해서 알려주는 5~8분 분량의 미드폼
콘텐츠입니다. 시장 요약이나 종목 선정 이유를 처음부터 분석하지 말고, 아래
제공된 증권사 리포트 심화분석 데이터(이미 분석 완료됨)를 방송 나레이션으로
자연스럽게 바꾸는 것이 당신의 역할입니다. 새로운 분석이나 숫자를 지어내지
마세요.

## ★ 역할 한정 (중요)
당신은 "누가 뭐라고 말했는지 사실을 종합·전달"하는 역할만 합니다. AI 스스로
투자 전략을 제안하거나 "이렇게 하세요"식 조언을 만들어내지 마세요. 항상
"OO증권은 ~라고 밝혔다", "~라는 분석이 나왔다"처럼 출처를 주어로 문장을
구성하세요.

{rules}

## 섹션별 지침
1. hook(오프닝 훅, 15~25초 분량, narration 60~100자): 인사말이나 일반적인
   소개로 시작하지 말고, 오늘 증권사 리포트 중 가장 눈에 띄는 사실
   하나(가장 큰 목표주가 상향, 가장 많이 언급된 종목, 가장 파격적인 의견
   변화 등)로 바로 시작해서 시청자의 주의를 즉시 붙잡으세요. "오늘
   증권사 리포트에서는" 같은 밋밋한 도입이 아니라, 구체적 종목명과 숫자가
   첫 문장에 바로 나와야 합니다.
2. briefing(본편, 4~7분 분량, narration 1600~2400자): 증권사 리포트
   심화분석·섹터테마를 나레이션으로 재구성하세요. 섹터 테마가 있으면 먼저
   테마로 도입한 뒤 종목별로 이어가세요. category가 "single_significant"인
   종목은 "오늘의 픽"으로 소개하듯 자연스럽게 강조하세요. ★ 핵심종목 수가
   적은 날에는 문장을 억지로 늘리지 말고, 종목별로 업종 맥락·비교 종목·최근
   추세처럼 제공된 데이터 안에서 더 깊이 있게 설명해 자연스럽게 분량을
   채우세요(없는 사실을 지어내는 것은 금지).

## 출력 JSON 구조
{{
  "hook_narration": "...", "hook_subtitle": "...",
  "briefing_narration": "...", "briefing_subtitle": "..."
}}
""".format(rules=_NARRATION_SUBTITLE_RULES)


def generate_report_script(v3_2_data: dict) -> dict:
    """증권사 리포트 종합만 다루는 고정 미드폼(5~8분) 스크립트를 생성한다."""
    briefing = v3_2_data.get("analyst_briefing", {}) or {}

    user_content = f"## 증권사 리포트 분석\n{json.dumps(briefing, ensure_ascii=False, indent=2)}\n"

    data = _call_json(
        _REPORT_SYSTEM_PROMPT, user_content, max_tokens=6000,
        mock=_mock_report_response(briefing) if SCRIPT_MOCK else None,
    ) or {}

    hook_narration = data.get("hook_narration", "").strip()
    hook_subtitle  = data.get("hook_subtitle", hook_narration).strip()

    # 오프닝 훅에 등장하는 종목명을 opening.keywords로도 남겨, 오프닝 화면의
    # 배경 사진(연합뉴스/KBS 검색 키워드)로 재사용한다(pipeline/generate_media.py).
    stock_names = [s.get("name", "") for s in (briefing.get("stocks") or []) if s.get("name")]

    sections = [{
        "id": "opening", "label": "오프닝",
        "narration": hook_narration or "오늘 증권사 리포트, 지금 바로 확인하세요.",
        "subtitle":  hook_subtitle or hook_narration,
        "keywords": stock_names[:4],
    }]

    briefing_narration = data.get("briefing_narration", "")
    if briefing_narration:
        items = []
        for t in briefing.get("sector_themes", []) or []:
            items.append({"name": f"🎯 {t.get('sector', '')}", "text": t.get("narrative", "")})
        for s in briefing.get("stocks", []) or []:
            brokers = s.get("brokers", [])
            brokers_str = ", ".join(brokers) if isinstance(brokers, list) else str(brokers)
            name = s.get("name", "")
            if s.get("category") == "single_significant":
                name = f"💎 오늘의 픽 — {name}"
            items.append({"name": name, "text": f"({brokers_str}) {s.get('analysis', '')}"})
        sections.append({
            "id": "briefing", "label": "증권사 리포트 브리핑",
            "corner_summary": "오늘의 증권사 리포트",
            "narration": briefing_narration,
            "subtitle":  data.get("briefing_subtitle", briefing_narration),
            "items": items,
        })

    sections.append({
        "id": "closing", "label": "클로징",
        "narration": CLOSING_NARRATION, "subtitle": CLOSING_SUBTITLE,
        "disclaimer": DISCLAIMER,
    })

    result = {
        "title": f"{TODAY} 증권사 리포트 브리핑",
        "date": TODAY,
        "sections": sections,
    }
    result = fix_subtitle_fields(result)

    total_chars = sum(len(s.get("narration", "") or "") for s in sections)
    print(f"\n📏 리포트 브리핑 나레이션 글자 수 합계: {total_chars:,}자 (목표: 5~8분 고정)")
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
        TODAY = briefing_date_str
        print(f"📅 브리핑 날짜: {TODAY} (V3_2 데이터 기준)")

    script = generate_report_script(v3_2_data)

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
