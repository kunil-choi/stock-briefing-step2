# stock-briefing-step2 — report_update

📺 **[stock-briefing-video](https://github.com/kunil-choi/stock-briefing-video)**를
1일 2개 영상 파이프라인(morning_core / report_update)으로 분리한 것 중
**report_update**(장중 업데이트, 09:20~10:20 KST, 증권사 리포트+오전장 반영)
담당 레포입니다.

## 데이터 소스 & 설계 원칙 (재설계: "1부/2부 연속 시리즈")

**[stock-briefing-v3-2](https://github.com/kunil-choi/stock-briefing-v3-2)**의
`data/briefing_data.json`을 `raw.githubusercontent.com`으로 직접 소비합니다
(`UPSTREAM_REPO = stock-briefing-v3-2`).

**설계 원칙**: STEP-1(morning_core)과 STEP-2(report_update)는 "각자 완결된
브리핑"이 아니라 "하루짜리 연속 시리즈의 1부/2부"다. 예전에는 V3_2가 종목선정을
처음부터 다시 해서 STEP-2가 STEP-1과 상당 부분 겹치는 "재브리핑"이 되는 문제가
있었다. 지금은 V3_2가 STEP-1 결과물 위에 새 정보(오전장 반응/증권사 리포트
심화분석/AI전략 업데이트)만 얹어 내려주므로, 이 레포는 그 내용을 **처음부터
재분석하지 않고 방송 나레이션으로 변환하기만 한다** (`generate_script.py`의
`generate_update_script()`).

## 3단계 길이 티어 (`shorts` / `mid` / `full`)

고정 15분 목표는 폐기하고, 리포트 볼륨에 비례한 가변 길이를 쓴다. 티어 결정
자체는 **이 레포가 아니라 V3_2**(`decide_length_tier()`, 리포트 핵심종목 수
기준)가 먼저 끝내서 `briefing_data.json`의 `length_tier` 필드로 내려주고,
이 레포는 그 값을 그대로 신뢰해 사용할 뿐 재계산하지 않는다(옛
`pipeline/report_decision.py`는 삭제됨).

| 티어 | 핵심종목 수 | 목표 길이 | 구성 |
|---|---|---|---|
| `shorts` | 5개 미만 | 30~60초 | 오프닝 + 리포트 하이라이트 1문단 + 클로징 |
| `mid`    | 5~14개   | 5~8분    | 오프닝 + 리캡 + 오전장 반응 + 리포트 브리핑 + 전략 업데이트(1문장 축약) + 클로징 |
| `full`   | 15개 이상 | 8~15분   | mid와 동일 + 전략 업데이트 전체 |

`pipeline/generate_script.py`의 `run()`이 `script.json`의 `video_format`
필드에 이 값을 그대로 기록하고, 이후 모든 단계(`generate_assets.py`,
`generate_video.py`, `generate_metadata.py`, `quality_gate.py`, 워크플로우의
TTS/길이 검증)가 이 값을 읽어 분기합니다.

> ⚠️ mid/full 경로는 이번 재설계에서 새로 추가된 코드라 실제 GitHub Actions
> 환경에서의 종단간 검증 횟수가 적습니다. 처음 실행될 때 워크플로우 로그와
> 산출물을 한 번 직접 확인해보시는 걸 권장합니다.

## 트리거 체인

```
(수동) workflow_dispatch → report_update.yml
  script (V3_2가 결정한 length_tier 그대로 사용) → voice / assets → video → generate_metadata.py → quality_gate.py
```

과금(OpenAI/TTS) 방지를 위해 `stock-briefing-v3-2`의 자동 dispatch를 제거했습니다.
`stock-briefing-v3-2`의 `docs/index.html`로 데이터가 준비됐는지 사람이 먼저 확인한
뒤, 이 레포 Actions 탭에서 수동으로 `workflow_dispatch`를 실행하세요. 자체 cron도
없습니다.

## 신규 구성 요소 (`stock-briefing-step1` 대비 추가/변경)

| 파일 | 역할 |
|---|---|
| `config/schedule.yml` | `briefing_type: report_update`, 실행 창(09:20~10:20), `duration.{shorts,mid,full}` |
| `pipeline/generate_script.py` | `UPSTREAM_REPO`를 V3_2로 변경. STEP-1 재브리핑용 다중 호출 파이프라인(`_generate_core`/`_generate_stock_section` 등, 옛 스키마 전용)을 전부 제거하고 `generate_update_script()`(mid/full, 단일 호출) + `generate_shorts_script()`(신규 스키마용으로 교체)로 재작성 |
| `pipeline/assets/builders.py`의 `build_recap()`/`build_reaction()`/`build_report_briefing()` | 리캡/오전장반응/리포트브리핑 슬라이드(신규, 기존 `_build_aggregate_stock_slide()` 재사용) |
| `pipeline/generate_assets.py` | 옛 롱폼 빌더(시장요약/섹터/종목카드) 호출 제거, mid/full은 recap→reaction→briefing→(full만)ai_strategy 순으로 렌더링 |
| `pipeline/generate_subtitles.py`, `pipeline/generate_video.py` | 프레임→오디오 ID 매핑 테이블에 `02_recap`/`03_reaction`/`04_briefing` 패턴 추가 |
| `pipeline/generate_metadata.py` | `TITLE_TEMPLATES`에 `report_update_mid` 추가, `report_update_longform` → `report_update_full`로 정정(안 그러면 mid/full 둘 다 morning_core 제목으로 폴백되는 버그) |
| `.github/workflows/report_update.yml` | `script` job이 V3_2가 결정한 `video_format`(shorts/mid/full)을 감지해 `voice`(TTS 최소 개수 3/4/6)·`video`(목표 길이) job에 전달 |

`pipeline/report_decision.py`는 삭제됐습니다(티어 결정이 V3_2로 이동).
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
