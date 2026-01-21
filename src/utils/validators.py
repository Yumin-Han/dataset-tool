"""데이터셋 구조 검증 유틸리티"""

import os
from pathlib import Path
from typing import Dict, List, Optional


def validate_dataset_structure(dataset_path: str, dataset_type: str = "raw") -> Dict[str, bool]:
    """데이터셋 디렉토리 구조를 검증합니다.
    
    Args:
        dataset_path: 데이터셋 루트 경로
        dataset_type: 'raw' 또는 'source'
    
    Returns:
        센서별 존재 여부 딕셔너리
        {
            'meta': True/False,
            'gnss': True/False,
            'ref_camera': True/False,
            'ref_lidar': True/False,
            'ref_radar': True/False,
            'ref_perception': True/False,
            'test_radar': True/False
        }
    """
    dataset_path = Path(dataset_path)
    result = {}
    
    # Meta 확인
    meta_path = dataset_path / "meta"
    result['meta'] = meta_path.exists() and (meta_path / "meta.json").exists()
    
    # GNSS 확인
    gnss_path = dataset_path / "gnss"
    if dataset_type == "raw":
        result['gnss'] = gnss_path.exists() and (gnss_path / "gnss.txt").exists()
    else:  # source
        result['gnss'] = gnss_path.exists() and len(list(gnss_path.glob("*.json"))) > 0
    
    # Reference 센서 확인
    ref_path = dataset_path / "ref"
    if ref_path.exists():
        # Camera
        cam_path = ref_path / "cam"
        result['ref_camera'] = cam_path.exists() and len(list(cam_path.iterdir())) > 0
        
        # LiDAR
        lidar_path = ref_path / "lidar" / "top"
        result['ref_lidar'] = lidar_path.exists() and len(list(lidar_path.glob("*.bin"))) > 0
        
        # Radar
        radar_path = ref_path / "radar"
        result['ref_radar'] = radar_path.exists() and len(list(radar_path.iterdir())) > 0
        
        # Perception
        perc_path = ref_path / "perception"
        result['ref_perception'] = perc_path.exists() and len(list(perc_path.iterdir())) > 0
    else:
        result['ref_camera'] = False
        result['ref_lidar'] = False
        result['ref_radar'] = False
        result['ref_perception'] = False
    
    # Test 레이더 확인
    test_path = dataset_path / "test"
    result['test_radar'] = test_path.exists() and len(list(test_path.iterdir())) > 0
    
    return result


def validate_timestamps(timestamps: List[int]) -> Dict[str, any]:
    """타임스탬프 리스트의 유효성을 검증합니다.
    
    Args:
        timestamps: Unix timestamp (microsecond) 리스트
    
    Returns:
        검증 결과 딕셔너리
        {
            'valid': True/False,
            'count': int,
            'min': int,
            'max': int,
            'duplicates': int,
            'out_of_order': int
        }
    """
    if not timestamps:
        return {
            'valid': False,
            'count': 0,
            'min': None,
            'max': None,
            'duplicates': 0,
            'out_of_order': 0,
            'message': '타임스탬프가 비어있습니다'
        }
    
    # 기본 통계
    count = len(timestamps)
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    
    # 중복 검사
    duplicates = count - len(set(timestamps))
    
    # 순서 검사
    out_of_order = 0
    for i in range(1, len(timestamps)):
        if timestamps[i] < timestamps[i-1]:
            out_of_order += 1
    
    # 유효성 판단
    valid = duplicates == 0 and out_of_order == 0
    
    result = {
        'valid': valid,
        'count': count,
        'min': min_ts,
        'max': max_ts,
        'duplicates': duplicates,
        'out_of_order': out_of_order
    }
    
    if not valid:
        messages = []
        if duplicates > 0:
            messages.append(f'{duplicates}개의 중복 타임스탬프')
        if out_of_order > 0:
            messages.append(f'{out_of_order}개의 순서 오류')
        result['message'] = ', '.join(messages)
    else:
        result['message'] = '모든 타임스탬프가 유효합니다'
    
    return result


def find_sensor_channels(dataset_path: str) -> Dict[str, List[str]]:
    """데이터셋에서 사용 가능한 센서 채널을 탐색합니다.
    
    Args:
        dataset_path: 데이터셋 루트 경로
    
    Returns:
        센서 타입별 채널 리스트
        {
            'camera': ['front_left', 'front_right', ...],
            'radar': ['front', 'left', ...],
            'perception': ['object', 'lane', 'structure', 'ins']
        }
    """
    dataset_path = Path(dataset_path)
    result = {
        'camera': [],
        'radar': [],
        'perception': []
    }
    
    ref_path = dataset_path / "ref"
    if not ref_path.exists():
        return result
    
    # Camera 채널 탐색
    cam_path = ref_path / "cam"
    if cam_path.exists():
        result['camera'] = [d.name for d in cam_path.iterdir() if d.is_dir()]
    
    # Radar 채널 탐색
    radar_path = ref_path / "radar"
    if radar_path.exists():
        result['radar'] = [d.name for d in radar_path.iterdir() if d.is_dir()]
    
    # Perception 채널 탐색
    perc_path = ref_path / "perception"
    if perc_path.exists():
        result['perception'] = [d.name for d in perc_path.iterdir() if d.is_dir()]
    
    return result
