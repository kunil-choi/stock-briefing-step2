# pipeline/assets/audio_post.py
"""
프리미엄 TTS 후처리(stock-briefing-step1 이식):
  - atempo: 최종 영상 길이 조정에 맞춰 나레이션 자체의 속도도 함께 보정
  - loudnorm: 방송 표준 음량(LUFS)으로 정규화
  - BGM 사이드체인 덕킹: 나레이션이 나올 때 BGM 볼륨을 자동으로 낮추고,
    intro/body/outro 구간별로 다른 볼륨을 적용
  - 투자 권유처럼 들리는 과장 표현 탐지(치환하지 않고 경고만 남김)

step1의 detect_advice_language()는 pipeline/assets/narrative_reorder.py의
_ADVICE_PATTERNS를 재사용하지만, 이 레포는 narrative_reorder.py(개체명 추출
기반 재정렬)를 두지 않으므로 같은 패턴 목록을 이 파일에 그대로 인라인한다
(step1과 패턴 내용은 동일, import 경로만 다름).

이 모듈의 함수들은 순수하게 입력 인자만으로 동작한다(config 파일을 직접
읽지 않음) — 호출부(generate_voice.py)가 config_audio.py에서 값을 읽어
넘겨준다.
"""
import os
import re
import shutil
import subprocess
from typing import List, Optional


def _run(cmd: List[str], label: str) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ {label} 실패")
        print(result.stderr[-800:])
        return False
    return True


def _atempo_filter_chain(speed: float) -> List[str]:
    """ffmpeg atempo 필터는 1개당 0.5~2.0배속만 지원하므로, 범위를 벗어나면
    여러 개를 체인으로 연결한다."""
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return filters


def apply_post_processing(input_path: str, output_path: str, speed: float = 1.0,
                           target_lufs: float = -16.0, true_peak: float = -1.5,
                           loudness_range: float = 11.0) -> bool:
    """개별 나레이션 mp3에 atempo(speed != 1.0일 때만) + loudnorm을 적용한다."""
    filters = []
    if abs(speed - 1.0) >= 0.001:
        filters.extend(_atempo_filter_chain(speed))
    filters.append(f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={loudness_range}")
    af = ",".join(filters)
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", af, "-c:a", "libmp3lame", "-b:a", "192k",
        output_path,
    ]
    return _run(cmd, f"오디오 후처리(atempo+loudnorm, speed={speed:.3f})")


def measure_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        dur = float(result.stdout.strip())
        return dur if dur > 0 else 0.0
    except Exception:
        return 0.0


def measure_loudness(path: str) -> Optional[float]:
    """ffmpeg ebur128 필터로 통합 러프니스(LUFS)를 실측한다."""
    cmd = ["ffmpeg", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        m = re.search(r"Integrated loudness:\s*\n\s*I:\s*(-?\d+\.?\d*)\s*LUFS", result.stderr)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def mix_bgm_with_ducking(video_path: str, bgm_path: str, out_path: str,
                          intro_end: float, outro_start: float, total_duration: float,
                          intro_volume: float = 0.08, body_volume: float = 0.045,
                          outro_volume: float = 0.08, threshold_db: float = -25,
                          ratio: float = 8) -> bool:
    """나레이션이 나오는 구간에서 BGM 볼륨을 자동으로 낮추는(사이드체인 덕킹)
    믹싱을 하고, intro/body/outro 구간별로 기본 볼륨을 다르게 적용한다."""
    if not os.path.isfile(bgm_path):
        print(f"  ⚠️ BGM 없음 → BGM 없이 진행")
        shutil.copy2(video_path, out_path)
        return True

    threshold_linear = 10 ** (threshold_db / 20)
    outro_start = max(outro_start, intro_end)
    volume_expr = (
        f"volume=enable='between(t,0,{intro_end:.2f})':volume={intro_volume},"
        f"volume=enable='between(t,{intro_end:.2f},{outro_start:.2f})':volume={body_volume},"
        f"volume=enable='between(t,{outro_start:.2f},{total_duration:.2f})':volume={outro_volume}"
    )
    filter_complex = (
        f"[1:a]{volume_expr}[bgm_vol];"
        f"[bgm_vol][0:a]sidechaincompress=threshold={threshold_linear:.4f}:ratio={ratio}:"
        f"attack=5:release=200[bgm_ducked];"
        f"[0:a][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    return _run(cmd, "BGM 사이드체인 덕킹 믹싱")


# ─────────────────────────────────────────────────────────────────────────────
# 투자 권유 과장 표현 탐지 (치환하지 않고 경고만) — step1
# pipeline/assets/narrative_reorder._ADVICE_PATTERNS와 동일한 패턴 목록.
# ─────────────────────────────────────────────────────────────────────────────

_ADVICE_PATTERNS = [
    (re.compile(r"비중을?\s*확대(?:하세요|하시길 권합니다|해야\s*합니다|할\s*만합니다)?"),
     "비중 변화 여부를 확인할 필요가 있다"),
    (re.compile(r"매수(?:를)?\s*(?:추천(?:합니다)?|권합니다|하세요|적기입니다|시점입니다)"),
     "매수 여부는 투자자 스스로 판단이 필요한 관전 포인트다"),
    (re.compile(r"매도(?:를)?\s*(?:추천(?:합니다)?|권합니다|하세요|시점입니다)"),
     "매도 여부는 투자자 스스로 판단이 필요한 관전 포인트다"),
    (re.compile(r"담아볼\s*만하다"), "관심을 가져볼 만한 관전 포인트다"),
    (re.compile(r"투자(?:하기)?\s*좋은\s*시점"), "주목할 시점"),
    (re.compile(r"제안합니다"), "점검해볼 필요가 있다"),
    (re.compile(r"추천합니다"), "확인할 필요가 있다"),
    (re.compile(r"사도\s*좋다"), "관전 포인트가 될 수 있다"),
]


def detect_advice_language(text: str) -> List[str]:
    """투자 권유처럼 들리는 과장 표현을 탐지만 하고 원문은 바꾸지 않는다."""
    if not text:
        return []
    hits = []
    for pattern, _ in _ADVICE_PATTERNS:
        for m in pattern.finditer(text):
            hits.append(m.group(0))
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# audio_report.json
# ─────────────────────────────────────────────────────────────────────────────

def build_audio_report(entries: List[dict]) -> dict:
    """entries: [{"id", "provider", "duration_seconds", "speed", "loudness_lufs",
    "warnings": [...]}, ...] → output/audio_report.json에 저장할 요약 구조."""
    providers_used = sorted({e.get("provider", "") for e in entries if e.get("provider")})
    total_warnings = sum(len(e.get("warnings") or []) for e in entries)
    return {
        "total": len(entries),
        "providers_used": providers_used,
        "total_advice_language_warnings": total_warnings,
        "entries": entries,
    }
