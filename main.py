"""
Dataset Tools CLI 진입점

데이터셋 변환 및 타임 정렬 작업을 위한 통합 CLI입니다.
"""

import argparse
import sys
from pathlib import Path


def main():
    """메인 CLI 진입점"""
    parser = argparse.ArgumentParser(
        description="RIDE 데이터셋 변환 및 타임 정렬 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # Raw 데이터를 Source로 변환
  dataset-tools convert-raw dataset/raw/scene1 dataset/source/scene1
  
  # 데이터셋 재조립 (타임 정렬)
  dataset-tools reassemble dataset/scene1 dataset/scene1_reassembled --trim 10
  
  # 동기화 검증
  dataset-tools verify dataset/scene1 --output report.csv
  
  # 데이터셋 포맷 버전 마이그레이션
  dataset-tools migrate dataset/v1.0/scene1 dataset/v1.2/scene1 --from v1.0 --to v1.2
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")
    
    # convert-raw 명령어
    parser_convert = subparsers.add_parser(
        "convert-raw",
        help="Raw 데이터셋을 Source 포맷으로 변환"
    )
    parser_convert.add_argument("input", help="입력 Raw 데이터셋 경로")
    parser_convert.add_argument("output", help="출력 Source 데이터셋 경로")
    parser_convert.add_argument("--max-diff", type=int, default=50000,
                              help="센서 간 최대 시간 차이 (마이크로초, 기본값: 50ms)")
    
    # reassemble 명령어
    parser_reassemble = subparsers.add_parser(
        "reassemble",
        help="데이터셋을 타임 정렬하여 재조립"
    )
    parser_reassemble.add_argument("dataset", help="입력 데이터셋 경로")
    parser_reassemble.add_argument("output", help="출력 데이터셋 경로")
    parser_reassemble.add_argument("--trim", type=int, default=10,
                                  help="앞뒤로 자를 프레임 수 (기본값: 10)")
    parser_reassemble.add_argument("--s3", action="store_true",
                                  help="S3/MinIO에서 읽기/쓰기")
    
    # verify 명령어
    parser_verify = subparsers.add_parser(
        "verify",
        help="데이터셋 동기화 검증 및 리포트 생성"
    )
    parser_verify.add_argument("dataset", help="검증할 데이터셋 경로")
    parser_verify.add_argument("--output", "-o", default="sync_report.csv",
                             help="출력 CSV 파일 경로 (기본값: sync_report.csv)")
    
    # migrate 명령어
    parser_migrate = subparsers.add_parser(
        "migrate",
        help="데이터셋 포맷 버전 마이그레이션"
    )
    parser_migrate.add_argument("input", help="입력 데이터셋 경로")
    parser_migrate.add_argument("output", help="출력 데이터셋 경로")
    parser_migrate.add_argument("--from-ver", default="v1.0", help="소스 버전 (기본값: v1.0)")
    parser_migrate.add_argument("--to-ver", default="v1.2", help="대상 버전 (기본값: v1.2)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # 명령어 실행
    try:
        if args.command == "convert-raw":
            from src.converters.raw_to_source import convert_raw_to_source
            convert_raw_to_source(args.input, args.output, args.max_diff)
            print(f"✓ Raw 데이터를 Source로 변환 완료: {args.output}")
            
        elif args.command == "reassemble":
            from src.align.reassembler import reassemble_dataset
            reassemble_dataset(args.dataset, args.output, args.trim, use_s3=args.s3)
            print(f"✓ 데이터셋 재조립 완료: {args.output}")
            
        elif args.command == "verify":
            from src.align.verifier import verify_sync
            verify_sync(args.dataset, args.output)
            print(f"✓ 동기화 검증 완료: {args.output}")
            
        elif args.command == "migrate":
            from src.converters.format_converter import convert_format
            convert_format(args.input, args.output, args.from_ver, args.to_ver)
            print(f"✓ 포맷 마이그레이션 완료: {args.output}")
            
    except Exception as e:
        print(f"✗ 오류 발생: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
