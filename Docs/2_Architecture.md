# Dataset Tools 아키텍처

## 기술 스택

### 언어 및 런타임
- Python 3.10+
- uv 패키지 매니저

### 주요 라이브러리
- **NumPy**: 수치 연산 및 포인트 클라우드 처리
- **OpenCV**: 이미지/비디오 처리
- **Pandas**: CSV 생성 및 데이터 분석
- **h5py**: Radar H5 파일 파싱
- **boto3**: S3/MinIO 연동
- **tqdm**: 진행률 표시

## 디렉토리 구조

```
dataset_tools/
├── pyproject.toml          # uv 의존성 정의
├── README.md               # 사용자 가이드
├── main.py                 # CLI 진입점
├── Docs/
│   ├── 1_Overview.md       # 개요 및 목표
│   ├── 2_Architecture.md   # 이 문서
│   └── 3_Usage.md          # 상세 사용법
└── src/
    ├── __init__.py
    ├── align/              # 시간 정렬 모듈
    │   ├── __init__.py
    │   ├── reassembler.py  # 데이터셋 재조립 (reassemble_dataset.py)
    │   ├── verifier.py     # 동기화 검증 (verify_sync.py)
    │   └── csv_generator.py # CSV 리포트 생성
    ├── converters/         # 데이터 변환 모듈
    │   ├── __init__.py
    │   ├── raw_to_source.py         # Raw → Source 변환
    │   ├── format_converter.py      # 포맷 마이그레이션 (v1 → v2)
    │   ├── calibration_converter.py # Calibration 통합
    │   └── radar_processor.py       # Radar 데이터 처리
    └── utils/              # 공통 유틸리티
        ├── __init__.py
        ├── data_loader.py  # TimedItem, DataLoader 클래스
        ├── parsers.py      # GNSS, Radar 파싱 함수
        ├── validators.py   # 데이터셋 구조 검증
        └── s3_helper.py    # S3/MinIO 연동 헬퍼
```

## 모듈 설계

### 1. align (시간 정렬)

#### reassembler.py
- **책임**: LiDAR 기준 센서 데이터 재조립
- **주요 함수**:
  - `reassemble_dataset(input_path, output_path, trim_count, use_s3)`
  - 앞뒤 trim_count 프레임 제거
  - matching.json 생성 (센서별 타임스탬프 매칭 정보)
  - 센서별 개별 파일로 분할 저장

#### verifier.py
- **책임**: 동기화 결과 검증
- **주요 함수**:
  - `verify_sync(dataset_path, output_csv)`
  - 센서 간 시간 차이 통계
  - 매칭 실패 프레임 탐지

#### csv_generator.py
- **책임**: 정렬 결과 CSV 리포트 생성
- **주요 함수**:
  - `generate_alignment_csv(dataset_path, output_csv)`
  - 프레임별 센서 타임스탬프 및 차이 기록

### 2. converters (데이터 변환)

#### raw_to_source.py
- **책임**: Raw 데이터를 Source 포맷으로 변환
- **주요 함수**:
  - `convert_raw_to_source(input_path, output_path, max_diff_us)`
  - AVI → PNG 프레임 추출
  - JSONL → JSON 개별 파일 분할
  - H5 → scan/track 분리

#### format_converter.py
- **책임**: 데이터셋 포맷 버전 마이그레이션
- **주요 함수**:
  - `convert_format(input_path, output_path, from_ver, to_ver)`
  - v1.0 → v1.2 메타데이터 구조 변경
  - 하위 호환성 유지

#### calibration_converter.py
- **책임**: Calibration 값 포맷 변환
- **주요 함수**:
  - `convert_calibration(input_calib, output_calib)`
  - 센서별 calibration.json 통합
  - 좌표계 변환 (필요 시)

#### radar_processor.py
- **책임**: Radar 데이터 특수 처리
- **주요 함수**:
  - `add_absolute_velocity(radar_data, gnss_data)`
  - 상대 속도 → 절대 속도 변환
  - 동적 객체 필터링

### 3. utils (공통 유틸리티)

#### data_loader.py
- **책임**: 멀티센서 데이터 로딩 및 동기화
- **주요 클래스**:
  - `TimedItem`: (ros_time, data) 튜플
  - `DataLoader`: 센서별 타임스탬프 정렬 및 최근접 매칭

#### parsers.py
- **책임**: 센서 데이터 파싱
- **주요 함수**:
  - `parse_inspvaxa_line(line)`: GNSS INSPVAXA 파싱
  - `parse_h5_radar(h5_path)`: Radar H5 파일 파싱
  - `parse_perception_jsonl(jsonl_path)`: Perception JSONL 파싱

#### validators.py
- **책임**: 데이터셋 구조 검증
- **주요 함수**:
  - `validate_dataset_structure(dataset_path, required_sensors)`
  - `validate_timestamps(timestamps)`: 타임스탬프 유효성 검증

#### s3_helper.py
- **책임**: S3/MinIO 연동
- **주요 함수**:
  - `build_s3_client()`: boto3 클라이언트 생성
  - `s3_list_scenes()`: 씬 목록 조회
  - `s3_download_dir() / s3_upload_dir()`: 디렉토리 업/다운로드

## 데이터 흐름

### 1. Raw → Source 변환
```
Raw Dataset
  ↓
converters/raw_to_source.py
  ├→ utils/parsers.py (H5, JSONL 파싱)
  └→ utils/validators.py (구조 검증)
  ↓
Source Dataset
```

### 2. 시간 정렬 및 재조립
```
Source Dataset
  ↓
align/reassembler.py
  ├→ utils/data_loader.py (센서 로딩 및 매칭)
  ├→ utils/parsers.py (GNSS, Radar 파싱)
  └→ converters/radar_processor.py (절대 속도 계산)
  ↓
Reassembled Dataset + matching.json
```

### 3. 검증 및 리포트
```
Reassembled Dataset
  ↓
align/verifier.py
  ├→ utils/data_loader.py (매칭 결과 검증)
  └→ align/csv_generator.py (CSV 생성)
  ↓
sync_report.csv
```

## 확장 가능성

### 새 센서 추가
1. `utils/parsers.py`에 파싱 함수 추가
2. `utils/data_loader.py`의 `DataLoader` 클래스에 센서 로딩 로직 추가
3. `converters/raw_to_source.py`에 변환 로직 추가

### 새 변환기 추가
1. `converters/` 폴더에 새 모듈 생성
2. `converters/__init__.py`에 export
3. `main.py`에 CLI 명령어 추가

### S3 이외 스토리지 지원
1. `utils/storage_helper.py` 추상화 레이어 추가
2. `s3_helper.py`, `local_helper.py` 등 구현체 분리
