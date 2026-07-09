# stock-briefing-step2 — report_update

📺 **[stock-briefing-video](https://github.com/kunil-choi/stock-briefing-video)**를
1일 2개 영상 파이프라인(morning_core / report_update)으로 분리한 것 중
**report_update**(장중 업데이트, 09:20~10:20 KST, 증권사 리포트+오전장 반영)
담당 레포입니다.

## 데이터 소스

**[stock-briefing-v3-2](https://github.com/kunil-choi/stock-briefing-v3-2)**의
`data/briefing_data.json`을 `raw.githubusercontent.com`으로 직접 소비합니다
(`stock-briefing-step1`과 동일한 `fetch_briefing_data()`/`build_briefing_text()`
구조, `UPSTREAM_REPO`만 다름). V3_2는 애널리스트 리포트 수집 + 오전장 반영
현재가까지 포함된 스냅샷을 발행하므로, 이 레포에서 별도 수집 없이 그대로
사용합니다.

## 조건부 롱폼/쇼츠 (`pipeline/report_decision.py`)

요구사항: *"리포트 핵심 종목 수가 5개 미만이거나 신규성이 낮으면 롱폼 대신
쇼츠/커뮤니티용 요약만 생성한다."*

- `count_core_stocks(brokerage_reports)` — simultaneous/new_coverage/
  single_significant에 등장한 종목명을 중복 제거해 카운트.
- `is_low_novelty(brokerage_reports)` — Phase 1 휴리스틱:
  `new_coverage == 0 and simultaneous <= 1`이면 "신규성 낮음". (더 정교한
  `ranking_score` 기반 판단은 후속 단계에서 교체 예정.)
- `decide_video_format()` → `"longform"` 또는 `"shorts"`.

`pipeline/generate_script.py`의 `run()`이 이 값을 매 실행마다 계산해
`script.json`의 `video_format` 필드에 기록하고, 이후 모든 단계
(`generate_assets.py`, `generate_video.py`, `generate_metadata.py`,
`quality_gate.py`, 워크플로우의 TTS/길이 검증)가 이 값을 읽어 분기합니다.

- **longform**: 기존 `stock-briefing-video`와 동일한 다중 섹션 구조
  (시장요약/업종분석/종목별 상세/집계 섹션/AI전략), 목표 13~20분.
- **shorts**: `generate_shorts_script()`가 단일 LLM 호출로 만드는 3섹션
  (`opening` / `highlight` / `closing`)짜리 축소 스크립트, 목표 30~60초.
  렌더링은 `pipeline/assets/builders.build_shorts_highlight()`가 담당하며,
  `generate_assets.py`가 `video_format=="shorts"`일 때 market_summary/
  sector/종목카드/AI전략 빌더 호출을 건너뜁니다.

> ⚠️ shorts 경로는 이번 구현에서 새로 추가된 코드라 longform 대비 실제
> GitHub Actions 환경에서의 종단간 검증 횟수가 적습니다. 처음 shorts로
> 분기되는 날은 워크플로우 로그와 산출물을 한 번 직접 확인해보시는 걸
> 권장합니다.

## 트리거 체인

```
stock-briefing-v3-2 완료 → workflow_dispatch → report_update.yml
  script (video_format 결정) → voice / assets → video → generate_metadata.py → quality_gate.py
```

자체 cron은 없습니다(V3_2가 끝나기 전에 실행되면 날짜 불일치 위험).

## 신규 구성 요소 (`stock-briefing-step1` 대비 추가/변경)

| 파일 | 역할 |
|---|---|
| `config/schedule.yml` | `briefing_type: report_update`, 실행 창(09:20~10:20), `report_decision.min_core_stocks: 5` |
| `pipeline/report_decision.py` | video_format 결정 로직 (신규) |
| `pipeline/generate_script.py` | `UPSTREAM_REPO`를 V3_2로 변경, `generate_shorts_script()` 추가, `run()`에 video_format 분기 추가 |
| `pipeline/assets/builders.py`의 `build_shorts_highlight()` | shorts 전용 단일 슬라이드 렌더링(추가된 함수) |
| `pipeline/generate_assets.py` | `video_format=="shorts"`일 때 롱폼 전용 빌더 호출 스킵 |
| `pipeline/generate_subtitles.py`, `pipeline/generate_video.py`, `pipeline/quality_gate.py` | 프레임→오디오 ID 매핑 테이블에 `05_highlight → highlight` 패턴 추가 |
| `pipeline/generate_metadata.py` | `video_format`을 script.json에서 동적으로 읽도록 변경(정적 설정값이 아님) — 제목/썸네일/오프닝 문구가 morning_core와 겹치지 않도록 `TITLE_TEMPLATES`가 `briefing_type`별로 분리돼 있음 |
| `.github/workflows/report_update.yml` | `workflow_dispatch`만 사용, `script` job이 감지한 `video_format`을 `voice`(TTS 최소 개수)/`video`(목표 길이) job에 전달 |

그 외 파일은 `stock-briefing-step1`에서 무수정 복사했습니다.

## 산출물

```
output/YYYY-MM-DD/
  metadata.json   # video_format: "longform" | "shorts"
  final.mp4
  thumbnail.png
  script.json
```

`metadata.json` 스키마는 `stock-briefing-step1`과 동일하되 `video_format`이
매 실행마다 달라질 수 있습니다.

## 실패 시 fallback

- `stock-briefing-v3-2`의 `briefing_data.json`을 못 가져오면 즉시 종료(exit 1).
- shorts 분기든 longform 분기든 `generate_metadata.py`의 fallback 동작은
  `stock-briefing-step1`과 동일합니다(README 참고).

## 필요 Secrets

| Secret | 용도 |
|---|---|
| `OPENAI_API_KEY` | 스크립트/TTS 생성 |

## 로컬 실행

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python pipeline/generate_script.py KO   # video_format을 콘솔에 출력함
python pipeline/generate_voice.py KO
python pipeline/generate_assets.py KO
python pipeline/generate_subtitles.py KO
TARGET_MIN_SECONDS=30 TARGET_MAX_SECONDS=60 python pipeline/generate_video.py KO   # shorts일 때
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

## 다음 단계 (이번 범위 아님)

`stock-briefing-step1`의 README와 동일 — 개체명 추출/scene_plan.json, 미디어
검색 파이프라인, 방송형 렌더러 고도화, "증권사 리포트 검증형" 내러티브 플롯,
프리미엄 TTS는 이번 범위에 없고 후속 설계·구현 대상입니다.
