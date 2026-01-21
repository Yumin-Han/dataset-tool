"""CSV 리포트 생성 모듈"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def generate_alignment_csv(dataset_path: str, output_csv: str) -> None:
    """센서 정렬 결과를 CSV로 생성합니다.
    
    주요 기능:
    - 전체 LiDAR 프레임에 대해 센서별 매칭 결과 기록
    - 시간 차이 계산 (초)
    
    Args:
        dataset_path: 데이터셋 경로
        output_csv: 출력 CSV 파일 경로
    
    CSV 컬럼:
        frame_idx, lidar_time, cam_front_left_time, cam_front_left_diff, ...
    """
    try:
        from time_align.reassemble_dataset import generate_csv
        
        print(f"CSV 생성 시작...")
        print(f"  데이터셋: {dataset_path}")
        print(f"  출력: {output_csv}")
        
        generate_csv(dataset_path, output_csv)
        
        print(f"✓ CSV 생성 완료: {output_csv}")
        
    except Exception as e:
        print(f"✗ CSV 생성 실패: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CSV 리포트 생성")
    parser.add_argument("dataset", help="데이터셋 경로")
    parser.add_argument("output", help="출력 CSV 파일")
    
    args = parser.parse_args()
    
    generate_alignment_csv(args.dataset, args.output)
