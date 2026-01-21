---
applyTo: 'dataset-tool/**'
extends: '../../../.github/instructions/general-coding.instructions.md'
---

# dataset-tool 전용 가이드라인

이 파일은 dataset-tool 개발 시 추가로 적용되는 가이드라인입니다.
공통 가이드라인은 [general-coding.instructions.md](../../../.github/instructions/general-coding.instructions.md)를 참조하세요.

---

## 🔧 dataset-tool 개요

**데이터셋 변환 및 타임 정렬 도구**

### 핵심 기능
1. **Raw → Source 변환**: AVI→PNG, JSONL→JSON, 파일명 표준화
2. **시간 동기화**: LiDAR 기준 멀티센서 정렬
3. **데이터셋 검증**: 동기화 품질 리포트 생성
4. **포맷 마이그레이션**: v1.0 → v1.2 등 버전 변환
5. **S3 통합**: MinIO/AWS S3 업로드/다운로드

### 대상 사용자
- 데이터 엔지니어
- ML 엔지니어
- 데이터셋 큐레이터

---

## 📁 프로젝트 구조

```
dataset-tool/
├── main.py                      # CLI 진입점
│
├── src/
│   ├── align/                   # 시간 정렬
│   │   ├── reassembler.py      # 데이터셋 재조립
│   │   ├── verifier.py         # 동기화 검증
│   │   └── csv_generator.py   # 리포트 생성
│   │
│   ├── converters/              # 데이터 변환
│   │   ├── raw_to_source.py    # Raw→Source 변환
│   │   ├── format_converter.py # 포맷 변환 (AVI, JSONL)
│   │   ├── calibration_converter.py  # 캘리브레이션 변환
│   │   └── radar_processor.py  # 레이더 H5 처리
│   │
│   └── utils/                   # 유틸리티
│       ├── data_loader.py      # DataLoader, TimedItem
│       ├── parsers.py          # GNSS, Radar 파싱
│       ├── validators.py       # 데이터셋 검증
│       └── s3_helper.py        # S3/MinIO 헬퍼
│
├── Docs/
│   ├── 1_Overview.md           # 개요
│   ├── 2_Architecture.md       # 아키텍처
│   └── 3_Usage.md              # 사용법
│
├── pyproject.toml
└── README.md
```

---

## 🔧 개발 가이드라인

### 1. CLI 명령어 구조

모든 명령어는 `argparse` 서브커맨드로 구현:

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description='RIDE 데이터셋 도구')
    subparsers = parser.add_subparsers(dest='command')
    
    # convert-raw 명령
    convert_parser = subparsers.add_parser('convert-raw')
    convert_parser.add_argument('input', help='Raw 데이터셋 경로')
    convert_parser.add_argument('output', help='Source 데이터셋 경로')
    
    # reassemble 명령
    reassemble_parser = subparsers.add_parser('reassemble')
    reassemble_parser.add_argument('input', help='입력 데이터셋 경로')
    reassemble_parser.add_argument('output', help='출력 데이터셋 경로')
    reassemble_parser.add_argument('--trim', type=int, default=0)
    
    args = parser.parse_args()
    # ... 실행 로직
```

### 2. 데이터 로더 패턴

**TimedItem 활용:**
```python
from src.utils.data_loader import DataLoader, TimedItem

# 센서 데이터 로드
loader = DataLoader()
lidar_items = loader.load_sensor_data(
    "dataset/scene1/ref/lidar/top",
    "*.bin",
    lambda path: int(path.stem)  # 파일명에서 타임스탬프 추출
)

# TimedItem 구조
for item in lidar_items:
    print(f"Timestamp: {item.timestamp}")  # unix time (us)
    print(f"Path: {item.path}")
    print(f"Data: {item.data}")  # 로드된 데이터 (lazy)
```

**멀티센서 동기화:**
```python
# LiDAR를 기준으로 정렬
lidar_items.sort(key=lambda x: x.timestamp)

# 각 LiDAR 프레임에 가장 가까운 카메라 프레임 찾기
for lidar_item in lidar_items:
    camera_item = find_closest(camera_items, lidar_item.timestamp)
    if abs(camera_item.timestamp - lidar_item.timestamp) < 50000:  # 50ms
        matched_pairs.append((lidar_item, camera_item))
```

### 3. 파일 변환 규칙

#### Raw → Source 변환

**카메라 (AVI → PNG):**
```python
import cv2

