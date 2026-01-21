"""데이터셋 포맷 버전 마이그레이션 모듈"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def convert_format(input_path: str, output_path: str, from_ver: str = "v1.0", to_ver: str = "v1.2") -> None:
    """데이터셋 포맷 버전을 마이그레이션합니다.
    
    주요 변경사항 (v1.0 → v1.2):
    - meta.json 구조 개선 (ref/test 분리)
    - calibration.json 통합 (camera.json, lidar.json, radar.json 병합)
    - matching.json 추가 (시간 정렬 정보)
    
    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 데이터셋 경로
        from_ver: 소스 버전 (예: "v1.0")
        to_ver: 대상 버전 (예: "v1.2")
    
    사용 예시:
        convert_format(
            "dataset/v1.0/scene1",
            "dataset/v1.2/scene1",
            from_ver="v1.0",
            to_ver="v1.2"
        )
    """
    print(f"포맷 마이그레이션 시작...")
    print(f"  {from_ver} → {to_ver}")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    
    # TODO: scripts/convert_v1tov12.py 등의 로직 통합
    try:
        if from_ver == "v1.0" and to_ver == "v1.2":
            import subprocess
            result = subprocess.run(
                [sys.executable, str(_project_root / "scripts" / "convert_v1tov12.py"),
                 input_path, output_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"✗ 마이그레이션 실패:\n{result.stderr}")
                raise RuntimeError(f"마이그레이션 실패: {result.stderr}")
            
            print(f"✓ 마이그레이션 완료")
        else:
            print(f"✗ 지원하지 않는 버전 변환: {from_ver} → {to_ver}")
            raise NotImplementedError(f"지원하지 않는 버전 변환: {from_ver} → {to_ver}")
            
    except FileNotFoundError:
        print("✗ 기존 변환 스크립트를 찾을 수 없습니다.")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="포맷 마이그레이션")
    parser.add_argument("input", help="입력 데이터셋 경로")
    parser.add_argument("output", help="출력 데이터셋 경로")
    parser.add_argument("--from-ver", default="v1.0", help="소스 버전")
    parser.add_argument("--to-ver", default="v1.2", help="대상 버전")
    
    args = parser.parse_args()
    
    convert_format(args.input, args.output, args.from_ver, args.to_ver)
