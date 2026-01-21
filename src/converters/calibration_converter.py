"""Calibration 값 변환 및 통합 모듈"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def convert_calibration(input_calib: str, output_calib: str) -> None:
    """Calibration 값을 변환하고 통합합니다.
    
    주요 기능:
    - camera.json, lidar.json, radar.json을 calibration.json으로 통합
    - 좌표계 변환 (필요 시)
    
    Args:
        input_calib: 입력 calibration 경로 (디렉토리 또는 파일)
        output_calib: 출력 calibration.json 경로
    
    사용 예시:
        convert_calibration(
            "dataset/scene1/meta",
            "dataset/scene1/meta/calibration.json"
        )
    """
    print(f"Calibration 변환 시작...")
    print(f"  입력: {input_calib}")
    print(f"  출력: {output_calib}")
    
    # TODO: scripts/convert_calibration_value.py 로직 통합
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_project_root / "scripts" / "convert_calibration_value.py"),
             input_calib, output_calib],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"✗ 변환 실패:\n{result.stderr}")
            raise RuntimeError(f"변환 실패: {result.stderr}")
        
        print(f"✓ 변환 완료")
        
    except FileNotFoundError:
        print("✗ 기존 변환 스크립트를 찾을 수 없습니다.")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Calibration 변환")
    parser.add_argument("input", help="입력 calibration 경로")
    parser.add_argument("output", help="출력 calibration.json 경로")
    
    args = parser.parse_args()
    
    convert_calibration(args.input, args.output)