# segment1.txt 파싱
# Format: frame_idx, unix_timestamp_ns
with open("segment1.txt") as f:
    timestamps = []
    for line in f:
        idx, ts_ns = line.strip().split(',')
        timestamps.append(int(ts_ns) // 1000)  # ns → us

# AVI 추출
cap = cv2.VideoCapture("segment1.avi")
for idx, timestamp in enumerate(timestamps):
    ret, frame = cap.read()
    if ret:
        output_path = f"cam/{timestamp:016d}.png"
        cv2.imwrite(output_path, frame)
```

**Perception (JSONL → JSON):**
```python
import json

# object.jsonl 파싱
with open("perception/object.jsonl") as f:
    for line in f:
        data = json.loads(line)
        timestamp = int(data['time_stamp'][:16])  # 19자리 → 16자리
        
        output_path = f"perception/object/{timestamp:016d}.json"
        with open(output_path, 'w') as out:
            json.dump(data, out, ensure_ascii=False)
```

**레이더 (H5 → BIN/JSON):**
```python
import h5py

with h5py.File("radar/front/scene.h5", 'r') as f:
    timestamps = f['Timestamp/Measurement'][:]  # ns
    
    for ts_ns in timestamps:
        ts_us = int(ts_ns // 1000)
        
        # scan: point cloud
        scan_data = f[f'Measurement/{ts_ns}'][:]
        output_scan = f"radar/front/scan/{ts_us:016d}.bin"
        scan_data.tofile(output_scan)
        
        # track: objects
        if f'Object/{ts_ns}' in f:
            track_data = parse_h5_track(f[f'Object/{ts_ns}'])
            output_track = f"radar/front/track/{ts_us:016d}.json"
            with open(output_track, 'w') as out:
                json.dump(track_data, out)
```

### 4. 시간 동기화 알고리즘

**LiDAR 기준 정렬:**
```python
def reassemble_dataset(input_dir, output_dir, trim=0):
    """데이터셋 재조립"""
    
    # 1. LiDAR 프레임 로드 (기준 센서)
    lidar_items = load_lidar_data(input_dir)
    lidar_items.sort(key=lambda x: x.timestamp)
    
    # 2. Trim (앞뒤 불안정 구간 제거)
    if trim > 0:
        lidar_items = lidar_items[trim:-trim]
    
    # 3. 다른 센서들 로드
    camera_items = load_camera_data(input_dir)
    radar_items = load_radar_data(input_dir)
    gnss_items = load_gnss_data(input_dir)
    
    # 4. 각 LiDAR 프레임마다 가장 가까운 센서 데이터 매칭
    matched_data = []
    for idx, lidar_item in enumerate(lidar_items):
        camera = find_closest(camera_items, lidar_item.timestamp, max_delta=50000)
        radar = find_closest(radar_items, lidar_item.timestamp, max_delta=50000)
        gnss = find_closest(gnss_items, lidar_item.timestamp, max_delta=10000)
        
        matched_data.append({
            'idx': idx,
            'timestamps': {
                'ref_lidar_top': lidar_item.timestamp,
                'ref_cam_front_left': camera.timestamp if camera else None,
                'ref_radar_front_scan': radar.timestamp if radar else None,
                'gnss': gnss.timestamp if gnss else None,
            }
        })
    
    # 5. matching.json 생성
    save_matching_json(output_dir, matched_data)
    
    # 6. 데이터 복사
    copy_matched_data(input_dir, output_dir, matched_data)
```

**Closest Match 알고리즘:**
```python
def find_closest(items: List[TimedItem], target_ts: int, max_delta: int = 50000):
    """가장 가까운 타임스탬프 아이템 찾기"""
    if not items:
        return None
    
    # Binary search (items는 정렬되어 있어야 함)
    idx = bisect.bisect_left([item.timestamp for item in items], target_ts)
    
    candidates = []
    if idx > 0:
        candidates.append(items[idx - 1])
    if idx < len(items):
        candidates.append(items[idx])
    
    # 가장 가까운 아이템 선택
    closest = min(candidates, key=lambda item: abs(item.timestamp - target_ts))
    
    # max_delta 체크
    if abs(closest.timestamp - target_ts) > max_delta:
        return None
    
    return closest
```

### 5. 데이터셋 검증

**동기화 품질 검증:**
```python
def verify_sync(dataset_dir, output_csv):
    """동기화 품질 검증"""
    
    matching = load_matching_json(dataset_dir)
    
    results = []
    for frame in matching['data']:
        lidar_ts = frame['timestamps']['ref_lidar_top']
        
        for sensor, sensor_ts in frame['timestamps'].items():
            if sensor == 'ref_lidar_top' or sensor_ts is None:
                continue
            
            delta_ms = abs(sensor_ts - lidar_ts) / 1000.0
            
            results.append({
                'frame_idx': frame['idx'],
                'sensor': sensor,
                'delta_ms': delta_ms,
                'status': 'OK' if delta_ms < 50 else 'WARNING'
            })
    
    # CSV 저장
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)
    
    # 통계
    print(f"평균 지연: {df['delta_ms'].mean():.2f} ms")
    print(f"최대 지연: {df['delta_ms'].max():.2f} ms")
    print(f"경고 프레임: {(df['status'] == 'WARNING').sum()} / {len(df)}")
```

### 6. S3/MinIO 연동

**업로드:**
```python
from src.utils.s3_helper import S3Helper

s3 = S3Helper(
    endpoint='https://s3.example.com',
    access_key='ACCESS_KEY',
    secret_key='SECRET_KEY',
    bucket='ride-datasets'
)

# 데이터셋 업로드
s3.upload_directory(
    local_path='dataset/20260121_123456',
    s3_prefix='scenes/20260121_123456'
)
```

**다운로드:**
```python
# 데이터셋 다운로드
s3.download_directory(
    s3_prefix='scenes/20260121_123456',
    local_path='dataset/20260121_123456'
)
```

---

## 🧪 테스트

### 단위 테스트
```python
import pytest
from src.utils.parsers import parse_inspvaxa_line

def test_inspvaxa_parsing():
    line = "#INSPVAXA,COM1,0,73.5,..."
    result = parse_inspvaxa_line(line)
    assert result['latitude'] == 37.1234
    assert result['longitude'] == 127.5678
```

### 통합 테스트
```bash
# Raw → Source 변환 테스트
python main.py convert-raw dataset/raw/scene1 dataset/source/scene1

# 재조립 테스트
python main.py reassemble dataset/source/scene1 dataset/aligned/scene1 --trim 10

# 검증 테스트
python main.py verify dataset/aligned/scene1 --output report.csv
```

---

## 📊 성능 최적화

### 1. 대용량 파일 처리
```python
# 메모리 매핑 활용
import numpy as np

def load_large_bin(path):
    """대용량 BIN 파일 로드"""
    # 전체 로드 대신 memmap 사용
    return np.memmap(path, dtype=np.float32, mode='r')
```

### 2. 병렬 처리
```python
from concurrent.futures import ProcessPoolExecutor

def convert_parallel(input_files, converter_func):
    """병렬 변환"""
    with ProcessPoolExecutor(max_workers=8) as executor:
        results = executor.map(converter_func, input_files)
    return list(results)
```

### 3. 진행률 표시
```python
from tqdm import tqdm

for item in tqdm(items, desc="Converting"):
    convert_item(item)
```

---

## 📦 배포

### CLI 도구로 배포
```bash
# uv로 설치
cd dataset-tool
uv pip install -e .

# 명령어 사용
dataset-tool convert-raw input/ output/
dataset-tool reassemble input/ output/ --trim 10
```

---

## 🔗 관련 문서

- [README.md](README.md): dataset-tool 소개
- [Docs/1_Overview.md](Docs/1_Overview.md): 상세 개요
- [Docs/2_Architecture.md](Docs/2_Architecture.md): 아키텍처 설명
- [Docs/3_Usage.md](Docs/3_Usage.md): 사용 예시
- [general-coding.instructions.md](../../../.github/instructions/general-coding.instructions.md): 공통 가이드라인

---

## ⚠️ 주의사항

1. **타임스탬프 정확도**: 항상 16자리 unix time (마이크로초)
2. **동기화 허용 오차**: LiDAR 기준 ±50ms
3. **데이터 무결성**: 변환 전후 프레임 수 검증 필수
4. **대용량 처리**: 메모리 매핑 및 병렬 처리 활용
5. **UTF-8 인코딩**: 모든 텍스트 파일은 UTF-8
6. **에러 핸들링**: 일부 센서 데이터 누락 시에도 진행 가능하도록 설계
