# Dataset Tools 사용 가이드

## 설치

### uv 사용 (권장)

```bash
cd dataset_tools
uv sync
```

### pip 사용

```bash
cd dataset_tools
pip install -e .
```

## CLI 명령어

### 1. Raw 데이터를 Source로 변환

Raw 데이터셋(AVI 세그먼트, JSONL 통합 파일)을 프레임 단위 Source 포맷으로 변환합니다.

```bash
# 기본 사용
uv run python main.py convert-raw \
    dataset/raw/20260114_172307 \
    dataset/source/20260114_172307

# 센서 간 최대 시간 차이 지정 (기본값: 100ms)
uv run python main.py convert-raw \
    dataset/raw/20260114_172307 \
    dataset/source/20260114_172307 \
    --max-diff 50000  # 50ms
```

**주요 변환 작업**:
- Camera: AVI → PNG (20fps)
- LiDAR: BIN 유지 (10fps)
- Radar: H5 → scan(BIN) + track(JSON) (10fps)
- Perception: JSONL → JSON (10fps)
- GNSS: TXT → JSON (100fps)

**출력 구조**:
```
source/20260114_172307/
├── meta/
│   ├── meta.json
│   ├── calibration.json
│   └── matching.json
├── ref/
│   ├── cam/front_left/{timestamp}.png
│   ├── lidar/top/{timestamp}.bin
│   ├── radar/front/scan/{timestamp}.bin
│   ├── radar/front/track/{timestamp}.json
│   └── perception/object/{timestamp}.json
└── test/
    └── AFI920/{scene_name}.h5
```

---

### 2. 데이터셋 재조립 (시간 정렬)

LiDAR 프레임 기준으로 모든 센서를 시간 동기화하고 재조립합니다.

```bash
# 기본 사용 (앞뒤 10 프레임 제거)
uv run python main.py reassemble \
    dataset/source/20260114_172307 \
    dataset/20260114_172307_reassembled

# 프레임 자르기 개수 지정
uv run python main.py reassemble \
    dataset/source/20260114_172307 \
    dataset/20260114_172307_reassembled \
    --trim 5

# S3/MinIO에서 처리
uv run python main.py reassemble \
    s3://seamless/detection/v1.0/scene1 \
    s3://seamless/detection/v1.2/scene1 \
    --s3
```

**주요 기능**:
- LiDAR 기준 최근접 센서 프레임 매칭
- `matching.json` 생성 (각 프레임의 센서별 타임스탬프 기록)
- 앞뒤 불안정 구간 제거 (기본값: 10 프레임)
- Radar 절대 속도 계산 (GNSS ego velocity 활용)

**출력**:
- `{output_path}/` 디렉토리에 재조립된 데이터셋
- `meta/matching.json`: 프레임별 센서 타임스탬프 매칭 정보

---

### 3. 동기화 검증

재조립된 데이터셋의 동기화 품질을 검증하고 리포트를 생성합니다.

```bash
# 기본 사용
uv run python main.py verify \
    dataset/20260114_172307_reassembled

# CSV 출력 경로 지정
uv run python main.py verify \
    dataset/20260114_172307_reassembled \
    --output reports/sync_report_20260114.csv
```

**출력 정보**:
- 센서별 매칭 성공/실패 통계
- 센서 간 시간 차이 (min, max, avg)
- 매칭 실패 프레임 목록

**CSV 컬럼**:
| 컬럼명 | 설명 |
|--------|------|
| `frame_idx` | LiDAR 프레임 인덱스 |
| `lidar_time` | LiDAR 타임스탬프 (unix microsecond) |
| `cam_front_left_time` | 카메라 타임스탬프 |
| `cam_front_left_diff` | LiDAR와의 시간 차이 (초) |
| `radar_front_time` | Radar 타임스탬프 |
| `radar_front_diff` | LiDAR와의 시간 차이 (초) |
| ... | 기타 센서들 |

---

### 4. 포맷 마이그레이션

데이터셋 포맷 버전을 업그레이드합니다.

```bash
# v1.0 → v1.2 마이그레이션
uv run python main.py migrate \
    dataset/v1.0/scene1 \
    dataset/v1.2/scene1 \
    --from-ver v1.0 \
    --to-ver v1.2
```

**주요 변경사항** (v1.0 → v1.2):
- `meta.json` 구조 개선 (ref/test 분리)
- `calibration.json` 통합 (camera.json, lidar.json, radar.json 병합)
- `matching.json` 추가 (시간 정렬 정보)

---

## Python API 사용

CLI 대신 Python 스크립트에서 직접 호출할 수 있습니다.

### 예시 1: Raw → Source 변환

