"""데이터셋 재조립 모듈

reassemble_dataset.py의 핵심 로직을 모듈화한 버전입니다.
기존 코드는 time_align/reassemble_dataset.py를 참조하세요.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 sys.path에 추가 (기존 코드 임포트용)
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def reassemble_dataset(
    dataset_path: str,
    output_path: str,
    trim_count: int = 10,
    use_s3: bool = False
) -> None:
    """데이터셋을 LiDAR 기준으로 시간 정렬하여 재조립합니다.
    
    주요 기능:
    - LiDAR 프레임 기준으로 모든 센서 동기화
    - 앞뒤 trim_count 프레임 제거
    - matching.json 생성 (각 프레임의 센서 타임스탬프 기록)
    - Radar 절대 속도 계산 (GNSS ego velocity 활용)
    
    Args:
        dataset_path: 입력 데이터셋 경로
        output_path: 출력 데이터셋 경로
        trim_count: 앞뒤로 자를 프레임 수
        use_s3: S3/MinIO 사용 여부
    
    사용 예시:
        reassemble_dataset(
            "dataset/source/20260114_172307",
            "dataset/20260114_172307_reassembled",
            trim_count=10
        )
    """
    # 기존 time_align/reassemble_dataset.py의 reassemble 함수 호출
    try:
        from time_align.reassemble_dataset import reassemble
        
        print(f"데이터셋 재조립 시작...")
        print(f"  입력: {dataset_path}")
        print(f"  출력: {output_path}")
        print(f"  Trim: {trim_count} 프레임")
        
        reassemble(
            dataset_path=dataset_path,
            output_path=output_path,
            trim_count=trim_count,
            save_as_frames=True,
            min_radar_points=0
        )
        
        print("✓ 재조립 완료")
        
    except Exception as e:
        print(f"✗ 재조립 실패: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="데이터셋 재조립")
    parser.add_argument("dataset", help="입력 데이터셋 경로")
    parser.add_argument("output", help="출력 데이터셋 경로")
    parser.add_argument("--trim", type=int, default=10, help="앞뒤로 자를 프레임 수")
    parser.add_argument("--s3", action="store_true", help="S3/MinIO 사용")
    
    args = parser.parse_args()
    
    reassemble_dataset(args.dataset, args.output, args.trim, args.s3)
