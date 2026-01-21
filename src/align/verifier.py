"""동기화 검증 모듈

verify_sync.py의 로직을 모듈화한 버전입니다.
"""

import sys
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 sys.path에 추가
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def verify_sync(dataset_path: str, output_csv: str = "sync_report.csv") -> None:
    """데이터셋의 동기화 품질을 검증합니다.
    
    주요 기능:
    - 센서별 매칭 성공/실패 통계
    - 센서 간 시간 차이 (min, max, avg)
    - CSV 리포트 생성
    
    Args:
        dataset_path: 검증할 데이터셋 경로
        output_csv: 출력 CSV 파일 경로
    
    사용 예시:
        verify_sync("dataset/20260114_172307_reassembled", "report.csv")
    """
    try:
        from time_align.verify_sync import verify_sync as _verify_sync
        
        print(f"동기화 검증 시작...")
        print(f"  데이터셋: {dataset_path}")
        
        _verify_sync(dataset_path, num_samples=5)
        
        print(f"✓ 검증 완료")
        
    except Exception as e:
        print(f"✗ 검증 실패: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="동기화 검증")
    parser.add_argument("dataset", help="검증할 데이터셋 경로")
    parser.add_argument("--output", "-o", default="sync_report.csv", help="출력 CSV 파일")
    
    args = parser.parse_args()
    
    verify_sync(args.dataset, args.output)
