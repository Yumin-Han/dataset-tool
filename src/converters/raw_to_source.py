"""Raw 데이터를 Source 포맷으로 변환하는 모듈

convert_raw_to_source.py의 로직을 모듈화한 버전입니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def convert_raw_to_source(input_path: str, output_path: str, max_diff_us: int = 100_000) -> None:
    """Raw 데이터셋을 Source 포맷으로 변환합니다.
    
    주요 변환:
    - Camera: AVI 세그먼트 → PNG 프레임
    - LiDAR: BIN 유지 (복사)
    - Radar: H5 통합파일 → scan(BIN) + track(JSON) 분할
    - Perception: JSONL 통합파일 → JSON 개별 파일 분할
    - GNSS: TXT 통합파일 → JSON 개별 파일 분할
    
    Args:
        input_path: 입력 Raw 데이터셋 경로
        output_path: 출력 Source 데이터셋 경로
        max_diff_us: 센서 간 최대 시간 차이 허용치 (마이크로초)
    
    사용 예시:
        convert_raw_to_source(
            "dataset/raw/20260114_172307",
            "dataset/source/20260114_172307",
            max_diff_us=100_000  # 100ms
        )
    """
    print(f"Raw → Source 변환 시작...")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  최대 시간 차이: {max_diff_us / 1000}ms")
    
    # TODO: scripts/convert_raw_to_source.py의 로직 통합
    # 현재는 기존 스크립트를 래핑
    try:
        # 임시로 기존 스크립트 호출
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_project_root / "scripts" / "convert_raw_to_source.py"),
             input_path, output_path, "--max-diff", str(max_diff_us)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"✗ 변환 실패:\n{result.stderr}")
            raise RuntimeError(f"변환 실패: {result.stderr}")
        
        print(f"✓ 변환 완료")
        
    except FileNotFoundError:
        print("✗ 기존 convert_raw_to_source.py 스크립트를 찾을 수 없습니다.")
        print("  scripts/convert_raw_to_source.py 파일이 존재하는지 확인하세요.")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Raw → Source 변환")
    parser.add_argument("input", help="입력 Raw 데이터셋 경로")
    parser.add_argument("output", help="출력 Source 데이터셋 경로")
    parser.add_argument("--max-diff", type=int, default=100000, help="최대 시간 차이 (us)")
    
    args = parser.parse_args()
    
    convert_raw_to_source(args.input, args.output, args.max_diff)
