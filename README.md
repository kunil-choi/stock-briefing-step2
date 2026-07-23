# stock-briefing-step2 — report_update

📺 **[stock-briefing-video](https://github.com/kunil-choi/stock-briefing-video)**를
1일 2개 영상 파이프라인(morning_core / report_update)으로 분리한 것 중
**report_update**(장중 업데이트, 09:20~10:20 KST, 증권사 리포트 종합)
담당 레포입니다.

## 데이터 소스 & 콘텐츠 범위 (재설계: 증권사 리포트 종합 전용)

**[stock-briefing-v3-2](https://github.com/kunil-choi/stock-briefing-v3-2)**의
`data/briefing_data.json`을 `raw.githubusercontent.com`으로 직접 소비하되,
이 중 `analyst_briefing`(증권사 리포트 심화분석)만 사용합니다.

**설계 원칙**: STEP-1(morning_core, 유튜브 언급 관심종목)과 STEP-2
(report_update, 증권사 리포트 종합)는 서로 다른 콘텐츠 축을 다루는 별개
영상이다. 예전 재설계("1부/2부 연속 시리즈")에서는 이 레포가 STEP-1
리캡·오전장 반응·AI전략 업데이트까지 함께 다뤘는데, 두 가지 이유로 폐기했다:

1. STEP-1과 콘텐츠가 겹쳐 시청 포인트가 흐려진다 — 콘텐츠 범위를 "오늘 나온
   증권사 리포트 종합"으로 좁혀 STEP-1과 명확히 구분되는 축으로 만들었다.
2. "AI전략 업데이트"(AI가 종목별로 자체 판단한 투자 전략을 제안하는 형식)는
   한국 자본시장법상 유사투자자문업 소지가 있어 제거했다. 이 레포는 "누가
   뭐라고 말했는지 사실을 종합·전달"하는 역할로 한정한다
   (`pipeline/generate_script.py`의 `_REPORT_SYSTEM_PROMPT` 참고 — AI 스스로
   투자 조언을 만들지 않고 항상 "OO증권은 ~라고 밝혔다" 형태로 문장을 구성).

## 고정 미드폼 (가변 길이 티어 폐기)

리포트 핵심종목 수에 따라 30초~15분을 오가던 3단계 가변 길이 티어
(`shorts`/`mid`/`full`)를 폐기하고 **5~8분 고정**으로 통일했다
(`config/schedule.yml`의 `duration`). 매일 길이가 들쭉날쭉하면 유튜브
알고리즘의 시청자 습관 학습(추천 신호)과 시청자의 "이 정도면 보겠다"는
사전 판단이 둘 다 흐려진다는 판단. 리포트가 적은 날에도 30초로 축소하지
않고, `generate_script.py`가 종목별 설명(업종 맥락/비교 종목/추세)을 더
깊게 다뤄 분량을 자연스럽게 채우도록 프롬프트에 명시했다(없는 사실을
지어내는 필러는 금지).

## 오프닝 훅 (주목도)

`OPENING_NARRATION` 같은 고정 인사말 대신, LLM이 오늘 리포트에서 가장
눈에 띄는 사실 하나(가장 큰 목표주가 상향, 가장 파격적인 의견 변화 등)로
바로 시작하는 **동적 훅**을 만든다(`generate_report_script()`의
`hook_narration`). 화면도 텍스트 카드가 아니라 그 종목의 연합뉴스/KBS
사진을 전체화면 배경으로 깐다(아래 미디어 섹션 참고) — 첫 화면부터
"방송사가 만든 콘텐츠"라는 인상을 주기 위함.

## 클론 음성 (ElevenLabs)

`stock-briefing-step1`의 프리미엄 TTS provider 폴백 체인
(`pipeline/assets/tts_providers.py`, `pipeline/config_audio.py`,
`config/audio.yml`)을 그대로 이식했다. `provider_priority`(기본
azure→elevenlabs→openai) 순서로 시도하며, `ELEVENLABS_API_KEY` +
`ELEVENLABS_VOICE_ID` Secret이 등록되면 자동으로 클론 목소리를 쓰고 없으면
OpenAI TTS(`nova`)로 폴백한다(코드 변경 불필요).

**클론 목소리를 실제로 쓰려면(1회성 수동 준비)**:
1. `voice_sample/`에 본인 목소리 녹음 파일(mp3/wav/m4a, 여러 개 가능)을 넣는다.
2. 로컬에서 `ELEVENLABS_API_KEY` 환경변수를 설정하고 `python pipeline/update_voice_id.py`를 실행한다 — ElevenLabs에 Voice Clone을 생성하고 `voice_id`를 출력한다.
3. 그 `voice_id`를 이 레포의 GitHub Secret `ELEVENLABS_VOICE_ID`로 등록하고, `ELEVENLABS_API_KEY`도 함께 등록한다.

합성 후에는 loudnorm으로 방송 표준 음량(-16 LUFS)에 맞추고, 투자 권유처럼
들리는 과장 표현을 탐지(치환 없이 경고만)해 `output/{lang}/audio_report.json`에
기록한다.

## 연합뉴스/KBS 이미지 (방송사 품질)

`stock-briefing-step1`의 미디어 검색 파이프라인
(`pipeline/assets/media_providers.py`/`media_pipeline.py`/`rights_review.py`/
`asset_search_service.py`)을 이식했다. step1은 개체명 추출(`scene_plan.json`)
결과를 입력으로 쓰지만, 이 레포는 스크립트 구조가 단순해서(오프닝/리포트
브리핑/클로징 3섹션, 리포트 items가 이미 종목명 단위로 정리돼 있음) 별도
개체명 추출 없이 `pipeline/generate_media.py`가 `script.json`의 리포트
종목/섹터테마 이름을 바로 검색 키워드로 써서 같은 검색·점수화·권리분류
로직을 재사용한다.

- **오프닝**: 오프닝 훅에 등장한 종목의 사진을 전체화면 배경으로 사용
  (`build_opening()` → `html_theme.background_layer()`).
- **리포트 브리핑**: 종목/섹터테마 카드마다 검색된 사진을 64×64 썸네일로
  붙인다(`build_report_briefing()` → `html_theme.point_card_img()`). 검색
  실패한 항목만 텍스트 전용 카드로 자연스럽게 폴백한다 — 텍스트만 나열되던
  이전 레이아웃 대신 사진 기반 구성으로 바꾼 부분.
- **썸네일**: `generate_metadata.py`가 같은 `media_map.json`을 재사용해
  오프닝과 통일감 있는 썸네일을 만든다.

모든 사진에는 출처(`사진: 연합뉴스`/`사진: KBS`)가 워터마크로 표시된다.
검색이 전부 실패하면 `assets/sector_fallback/`의 섹터별 그래픽으로,
그마저 없으면 텍스트 전용 카드로 단계적으로 폴백한다.

## 트리거 체인

```
(수동) workflow_dispatch → report_update.yml
  script → voice / assets(media_map.json 생성 → 프레임 렌더링) → video → generate_metadata.py → quality_gate.py
```

과금(OpenAI/TTS) 방지를 위해 `stock-briefing-v3-2`의 자동 dispatch를 제거했습니다.
`stock-briefing-v3-2`의 `docs/index.html`로 데이터가 준비됐는지 사람이 먼저 확인한
뒤, 이 레포 Actions 탭에서 수동으로 `workflow_dispatch`를 실행하세요. 자체 cron도
없습니다.

## 산출물

```
output/YYYY-MM-DD/
  metadata.json
  final.mp4
  thumbnail.png
  script.json
```

## 실패 시 fallback

- `stock-briefing-v3-2`의 `briefing_data.json`을 못 가져오면 즉시 종료(exit 1).
- 연합뉴스/KBS 이미지 검색이 실패해도 파이프라인은 중단되지 않고 섹터
  fallback → 텍스트 카드 순으로 자연스럽게 폴백한다.
- TTS provider가 전부 실패하면(OpenAI 키까지 없는 경우) 즉시 종료.

## 필요 Secrets

| Secret | 용도 | 없을 때 |
|---|---|---|
| `OPENAI_API_KEY` | 스크립트 생성(필수) + TTS 폴백 | 스크립트 생성 자체가 불가(필수) |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | 클론 목소리 TTS | OpenAI TTS(`nova`)로 자동 폴백 |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | Azure TTS(선택, elevenlabs보다 우선순위 높음) | 건너뛰고 다음 provider 시도 |
| `YONHAP_API_KEY` / `KBS_API_KEY` | 연합뉴스/KBS 이미지 검색(선택 — 없어도 공개 검색 페이지로 동작) | 공개 검색 경로로 동작(현재 기본) |
| `NAVER_SEARCH_CLIENT_ID` / `NAVER_SEARCH_CLIENT_SECRET` | 네이버 뉴스 검색으로 이미지 검색 보완(선택) | 해당 커넥터만 비활성 |

## 로컬 실행

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python pipeline/generate_script.py KO
python pipeline/generate_voice.py KO
python pipeline/generate_media.py KO     # media_map.json 생성 (assets보다 먼저)
python pipeline/generate_assets.py KO
python pipeline/generate_subtitles.py KO
TARGET_MIN_SECONDS=300 TARGET_MAX_SECONDS=480 python pipeline/generate_video.py KO
python pipeline/generate_metadata.py KO
python pipeline/quality_gate.py KO
```

드라이런(과금 없이 파이프라인 구조만 검증): `SCRIPT_MOCK=1 TTS_MOCK=1 MEDIA_MOCK=1`
환경변수를 위 각 단계에 붙여서 실행하거나, Actions 탭에서 `workflow_dispatch`의
`dry_run` 입력을 켜서 실행한다.

## 다음 단계 (이번 범위 아님)

방송형 렌더러 추가 고도화(리포트 상위 1건에 대한 전체화면 스포트라이트
프레임 등), KBS 내부망/연합뉴스 정식 계약 API 연동은 이번 범위에 없고
후속 설계·구현 대상입니다.
