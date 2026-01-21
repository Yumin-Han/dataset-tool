# Dataset Tools 모듈 재구성 완료

## 생성된 구조

```
dataset_tools/
├── pyproject.toml          # uv 기반 의존성 관리
├── README.md               # 사용자 가이드
├── main.py                 # CLI 진입점
├── .gitignore              # Git 제외 파일
├── Docs/
│   ├── 1_Overview.md       # 개요 및 목표
│   ├── 2_Architecture.md   # 시스템 아키텍처
│   └── 3_Usage.md          # 상세 사용 가이드
└── src/
    ├── __init__.py
    ├── align/              # 시간 정렬 모듈
    │   ├── __init__.py
    │   ├── reassembler.py  # 데이터셋 재조립
    │   ├── verifier.py     # 동기화 검증
    │   └── csv_generator.py # CSV 리포트 생성
    ├── converters/         # 데이터 변환 모듈
    │   ├── __init__.py
    │   ├── raw_to_source.py         # Raw → Source 변환
    │   ├── format_converter.py      # 포맷 마이그레이션
    │   ├── calibration_converter.py # Calibration 변환
    │   └── radar_processor.py       # Radar 데이터 처리
    └── utils/              # 공통 유틸리티
        ├── __init__.py
        ├── data_loader.py  # DataLoader, TimedItem
        ├── parsers.py      # GNSS, Radar 파싱
        ├── validators.py   # 데이터셋 검증
        └── s3_helper.py    # S3/MinIO 연동
```

## 주요 특징

### 1. 모듈화된 구조
- `time_align/`과 `scripts/`의 기능을 통합
- 재사용 가능한 유틸리티 분리 (`utils/`)
- 명확한 책임 분리 (`align/`, `converters/`)

### 2. 통합 CLI
```bash
# Raw → Source 변환
uv run python main.py convert-raw dataset/raw/scene1 dataset/source/scene1

# 데이터셋 재조립
uv run python main.py reassemble dataset/source/scene1 dataset/scene1_reassembled --trim 10

# 동기화 검증
uv run python main.py verify dataset/scene1_reassembled --output report.csv

# 포맷 마이그레이션
uv run python main.py migrate dataset/v1.0/scene1 dataset/v1.2/scene1
```

### 3. 하위 호환성
- 기존 `time_align/reassemble_dataset.py` 코드를 래핑
- 기존 `scripts/` 스크립트들을 subprocess로 호출
- 점진적 마이그레이션 가능

### 4. 독립 실행 가능
```bash
cd dataset_tools
uv sync
uv run python main.py --help
```

### 5. Python API 지원
```python
from src.align.reassembler import reassemble_dataset
from src.utils.data_loader import DataLoader

# 데이터셋 재조립
reassemble_dataset("input", "output", trim_count=10)

# 데이터 로딩
loader = DataLoader("dataset/scene1")
sync_data = loader.get_sync_frame(lidar_idx=0)
```

## 다음 단계

### 1. 기존 코드 마이그레이션
현재는 기존 스크립트를 subprocess로 호출하는 wrapper 형태입니다.
점진적으로 로직을 모듈 내부로 이전하면 됩니다.

**우선순위**:
1. `reassemble_dataset.py` → `src/align/reassembler.py` (핵심 로직)
2. `convert_raw_to_source.py` → `src/converters/raw_to_source.py`
3. 기타 스크립트들 통합

### 2. 테스트 작성
```bash
cd dataset_tools
uv add --dev pytest pytest-cov
pytest tests/
```

### 3. CI/CD 설정
- GitHub Actions에서 자동 테스트
- 릴리스 자동화

### 4. 문서 개선
- 각 모듈별 상세 API 문서
- 튜토리얼 추가
- 트러블슈팅 가이드 확장

## 기존 코드와의 관계

### 유지
- `time_align/` : 기존 스크립트 유지 (하위 호환성)
- `scripts/` : 기존 스크립트 유지

### 새로 생성
- `dataset_tools/` : 통합 모듈 (selection_tool 스타일)

### 사용 방법
```bash
# 기존 방식 (여전히 작동)
python time_align/reassemble_dataset.py dataset/scene1 output --trim 10

# 새로운 방식 (권장)
uv run python dataset_tools/main.py reassemble dataset/scene1 output --trim 10
```

## 이점

1. **개발 효율성**: 일관된 CLI 및 모듈 구조
2. **유지보수성**: 공통 로직 중복 제거
3. **확장성**: 새 변환기 추가 용이
4. **재사용성**: 다른 프로젝트에서 라이브러리로 활용 가능
5. **문서화**: 체계적인 문서 구조

## 참고

- 기존 코드: `time_align/`, `scripts/`
- 새 모듈: `dataset_tools/`
- Selection Tool 참조: `selection_tool/`
