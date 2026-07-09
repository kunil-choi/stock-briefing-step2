# pipeline/report_decision.py
"""
report_update의 video_format(longform|shorts) 결정 로직.

요구사항: "리포트 핵심 종목 수가 5개 미만이거나 신규성이 낮으면 롱폼 대신
쇼츠/커뮤니티용 요약만 생성한다."

Phase 1 구현은 단순 휴리스틱이다 — 정교한 ranking_score 기반 판단은 후속
단계(주도주 랭킹형 플롯, F)에서 다룰 예정이며, 여기서는 그 전 단계의
최소 기준선 역할만 한다.
"""
from config_schedule import REPORT_DECISION

MIN_CORE_STOCKS = REPORT_DECISION.get("min_core_stocks", 5)


def count_core_stocks(brokerage_reports: dict) -> int:
    """simultaneous/new_coverage/single_significant에 등장한 종목명을
    중복 제거해 센다 = "리포트 핵심 종목 수"."""
    if not brokerage_reports:
        return 0
    names = set()
    for bucket in ("simultaneous", "new_coverage", "single_significant"):
        for r in brokerage_reports.get(bucket, []) or []:
            name = (r.get("stock_name") or "").strip()
            if name:
                names.add(name)
    return len(names)


def is_low_novelty(brokerage_reports: dict) -> bool:
    """"신규성이 낮다"의 Phase 1 휴리스틱: 신규 커버리지 개시가 0건이고
    동시언급(여러 증권사가 같은 종목을 동시에 주목)도 1건 이하면 오늘
    특별히 새로운 이슈가 없다고 본다."""
    if not brokerage_reports:
        return True
    new_coverage_count = len(brokerage_reports.get("new_coverage") or [])
    simultaneous_count = len(brokerage_reports.get("simultaneous") or [])
    return new_coverage_count == 0 and simultaneous_count <= 1


def decide_video_format(brokerage_reports: dict) -> str:
    """"longform" | "shorts" 반환."""
    core_count = count_core_stocks(brokerage_reports)
    low_novelty = is_low_novelty(brokerage_reports)
    if core_count < MIN_CORE_STOCKS or low_novelty:
        print(f"  [report_decision] 핵심종목 {core_count}개(<{MIN_CORE_STOCKS}) 또는 "
              f"신규성 낮음({low_novelty}) → video_format=shorts")
        return "shorts"
    print(f"  [report_decision] 핵심종목 {core_count}개, 신규성 충족 → video_format=longform")
    return "longform"