```python
from src.converters.raw_to_source import convert_raw_to_source

convert_raw_to_source(
    input_path="dataset/raw/20260114_172307",
    output_path="dataset/source/20260114_172307",
    max_diff_us=100_000  # 100ms
)
```

### 예시 2: 데이터셋 재조립

```python
from src.align.reassembler import reassemble_dataset

reassemble_dataset(
    dataset_path="dataset/source/20260114_172307",
    output_path="dataset/20260114_172307_reassembled",
    trim_count=10,
    use_s3=False
)
```

### 예시 3: DataLoader 직접 사용

```python
from src.utils.data_loader import DataLoader

loader = DataLoader("dataset/source/20260114_172307")

# LiDAR 프레임 기준 동기화된 센서 데이터 가져오기
sync_data = loader.get_sync_frame(lidar_idx=0)

print(f"LiDAR time: {sync_data['lidar']['ros_time']}")
print(f"Camera time: {sync_data['camera']['by_name']['front_left']['ros_time']}")
print(f"Radar time: {sync_data['radar']['scans']['ros_time']}")
```

---

## 환경 변수

### S3/MinIO 연동

```bash
# MinIO 엔드포인트
export MINIO_ENDPOINT="http://mlops-showroom-minio:9000"

# 버킷 및 프리픽스
export MINIO_BUCKET="seamless"
export MINIO_DST_PREFIX="detection/v1.0"

# 인증 정보
export MINIO_ACCESS_KEY="your_access_key"
export MINIO_SECRET_KEY="your_secret_key"
```

### 예시 (seamless 버킷)

```bash
MINIO_BUCKET="seamless" \
MINIO_DST_PREFIX="detection/v1.0" \
MINIO_ACCESS_KEY="dante" \
MINIO_SECRET_KEY="your_secret" \
uv run python main.py reassemble \
    "s3://seamless/detection/v1.0/scene1" \
    "s3://seamless/detection/v1.2/scene1" \
    --s3
```

---

## 트러블슈팅

### 1. 센서 간 시간 차이 초과

**증상**: "센서 간 최대 시간 차이 초과" 오류

**해결**:
```bash
# --max-diff 값을 늘려서 재시도 (200ms)
uv run python main.py convert-raw input output --max-diff 200000
```

### 2. GNSS 데이터 파싱 실패

**증상**: "INSPVAXA 파싱 실패" 경고

**해결**:
- GNSS 파일 인코딩 확인 (UTF-8 필수)
- 첫 줄에 `#INSPVAXA` 헤더가 있는지 확인
- 수동으로 `gnss/gnss.txt` 파일 확인

### 3. H5 파일 읽기 오류

**증상**: "Radar H5 파일을 읽을 수 없음"

**해결**:
```python
# H5 파일 구조 확인
import h5py
with h5py.File("radar.h5", "r") as f:
    print(list(f.keys()))  # 최상위 그룹 확인
```

### 4. S3 연결 실패

**증상**: "S3 연결 오류"

**해결**:
```bash
# 환경 변수 확인
echo $MINIO_ENDPOINT
echo $MINIO_ACCESS_KEY

# boto3 수동 테스트
python -c "import boto3; print(boto3.__version__)"
```

---

## FAQ

### Q1: 여러 씬을 한 번에 처리하려면?

bash 루프를 사용하세요:

```bash
for scene in dataset/raw/*/; do
    scene_name=$(basename "$scene")
    uv run python main.py convert-raw \
        "dataset/raw/$scene_name" \
        "dataset/source/$scene_name"
done
```

### Q2: matching.json 포맷은?

```json
{
  "scene_name": "20260114_172307",
  "data": [
    {
      "idx": 0,
      "timestamps": {
        "gnss": 1768378988420000,
        "ref_cam_front_left": 1768378988454691,
        "ref_lidar_top": 1768378988519855,
        "ref_radar_front_scan": 1768378988438442,
        "ref_perception_object": 1768378988519449
      }
    }
  ]
}
```

### Q3: trim_count는 왜 필요한가요?

- 시작/종료 시점에 일부 센서만 데이터가 있을 수 있음
- 앞뒤 10프레임 정도를 제거하면 안정적인 동기화 구간만 유지

### Q4: Radar 절대 속도는 어떻게 계산하나요?

```
v_abs = v_rel + v_ego
```

- `v_rel`: Radar 측정 상대 속도
- `v_ego`: GNSS/INS에서 측정한 ego 차량 속도
- 좌표계 변환 적용 (NED → Body Frame)

---

## 다음 단계

- 새 센서 추가: [2_Architecture.md](2_Architecture.md#새-센서-추가) 참조
- 커스텀 변환기 작성: [2_Architecture.md](2_Architecture.md#새-변환기-추가) 참조
- 기여 가이드: 프로젝트 루트의 `.github/instructions/general-coding.instructions.md` 참조
