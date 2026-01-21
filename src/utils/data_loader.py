"""멀티센서 데이터 로딩 및 동기화"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import bisect
import json


@dataclass
class TimedItem:
    """타임스탬프 기반 데이터 컨테이너"""
    ros_time: float  # Unix timestamp (second)
    data: Any        # 파일 경로, 딕셔너리 등 임의 데이터


class DataLoader:
    """
    멀티센서 데이터셋 로딩 및 시간 동기화를 담당하는 클래스
    
    주요 기능:
    - LiDAR 기준 시간축으로 모든 센서 데이터 정렬
    - 최근접 타임스탬프 매칭 (bisect 기반)
    - Source/Raw 데이터셋 포맷 지원
    
    사용 예시:
        loader = DataLoader("dataset/20260114_172307")
        sync_data = loader.get_sync_frame(lidar_idx=0)
        print(sync_data['lidar']['ros_time'])
        print(sync_data['camera']['by_name']['front_left']['ros_time'])
    """
    
    def __init__(self, dataset_path: str) -> None:
        """데이터셋을 로드하고 인덱싱합니다.
        
        Args:
            dataset_path: 데이터셋 루트 경로
        """
        self.dataset_path = Path(dataset_path)
        self.metadata = self._load_metadata()
        
        # 센서 디렉토리 경로 설정
        self._setup_paths()
        
        # 센서 데이터 인덱싱
        self.camera_names: List[str] = []
        self.point_files: List[TimedItem] = []
        self.camera_frames: Dict[str, List[TimedItem]] = {}
        self.gnss_events: List[TimedItem] = []
        self.radar_scan_events: List[TimedItem] = []
        self.radar_track_events: List[TimedItem] = []
        self.perception_events: List[TimedItem] = []
        
        self._index_all_sensors()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """meta/meta.json 파일을 로드합니다."""
        meta_path = self.dataset_path / "meta" / "meta.json"
        if not meta_path.exists():
            # 구 포맷 호환
            meta_path = self.dataset_path / "metadata.json"
        
        if not meta_path.exists():
            return {}
        
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"메타데이터 로드 실패: {e}")
            return {}
    
    def _setup_paths(self) -> None:
        """센서 데이터 디렉토리 경로를 설정합니다."""
        # ref 센서
        ref_path = self.dataset_path / "ref"
        self.cam_dir = ref_path / "cam"
        self.lidar_dir = ref_path / "lidar" / "top"
        self.gnss_dir = self.dataset_path / "gnss"
        self.radar_dir = ref_path / "radar"
        self.perception_dir = ref_path / "perception"
        
        # 구 포맷 호환
        if not self.lidar_dir.exists():
            self.lidar_dir = self.dataset_path / "points"
        if not self.cam_dir.exists():
            self.cam_dir = self.dataset_path / "cam"
        if not self.radar_dir.exists():
            self.radar_dir = self.dataset_path / "radar"
        if not self.perception_dir.exists():
            self.perception_dir = self.dataset_path / "perception"
    
    def _index_all_sensors(self) -> None:
        """모든 센서 데이터를 인덱싱합니다."""
        self._index_lidar()
        self._index_cameras()
        self._index_gnss()
        self._index_radar()
        self._index_perception()
    
    def _index_lidar(self) -> None:
        """LiDAR 파일을 인덱싱합니다 (BIN 파일)."""
        if not self.lidar_dir.exists():
            return
        
        items = []
        for path in sorted(self.lidar_dir.glob("*.bin")):
            # 파일명: {unixtimestamp_us}.bin
            try:
                timestamp_us = int(path.stem)
                ros_time = timestamp_us / 1e6  # 마이크로초 -> 초
                items.append(TimedItem(ros_time=ros_time, data=str(path)))
            except ValueError:
                continue
        
        items.sort(key=lambda x: x.ros_time)
        self.point_files = items
    
    def _index_cameras(self) -> None:
        """카메라 파일을 인덱싱합니다 (PNG 또는 AVI+TXT)."""
        if not self.cam_dir.exists():
            return
        
        # 카메라 채널 탐색
        self.camera_names = [d.name for d in self.cam_dir.iterdir() if d.is_dir()]
        
        for cam_name in self.camera_names:
            cam_path = self.cam_dir / cam_name
            items = []
            
            # PNG 파일 (Source 포맷)
            for png_path in sorted(cam_path.glob("*.png")):
                try:
                    timestamp_us = int(png_path.stem)
                    ros_time = timestamp_us / 1e6
                    items.append(TimedItem(ros_time=ros_time, data=str(png_path)))
                except ValueError:
                    continue
            
            # AVI+TXT 파일 (Raw 포맷)
            if not items:
                for txt_path in sorted(cam_path.glob("*.txt")):
                    avi_path = cam_path / f"{txt_path.stem}.avi"
                    if not avi_path.exists():
                        continue
                    
                    try:
                        with open(txt_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            for line in lines[1:]:  # 헤더 스킵
                                parts = line.strip().split(",")
                                if len(parts) < 3:
                                    continue
                                frame_idx = int(parts[0])
                                ros_time = float(parts[2])
                                items.append(TimedItem(
                                    ros_time=ros_time,
                                    data={"video_path": str(avi_path), "frame_no": frame_idx}
                                ))
                    except Exception:
                        continue
            
            items.sort(key=lambda x: x.ros_time)
            self.camera_frames[cam_name] = items
    
    def _index_gnss(self) -> None:
        """GNSS 파일을 인덱싱합니다 (JSON 또는 TXT)."""
        # JSON 파일 (Source 포맷)
        if self.gnss_dir.exists():
            items = []
            for json_path in sorted(self.gnss_dir.glob("*.json")):
                try:
                    timestamp_us = int(json_path.stem)
                    ros_time = timestamp_us / 1e6
                    items.append(TimedItem(ros_time=ros_time, data=str(json_path)))
                except ValueError:
                    continue
            items.sort(key=lambda x: x.ros_time)
            self.gnss_events = items
        
        # TXT 파일 (Raw 포맷)
        if not self.gnss_events:
            gnss_txt = self.gnss_dir / "gnss.txt"
            if gnss_txt.exists():
                from .parsers import parse_inspvaxa_line
                items = []
                try:
                    with open(gnss_txt, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line.startswith("#INSPVAXA"):
                                continue
                            parsed = parse_inspvaxa_line(line)
                            if parsed:
                                items.append(TimedItem(ros_time=parsed['timestamp'], data=parsed))
                except Exception as e:
                    print(f"GNSS TXT 파싱 실패: {e}")
                items.sort(key=lambda x: x.ros_time)
                self.gnss_events = items
    
    def _index_radar(self) -> None:
        """Radar 파일을 인덱싱합니다 (BIN/JSON 또는 H5)."""
        if not self.radar_dir.exists():
            return
        
        # Radar 채널 탐색 (front, left, right, rear)
        for radar_channel in self.radar_dir.iterdir():
            if not radar_channel.is_dir():
                continue
            
            # Scan 데이터 (BIN)
            scan_dir = radar_channel / "scan"
            if scan_dir.exists():
                items = []
                for bin_path in sorted(scan_dir.glob("*.bin")):
                    try:
                        timestamp_us = int(bin_path.stem)
                        ros_time = timestamp_us / 1e6
                        items.append(TimedItem(ros_time=ros_time, data=str(bin_path)))
                    except ValueError:
                        continue
                items.sort(key=lambda x: x.ros_time)
                self.radar_scan_events.extend(items)
            
            # Track 데이터 (JSON)
            track_dir = radar_channel / "track"
            if track_dir.exists():
                items = []
                for json_path in sorted(track_dir.glob("*.json")):
                    try:
                        timestamp_us = int(json_path.stem)
                        ros_time = timestamp_us / 1e6
                        items.append(TimedItem(ros_time=ros_time, data=str(json_path)))
                    except ValueError:
                        continue
                items.sort(key=lambda x: x.ros_time)
                self.radar_track_events.extend(items)
    
    def _index_perception(self) -> None:
        """Perception 파일을 인덱싱합니다 (JSON 또는 JSONL)."""
        if not self.perception_dir.exists():
            return
        
        # Object 데이터
        object_dir = self.perception_dir / "object"
        if object_dir.exists():
            items = []
            for json_path in sorted(object_dir.glob("*.json")):
                try:
                    timestamp_us = int(json_path.stem)
                    ros_time = timestamp_us / 1e6
                    items.append(TimedItem(ros_time=ros_time, data=str(json_path)))
                except ValueError:
                    continue
            items.sort(key=lambda x: x.ros_time)
            self.perception_events = items
    
    def _find_closest(self, events: List[TimedItem], target_time: float) -> Optional[TimedItem]:
        """최근접 타임스탬프 이벤트를 찾습니다 (bisect 기반).
        
        Args:
            events: 타임스탬프 정렬된 이벤트 리스트
            target_time: 기준 시간
        
        Returns:
            가장 가까운 이벤트 또는 None
        """
        if not events:
            return None
        
        # bisect로 삽입 위치 찾기
        times = [e.ros_time for e in events]
        idx = bisect.bisect_left(times, target_time)
        
        # 경계 처리
        if idx == 0:
            return events[0]
        if idx == len(events):
            return events[-1]
        
        # 좌우 비교
        left = events[idx - 1]
        right = events[idx]
        
        if abs(left.ros_time - target_time) < abs(right.ros_time - target_time):
            return left
        return right
    
    def get_sync_frame(self, lidar_idx: int) -> Optional[Dict[str, Any]]:
        """LiDAR 프레임 기준으로 동기화된 센서 데이터를 반환합니다.
        
        Args:
            lidar_idx: LiDAR 프레임 인덱스
        
        Returns:
            동기화 결과 딕셔너리
            {
                'lidar': {'idx': int, 'ros_time': float, 'data': str},
                'camera': {'by_name': {'front_left': {...}, ...}},
                'gnss': {'idx': int, 'ros_time': float, 'data': dict},
                'radar': {'scans': {...}, 'tracks': {...}},
                'perception': {'idx': int, 'ros_time': float, 'data': str}
            }
        """
        if lidar_idx < 0 or lidar_idx >= len(self.point_files):
            return None
        
        lidar_item = self.point_files[lidar_idx]
        target_time = lidar_item.ros_time
        
        result = {
            'lidar': {
                'idx': lidar_idx,
                'ros_time': lidar_item.ros_time,
                'data': lidar_item.data
            },
            'camera': {'by_name': {}},
            'gnss': None,
            'radar': {'scans': None, 'tracks': None},
            'perception': None
        }
        
        # Camera 매칭
        for cam_name, cam_events in self.camera_frames.items():
            cam_match = self._find_closest(cam_events, target_time)
            if cam_match:
                cam_idx = cam_events.index(cam_match)
                result['camera']['by_name'][cam_name] = {
                    'idx': cam_idx,
                    'ros_time': cam_match.ros_time,
                    'data': cam_match.data
                }
        
        # GNSS 매칭
        gnss_match = self._find_closest(self.gnss_events, target_time)
        if gnss_match:
            result['gnss'] = {
                'idx': self.gnss_events.index(gnss_match),
                'ros_time': gnss_match.ros_time,
                'data': gnss_match.data
            }
        
        # Radar 매칭
        radar_scan_match = self._find_closest(self.radar_scan_events, target_time)
        if radar_scan_match:
            result['radar']['scans'] = {
                'idx': self.radar_scan_events.index(radar_scan_match),
                'ros_time': radar_scan_match.ros_time,
                'data': radar_scan_match.data
            }
        
        radar_track_match = self._find_closest(self.radar_track_events, target_time)
        if radar_track_match:
            result['radar']['tracks'] = {
                'idx': self.radar_track_events.index(radar_track_match),
                'ros_time': radar_track_match.ros_time,
                'data': radar_track_match.data
            }
        
        # Perception 매칭
        perc_match = self._find_closest(self.perception_events, target_time)
        if perc_match:
            result['perception'] = {
                'idx': self.perception_events.index(perc_match),
                'ros_time': perc_match.ros_time,
                'data': perc_match.data
            }
        
        return result
