"""센서 데이터 파싱 유틸리티"""

import datetime
from typing import Dict, Any, Optional, Tuple


def parse_inspvaxa_line(line: str, leap_seconds: int = 18) -> Optional[Dict[str, Any]]:
    """INSPVAXA 문장을 파싱하여 딕셔너리로 반환합니다.
    
    Args:
        line: #INSPVAXA로 시작하는 GNSS 문장
        leap_seconds: GPS-UTC leap seconds (기본값: 18, 2024년 기준)
    
    Returns:
        파싱된 GNSS 데이터 딕셔너리 또는 None
        {
            'timestamp': float,  # Unix timestamp (KST)
            'utc_str': str,      # KST 시간 문자열
            'latitude': float,
            'longitude': float,
            'height': float,
            'n_vel': float,      # North velocity
            'e_vel': float,      # East velocity
            'u_vel': float,      # Up velocity
            'roll': float,
            'pitch': float,
            'azimuth': float,
            'ins_status': str,
            'pos_type': str
        }
    """
    if not line.startswith("#INSPVAXA"):
        return None
    if ";" not in line:
        return None
    
    header_part, data_part = line.split(";", 1)
    header_tokens = header_part.split(",")
    data_tokens = data_part.split(",")
    
    # 헤더에서 GPS 시간 추출
    timestamp = 0.0
    utc_str = ""
    try:
        if len(header_tokens) >= 7:
            gps_week = int(header_tokens[5])
            gps_seconds = float(header_tokens[6])
            gps_epoch = datetime.datetime(1980, 1, 6, 0, 0, 0, tzinfo=datetime.timezone.utc)
            # UTC 시간 계산
            utc_dt = gps_epoch + datetime.timedelta(weeks=gps_week, seconds=gps_seconds - leap_seconds)
            
            # KST (UTC+9) 시간대로 변환
            kst_tz = datetime.timezone(datetime.timedelta(hours=9))
            kst_dt = utc_dt.astimezone(kst_tz)
            
            utc_str = kst_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-2]
            timestamp = kst_dt.timestamp()
    except (ValueError, IndexError):
        return None
    
    # 데이터 파트 파싱
    if len(data_tokens) < 12:
        return None
    
    try:
        ins_status = data_tokens[0]
        pos_type = data_tokens[1]
        lat = float(data_tokens[2])
        lon = float(data_tokens[3])
        hgt = float(data_tokens[4])
        n_vel = float(data_tokens[6])
        e_vel = float(data_tokens[7])
        u_vel = float(data_tokens[8])
        roll = float(data_tokens[9])
        pitch = float(data_tokens[10])
        azimuth = float(data_tokens[11])
    except (ValueError, IndexError):
        return None
    
    return {
        'timestamp': timestamp,
        'utc_str': utc_str,
        'latitude': lat,
        'longitude': lon,
        'height': hgt,
        'n_vel': n_vel,
        'e_vel': e_vel,
        'u_vel': u_vel,
        'roll': roll,
        'pitch': pitch,
        'azimuth': azimuth,
        'ins_status': ins_status,
        'pos_type': pos_type
    }


def sanitize_gnss_sentence(raw_text: str) -> Optional[str]:
    """GNSS 수신 문자열에서 제어문자를 제거하고 정규화합니다.
    
    Args:
        raw_text: 원시 GNSS 문장
    
    Returns:
        정규화된 문장 또는 None
    """
    if not raw_text:
        return None
    
    # INSPVAXA만 로깅 대상으로 제한
    if "#INSPVAXA" not in raw_text:
        return None
    
    # 제어문자 제거 (탭/공백 제외)
    cleaned = "".join(
        ch
        for ch in raw_text
        if (ch == "\t")
        or (" " <= ch <= "~" and ch != "\x7f")
    ).strip()
    
    if not cleaned:
        return None
    
    # #INSPVAXA 앞의 쓰레기 바이트 제거
    cleaned = cleaned[cleaned.find("#INSPVAXA"):]
    cleaned = cleaned.strip()
    
    if not cleaned or not cleaned.startswith("#INSPVAXA"):
        return None
    
    return cleaned


def parse_h5_radar(h5_file, frame_idx: int = None) -> Optional[Dict[str, Any]]:
    """H5 Radar 파일에서 데이터를 파싱합니다.
    
    Args:
        h5_file: h5py.File 객체
        frame_idx: 특정 프레임 인덱스 (None이면 전체)
    
    Returns:
        파싱된 Radar 데이터 딕셔너리
        {
            'timestamps': list,    # Unix timestamp 목록
            'scans': list,         # Measurement 데이터 (포인트 클라우드)
            'tracks': list         # Object 데이터 (트랙)
        }
    """
    try:
        result = {
            'timestamps': [],
            'scans': [],
            'tracks': []
        }
        
        # Timestamp 그룹에서 시간 정보 추출
        if 'Timestamp' in h5_file:
            timestamp_group = h5_file['Timestamp']
            if 'unix_timestamp_us' in timestamp_group:
                timestamps = timestamp_group['unix_timestamp_us'][:]
                result['timestamps'] = timestamps.tolist()
        
        # Measurement 그룹에서 scan 데이터 추출
        if 'Measurement' in h5_file:
            measurement_group = h5_file['Measurement']
            if frame_idx is not None:
                # 특정 프레임만 추출
                frame_key = f'{frame_idx:06d}'
                if frame_key in measurement_group:
                    result['scans'] = [measurement_group[frame_key][:]]
            else:
                # 전체 프레임 추출
                for key in sorted(measurement_group.keys()):
                    result['scans'].append(measurement_group[key][:])
        
        # Object 그룹에서 track 데이터 추출
        if 'Object' in h5_file:
            object_group = h5_file['Object']
            if frame_idx is not None:
                # 특정 프레임만 추출
                frame_key = f'{frame_idx:06d}'
                if frame_key in object_group:
                    result['tracks'] = [object_group[frame_key][:]]
            else:
                # 전체 프레임 추출
                for key in sorted(object_group.keys()):
                    result['tracks'].append(object_group[key][:])
        
        return result
        
    except Exception as e:
        print(f"H5 파싱 오류: {e}")
        return None


def ned_to_body_velocity(north: float, east: float, heading_deg: float) -> Tuple[float, float]:
    """NED 좌표계 속도를 Body 좌표계로 변환합니다.
    
    Args:
        north: North 방향 속도 (m/s)
        east: East 방향 속도 (m/s)
        heading_deg: Heading 각도 (도)
    
    Returns:
        (v_x, v_y): Body 좌표계 속도 (전방, 좌측)
    """
    import math
    
    heading_rad = math.radians(heading_deg)
    
    # Rotation matrix: NED to Body
    # Body X (forward) = North*cos(heading) + East*sin(heading)
    # Body Y (left) = -North*sin(heading) + East*cos(heading)
    v_x = north * math.cos(heading_rad) + east * math.sin(heading_rad)
    v_y = -north * math.sin(heading_rad) + east * math.cos(heading_rad)
    
    return v_x, v_y
