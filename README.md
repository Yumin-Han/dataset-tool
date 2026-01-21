# Dataset Tools

RIDE 프로젝트의 멀티센서 데이터셋 변환 및 타임 정렬 도구 모음입니다.

## 개요

이 모듈은 기존 `time_align`과 `scripts` 폴더의 기능을 통합하여 다음과 같은 기능을 제공합니다:

### 주요 기능

1. **데이터 정렬 (Time Alignment)**
   - 멀티센서 데이터를 LiDAR 기준으로 시간 동기화
   - 정렬 결과 검증 및 CSV 리포트 생성
   - 교정된 데이터셋 재조립

2. **데이터 변환 (Converters)**
   - Raw 데이터를 Source 포맷으로 변환
   - 데이터셋 포맷 버전 마이그레이션 (v1.0 → v1.2)
   - Calibration 값 변환 및 통합
   - Radar 데이터 처리 및 재구성

## 디렉토리 구조

```
dataset_tools/
├── pyproject.toml          # uv 기반 의존성 관리
├── README.md               # 이 파일
├── main.py                 # CLI 진입점
├── Docs/                   # 문서
│   ├── 1_Overview.md       # 개요 및 목표
│   ├── 2_Architecture.md   # 시스템 아키텍처
│   └── 3_Usage.md          # 사용 가이드
└── src/
    ├── align/              # 시간 정렬 기능
    │   ├── reassembler.py  # 데이터셋 재조립
    │   ├── verifier.py     # 동기화 검증
    │   └── csv_generator.py # CSV 리포트 생성
    ├── converters/         # 데이터 변환 기능
    │   ├── raw_to_source.py         # Raw → Source 변환
    │   ├── format_converter.py      # 포맷 마이그레이션
    │   ├── calibration_converter.py # Calibration 변환
    │   └── radar_processor.py       # Radar 데이터 처리
    └── utils/              # 공통 유틸리티
        ├── data_loader.py  # 데이터 로딩
        ├── parsers.py      # 파싱 함수들
        └── validators.py   # 검증 함수들
```

## 빠른 시작

### 설치

```bash
# uv를 사용하는 경우
cd dataset_tools
uv sync

# pip를 사용하는 경우
pip install -e .
```

### 사용 예시

#### 1. Raw 데이터를 Source로 변환

```bash
# CLI 사용
uv run python main.py convert-raw dataset/20260114_172307 dataset/converted/20260114_172307

# 또는 직접 모듈 호출
uv run python -m src.converters.raw_to_source \
    --input dataset/20260114_172307 \
    --output dataset/converted/20260114_172307
```

#### 2. 데이터셋 타임 정렬 및 재조립

```bash
# CLI 사용
uv run python main.py reassemble \
    --dataset dataset/20260114_172307 \
    --output dataset/20260114_172307_reassembled \
    --trim 10

# 또는 직접 모듈 호출
uv run python -m src.align.reassembler \
    --dataset dataset/20260114_172307 \
    --output dataset/20260114_172307_reassembled \
    --trim 10
```

#### 3. 동기화 검증 및 CSV 생성

```bash
uv run python main.py verify dataset/20260114_172307 --output sync_report.csv
```

## 개발 환경

- Python 3.10 이상
- uv 패키지 매니저 권장
- Windows 11, Ubuntu 22.04 LTS 지원

## 문서

자세한 사용법과 아키텍처는 [Docs](Docs/) 폴더를 참조하세요:

- [1_Overview.md](Docs/1_Overview.md) - 프로젝트 개요 및 목표
- [2_Architecture.md](Docs/2_Architecture.md) - 시스템 아키텍처
- [3_Usage.md](Docs/3_Usage.md) - 상세 사용 가이드

## 기여

이 모듈은 RIDE 프로젝트의 일부입니다. 기여 시 프로젝트의 코딩 가이드라인을 따라주세요.

## 라이선스

(프로젝트 라이선스에 따름)
