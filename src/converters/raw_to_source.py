"""Raw 데이터를 Source 포맷으로 변환하는 모듈

주요 기능:
1. 모든 센서의 교집합 시간 영역 내 데이터만 변환 (최대 100ms 허용)
2. 센서별 데이터를 unix timestamp 기반 개별 파일로 분할 저장
3. Perception timestamp는 time_stamp 키 사용 (19자리 중 16자리만 파일명으로 활용)
4. Radar scan은 Measurement 데이터, track은 Object 데이터 사용
5. GNSS는 #INSPVAXA 형식 파싱하여 timestamp 추출
"""

import os
import glob
import shutil
import json
import bisect
import csv
import numpy as np
import cv2
import h5py
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from tqdm import tqdm

from ..utils.parsers import parse_inspvaxa_line, sanitize_gnss_sentence

# 센서 간 시작/끝 시간 딜레이 허용치 (마이크로초)
MAX_TIME_DIFF_US = 50_000  # 100ms = 100,000us


@dataclass
class SensorTimeRange:
    """센서별 시간 범위 정보를 담는 클래스"""
    sensor_name: str
    start_time: int  # 마이크로초 (16자리)
    end_time: int    # 마이크로초 (16자리)
    frame_count: int
    timestamps: List[int]  # 모든 프레임의 타임스탬프 목록


def _ensure_dir(path: str) -> None:
    """디렉토리가 존재하지 않으면 생성합니다."""
    if not os.path.exists(path):
        os.makedirs(path)


def _is_within_range(timestamp: int, start: int, end: int) -> bool:
    """타임스탬프가 허용 범위 내에 있는지 확인합니다."""
    return (start - MAX_TIME_DIFF_US) <= timestamp <= (end + MAX_TIME_DIFF_US)


def _get_gnss_time_range(src_scene_path: str) -> Optional[SensorTimeRange]:
    """GNSS 데이터의 시간 범위를 계산합니다."""
    src_gnss_path = os.path.join(src_scene_path, "gnss", "gnss.txt")
    if not os.path.exists(src_gnss_path):
        print(f"[GNSS] 파일을 찾을 수 없음: {src_gnss_path}")
        return None

    try:
        timestamps = []
        with open(src_gnss_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                sentence = sanitize_gnss_sentence(raw_line)
                if not sentence:
                    continue

                parsed = parse_inspvaxa_line(sentence)
                if not parsed or parsed.get('timestamp', 0) <= 0:
                    continue

                # timestamp는 초 단위 -> 마이크로초로 변환
                ts_us = int(parsed['timestamp'] * 1e6)
                timestamps.append(ts_us)

        if not timestamps:
            return None

        return SensorTimeRange(
            sensor_name="gnss",
            start_time=min(timestamps),
            end_time=max(timestamps),
            frame_count=len(timestamps),
            timestamps=sorted(timestamps)
        )
    except Exception as e:
        print(f"[GNSS] 시간 범위 계산 오류: {e}")
        return None


def _get_lidar_time_range(src_scene_path: str) -> Dict[str, SensorTimeRange]:
    """LiDAR 데이터의 시간 범위를 계산합니다."""
    src_lidar_root = os.path.join(src_scene_path, "ref", "lidar")
    if not os.path.exists(src_lidar_root):
        print(f"[LiDAR] 경로를 찾을 수 없음: {src_lidar_root}")
        return {}

    result = {}
    for model_name in os.listdir(src_lidar_root):
        src_model_dir = os.path.join(src_lidar_root, model_name)
        if not os.path.isdir(src_model_dir):
            continue

        files = glob.glob(os.path.join(src_model_dir, "*.bin"))
        timestamps = []

        for f in files:
            try:
                ts = int(os.path.splitext(os.path.basename(f))[0])
                timestamps.append(ts)
            except ValueError:
                continue

        if not timestamps:
            continue

        result[model_name] = SensorTimeRange(
            sensor_name=f"lidar_{model_name}",
            start_time=min(timestamps),
            end_time=max(timestamps),
            frame_count=len(timestamps),
            timestamps=sorted(timestamps)
        )

    return result


def _get_camera_time_range(src_scene_path: str) -> Dict[str, SensorTimeRange]:
    """카메라 데이터의 시간 범위를 계산합니다."""
    src_cam_root = os.path.join(src_scene_path, "ref", "cam")
    if not os.path.exists(src_cam_root):
        print(f"[Camera] 경로를 찾을 수 없음: {src_cam_root}")
        return {}

    result = {}
    for pos_name in os.listdir(src_cam_root):
        src_pos_dir = os.path.join(src_cam_root, pos_name)
        if not os.path.isdir(src_pos_dir):
            continue

        avi_files = glob.glob(os.path.join(src_pos_dir, "*.avi"))
        all_timestamps = []

        for avi_path in avi_files:
            txt_path = avi_path.replace(".avi", ".txt")
            if not os.path.exists(txt_path):
                continue

            try:
                df = pd.read_csv(txt_path)
                for _, row in df.iterrows():
                    if 'ros_epoch' in row and pd.notna(row['ros_epoch']):
                        ts = int(row['ros_epoch'] * 1e6)
                        all_timestamps.append(ts)
            except Exception:
                continue

        if not all_timestamps:
            continue

        result[pos_name] = SensorTimeRange(
            sensor_name=f"camera_{pos_name}",
            start_time=min(all_timestamps),
            end_time=max(all_timestamps),
            frame_count=len(all_timestamps),
            timestamps=sorted(all_timestamps)
        )

    return result


def _get_radar_time_range(src_scene_path: str) -> Dict[str, SensorTimeRange]:
    """레이더 데이터의 시간 범위를 계산합니다."""
    src_radar_root = os.path.join(src_scene_path, "ref", "radar")
    if not os.path.exists(src_radar_root):
        print(f"[Radar] 경로를 찾을 수 없음: {src_radar_root}")
        return {}

    result = {}
    for pos_name in os.listdir(src_radar_root):
        src_pos_dir = os.path.join(src_radar_root, pos_name)
        if not os.path.isdir(src_pos_dir):
            continue

        h5_files = glob.glob(os.path.join(src_pos_dir, "*.h5"))
        all_timestamps = []

        for h5_path in h5_files:
            # _repacked.h5 파일은 건너뜀
            if "_repacked" in h5_path:
                continue
            try:
                with h5py.File(h5_path, 'r') as f:
                    for key in f.keys():
                        if not key.startswith("SCAN_"):
                            continue
                        group = f[key]
                        if 'Timestamp' in group:
                            ts_data = group['Timestamp'][()]
                            if hasattr(ts_data, '__iter__'):
                                ts = int(ts_data[0])
                            else:
                                ts = int(ts_data)
                            all_timestamps.append(ts)
            except Exception as e:
                print(f"[Radar] H5 파일 읽기 오류 {h5_path}: {e}")
                continue

        if not all_timestamps:
            continue

        result[pos_name] = SensorTimeRange(
            sensor_name=f"radar_{pos_name}",
            start_time=min(all_timestamps),
            end_time=max(all_timestamps),
            frame_count=len(all_timestamps),
            timestamps=sorted(all_timestamps)
        )

    return result


def _get_perception_time_range(src_scene_path: str) -> Dict[str, SensorTimeRange]:
    """Perception 데이터의 시간 범위를 계산합니다."""
    src_percep_root = os.path.join(src_scene_path, "ref", "perception")
    if not os.path.exists(src_percep_root):
        print(f"[Perception] 경로를 찾을 수 없음: {src_percep_root}")
        return {}

    result = {}
    jsonl_files = glob.glob(os.path.join(src_percep_root, "*.jsonl"))

    for jsonl_path in jsonl_files:
        filename = os.path.basename(jsonl_path)
        type_name = os.path.splitext(filename)[0]

        timestamps = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = None
                        if 'time_stamp' in data:
                            ts_raw = data['time_stamp']
                            ts_str = str(ts_raw)[:16]
                            ts = int(ts_str)
                        elif 'timestamp' in data:
                            ts_raw = data['timestamp']
                            if isinstance(ts_raw, float):
                                ts = int(ts_raw * 1e6)
                            else:
                                ts_str = str(ts_raw)[:16]
                                ts = int(ts_str)

                        if ts:
                            timestamps.append(ts)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception as e:
            print(f"[Perception] 파일 읽기 오류 {jsonl_path}: {e}")
            continue

        if not timestamps:
            continue

        result[type_name] = SensorTimeRange(
            sensor_name=f"perception_{type_name}",
            start_time=min(timestamps),
            end_time=max(timestamps),
            frame_count=len(timestamps),
            timestamps=sorted(timestamps)
        )

    return result


def _collect_all_sensor_time_ranges(src_scene_path: str) -> List[SensorTimeRange]:
    """모든 센서의 시간 범위 정보를 수집합니다."""
    all_ranges = []

    gnss_range = _get_gnss_time_range(src_scene_path)
    if gnss_range:
        all_ranges.append(gnss_range)

    lidar_ranges = _get_lidar_time_range(src_scene_path)
    all_ranges.extend(lidar_ranges.values())

    camera_ranges = _get_camera_time_range(src_scene_path)
    all_ranges.extend(camera_ranges.values())

    radar_ranges = _get_radar_time_range(src_scene_path)
    all_ranges.extend(radar_ranges.values())

    perception_ranges = _get_perception_time_range(src_scene_path)
    all_ranges.extend(perception_ranges.values())

    return all_ranges


def _calculate_intersection_time_range(all_ranges: List[SensorTimeRange]) -> Tuple[int, int]:
    """모든 센서의 교집합 시간 범위를 계산합니다."""
    if not all_ranges:
        raise ValueError("센서 시간 범위 정보가 없습니다.")

    print("\n=== 센서별 시간 범위 ===")
    for r in all_ranges:
        duration_sec = (r.end_time - r.start_time) / 1e6
        print(f"  {r.sensor_name}: {r.start_time} ~ {r.end_time} ({r.frame_count} frames, {duration_sec:.2f}s)")

    common_start = max(r.start_time for r in all_ranges)
    common_end = min(r.end_time for r in all_ranges)

    print(f"\n=== 교집합 시간 범위 (100ms 허용) ===")
    print(f"  교집합: {common_start} ~ {common_end}")
    common_duration_sec = (common_end - common_start) / 1e6
    print(f"  교집합 구간: {common_duration_sec:.2f}s")

    print(f"\n=== 센서별 교집합 영향 분석 ===")
    print(f"  {'센서명':<25} {'원본 프레임':>12} {'교집합 범위 내':>14} {'보존율':>10} {'제외 프레임':>12}")
    print("  " + "-" * 75)

    for r in all_ranges:
        frames_in_range = sum(
            1 for ts in r.timestamps
            if _is_within_range(ts, common_start, common_end)
        )
        retention_rate = (frames_in_range / r.frame_count * 100) if r.frame_count > 0 else 0
        excluded = r.frame_count - frames_in_range

        print(f"  {r.sensor_name:<25} {r.frame_count:>12} {frames_in_range:>14} {retention_rate:>9.1f}% {excluded:>12}")

    print("  " + "-" * 75)

    if common_start > common_end:
        if (common_start - common_end) <= MAX_TIME_DIFF_US:
            print("  [경고] 교집합이 없으나 100ms 허용 범위 내에서 겹침")
            mid = (common_start + common_end) // 2
            return mid, mid
        else:
            raise ValueError("센서 간 교집합 시간 범위가 존재하지 않습니다.")

    return common_start, common_end


def _convert_gnss(src_scene_path: str, dst_scene_path: str,
                  common_start: int, common_end: int) -> int:
    """GNSS 데이터를 변환합니다."""
    src_gnss_path = os.path.join(src_scene_path, "gnss", "gnss.txt")
    if not os.path.exists(src_gnss_path):
        print(f"[GNSS] 파일을 찾을 수 없음: {src_gnss_path}")
        return 0

    dst_gnss_dir = os.path.join(dst_scene_path, "gnss")
    _ensure_dir(dst_gnss_dir)

    print(f"[GNSS] 변환 시작: {src_gnss_path}")

    converted_count = 0
    try:
        with open(src_gnss_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                sentence = sanitize_gnss_sentence(raw_line)
                if not sentence:
                    continue

                parsed = parse_inspvaxa_line(sentence)
                if not parsed or parsed.get('timestamp', 0) <= 0:
                    continue

                ts_us = int(parsed['timestamp'] * 1e6)

                if not _is_within_range(ts_us, common_start, common_end):
                    continue

                # 딕셔너리로 변환하여 저장
                data_dict = {
                    "timestamp": parsed['timestamp'],
                    "latitude": parsed['latitude'],
                    "longitude": parsed['longitude'],
                    "height": parsed['height'],
                    "north_vel": parsed['n_vel'],
                    "east_vel": parsed['e_vel'],
                    "up_vel": parsed['u_vel'],
                    "roll": parsed['roll'],
                    "pitch": parsed['pitch'],
                    "azimuth": parsed['azimuth'],
                    "ins_status": parsed['ins_status'],
                    "pos_type": parsed['pos_type'],
                    "utc_time": parsed['utc_str'],
                    "sentence": sentence
                }

                json_path = os.path.join(dst_gnss_dir, f"{ts_us}.json")
                with open(json_path, 'w', encoding='utf-8') as out_f:
                    json.dump(data_dict, out_f, indent=4)
                converted_count += 1

        print(f"[GNSS] 변환 완료: {converted_count} 프레임")

    except Exception as e:
        print(f"[GNSS] 변환 중 오류 발생: {e}")

    return converted_count


def _convert_lidar(src_scene_path: str, dst_scene_path: str,
                   common_start: int, common_end: int) -> int:
    """LiDAR 데이터를 변환합니다 (교집합 범위만 복사)."""
    src_lidar_root = os.path.join(src_scene_path, "ref", "lidar")
    if not os.path.exists(src_lidar_root):
        print(f"[LiDAR] 경로를 찾을 수 없음: {src_lidar_root}")
        return 0

    dst_lidar_root = os.path.join(dst_scene_path, "ref", "lidar")
    total_copied = 0

    for model_name in os.listdir(src_lidar_root):
        src_model_dir = os.path.join(src_lidar_root, model_name)
        if not os.path.isdir(src_model_dir):
            continue

        dst_model_dir = os.path.join(dst_lidar_root, model_name)
        _ensure_dir(dst_model_dir)

        print(f"[LiDAR] {model_name} 복사 시작...")

        files = glob.glob(os.path.join(src_model_dir, "*.bin"))
        copied_count = 0

        for src_file in files:
            file_name = os.path.basename(src_file)
            try:
                ts = int(os.path.splitext(file_name)[0])
                if not _is_within_range(ts, common_start, common_end):
                    continue
            except ValueError:
                continue

            dst_file = os.path.join(dst_model_dir, file_name)
            shutil.copy2(src_file, dst_file)
            copied_count += 1

        print(f"[LiDAR] {model_name} 복사 완료: {copied_count} 파일")
        total_copied += copied_count

    return total_copied


def _convert_camera(src_scene_path: str, dst_scene_path: str,
                    common_start: int, common_end: int) -> int:
    """카메라 데이터를 변환합니다 (AVI → PNG)."""
    src_cam_root = os.path.join(src_scene_path, "ref", "cam")
    if not os.path.exists(src_cam_root):
        print(f"[Camera] 경로를 찾을 수 없음: {src_cam_root}")
        return 0

    dst_cam_root = os.path.join(dst_scene_path, "ref", "cam")
    total_frames = 0

    for pos_name in os.listdir(src_cam_root):
        src_pos_dir = os.path.join(src_cam_root, pos_name)
        if not os.path.isdir(src_pos_dir):
            continue

        dst_pos_dir = os.path.join(dst_cam_root, pos_name)
        _ensure_dir(dst_pos_dir)

        print(f"[Camera] {pos_name} 변환 시작...")

        avi_files = sorted(glob.glob(os.path.join(src_pos_dir, "*.avi")))
        position_frames = 0

        for avi_path in avi_files:
            txt_path = avi_path.replace(".avi", ".txt")
            if not os.path.exists(txt_path):
                print(f"[Camera] .txt 파일을 찾을 수 없음 (스킵): {txt_path}")
                continue

            try:
                df = pd.read_csv(txt_path)
                timestamps = []
                for _, row in df.iterrows():
                    if 'ros_epoch' in row and pd.notna(row['ros_epoch']):
                        ts = int(row['ros_epoch'] * 1e6)
                        timestamps.append(ts)
            except Exception as e:
                print(f"[Camera] 타임스탬프 파일 읽기 실패: {e}")
                continue

            cap = cv2.VideoCapture(avi_path)
            if not cap.isOpened():
                print(f"[Camera] 비디오 열기 실패: {avi_path}")
                continue

            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx < len(timestamps):
                    ts = timestamps[frame_idx]
                    if _is_within_range(ts, common_start, common_end):
                        dst_png = os.path.join(dst_pos_dir, f"{ts}.png")
                        cv2.imwrite(dst_png, frame)
                        position_frames += 1

                frame_idx += 1

            cap.release()

        print(f"[Camera] {pos_name} 변환 완료: {position_frames} 프레임")
        total_frames += position_frames

    return total_frames


def _convert_radar(src_scene_path: str, dst_scene_path: str,
                   common_start: int, common_end: int) -> int:
    """레이더 데이터를 변환합니다."""
    src_radar_root = os.path.join(src_scene_path, "ref", "radar")
    if not os.path.exists(src_radar_root):
        print(f"[Radar] 경로를 찾을 수 없음: {src_radar_root}")
        return 0

    dst_radar_root = os.path.join(dst_scene_path, "ref", "radar")
    total_scans = 0

    for pos_name in os.listdir(src_radar_root):
        src_pos_dir = os.path.join(src_radar_root, pos_name)
        if not os.path.isdir(src_pos_dir):
            continue

        dst_pos_dir = os.path.join(dst_radar_root, pos_name)
        dst_scan_dir = os.path.join(dst_pos_dir, "scan")
        dst_track_dir = os.path.join(dst_pos_dir, "track")

        _ensure_dir(dst_pos_dir)
        _ensure_dir(dst_scan_dir)
        _ensure_dir(dst_track_dir)

        h5_files = glob.glob(os.path.join(src_pos_dir, "*.h5"))
        position_scans = 0

        for h5_path in h5_files:
            if "_repacked" in h5_path:
                continue

            file_name = os.path.basename(h5_path)

            # H5 파일 복사
            dst_h5_path = os.path.join(dst_pos_dir, file_name)
            print(f"[Radar] {pos_name} H5 복사: {file_name}")
            shutil.copy2(h5_path, dst_h5_path)

            try:
                with h5py.File(h5_path, 'r') as f:
                    for key in sorted(f.keys()):
                        if not key.startswith("SCAN_"):
                            continue

                        try:
                            group = f[key]

                            if 'Timestamp' not in group:
                                continue

                            ts_data = group['Timestamp'][()]
                            if hasattr(ts_data, '__iter__'):
                                ts = int(ts_data[0])
                            else:
                                ts = int(ts_data)

                            if not _is_within_range(ts, common_start, common_end):
                                continue

                            # Measurement -> scan .bin
                            if 'Measurement' in group:
                                meas_data = group['Measurement'][()]
                                bin_path = os.path.join(dst_scan_dir, f"{ts}.bin")
                                meas_data.tofile(bin_path)

                            # Object -> track .json
                            if 'Object' in group:
                                obj_data = group['Object'][()]
                                tracks = []
                                for row in obj_data:
                                    t = {
                                        "id": int(row["Id"]),
                                        "status": int(row["Status"]),
                                        "age": int(row["AliveAge"]),
                                        "x": float(row["XPos"]),
                                        "y": float(row["YPos"]),
                                        "z": float(row["ZPos"]),
                                        "vx": float(row["XVel"]),
                                        "vy": float(row["YVel"]),
                                        "width": float(row["Width"]),
                                        "length": float(row["Length"]),
                                        "height": float(row["Height"]),
                                        "heading": float(row["HeadAng"]),
                                        "power": float(row["Power"]),
                                        "type": int(row["Class"]),
                                    }
                                    tracks.append(t)

                                json_path = os.path.join(dst_track_dir, f"{ts}.json")
                                with open(json_path, 'w', encoding='utf-8') as jf:
                                    json.dump({"tracks": tracks, "timestamp": ts}, jf, indent=2)

                            position_scans += 1

                        except Exception as inner_e:
                            print(f"[Radar] 그룹 {key} 처리 중 오류: {inner_e}")

            except Exception as e:
                print(f"[Radar] H5 파일 처리 실패 {h5_path}: {e}")

        print(f"[Radar] {pos_name} 변환 완료: {position_scans} 스캔")
        total_scans += position_scans

    return total_scans


def _convert_perception(src_scene_path: str, dst_scene_path: str,
                        common_start: int, common_end: int) -> int:
    """Perception 데이터를 변환합니다."""
    src_percep_root = os.path.join(src_scene_path, "ref", "perception")
    if not os.path.exists(src_percep_root):
        print(f"[Perception] 경로를 찾을 수 없음: {src_percep_root}")
        return 0

    dst_percep_root = os.path.join(dst_scene_path, "ref", "perception")
    _ensure_dir(dst_percep_root)

    total_frames = 0
    jsonl_files = glob.glob(os.path.join(src_percep_root, "*.jsonl"))

    for jsonl_path in jsonl_files:
        filename = os.path.basename(jsonl_path)
        type_name = os.path.splitext(filename)[0]

        dst_type_dir = os.path.join(dst_percep_root, type_name)
        _ensure_dir(dst_type_dir)

        print(f"[Perception] {type_name} 변환 시작...")

        try:
            type_frames = 0
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)

                        ts = None
                        if 'time_stamp' in data:
                            ts_raw = data['time_stamp']
                            ts_str = str(ts_raw)[:16]
                            ts = int(ts_str)
                        elif 'timestamp' in data:
                            ts_raw = data['timestamp']
                            if isinstance(ts_raw, float):
                                ts = int(ts_raw * 1e6)
                            else:
                                ts_str = str(ts_raw)[:16]
                                ts = int(ts_str)

                        if ts is None:
                            continue

                        if not _is_within_range(ts, common_start, common_end):
                            continue

                        out_file = os.path.join(dst_type_dir, f"{ts}.json")
                        with open(out_file, 'w', encoding='utf-8') as out_f:
                            json.dump(data, out_f, indent=4, default=str)
                        type_frames += 1

                    except json.JSONDecodeError:
                        continue

            print(f"[Perception] {type_name} 완료: {type_frames} 프레임")
            total_frames += type_frames

        except Exception as e:
            print(f"[Perception] 파일 읽기 실패 {jsonl_path}: {e}")

    return total_frames


def _copy_meta(src_scene_path: str, dst_scene_path: str) -> None:
    """메타 데이터를 복사합니다."""
    src_meta = os.path.join(src_scene_path, "meta")
    dst_meta = os.path.join(dst_scene_path, "meta")

    if os.path.exists(src_meta):
        if os.path.exists(dst_meta):
            shutil.rmtree(dst_meta)
        shutil.copytree(src_meta, dst_meta)
        print("[Meta] 메타 데이터 복사 완료")
    else:
        _ensure_dir(dst_meta)
        print("[Meta] 원본 meta 폴더가 없어 빈 폴더 생성")


def _collect_output_timestamps(dst_scene_path: str) -> Dict[str, List[int]]:
    """출력 폴더에서 각 센서별 타임스탬프를 수집합니다."""
    timestamps = {}

    # GNSS
    gnss_dir = os.path.join(dst_scene_path, "gnss")
    if os.path.exists(gnss_dir):
        ts_list = []
        for f in glob.glob(os.path.join(gnss_dir, "*.json")):
            try:
                ts = int(os.path.splitext(os.path.basename(f))[0])
                ts_list.append(ts)
            except ValueError:
                continue
        timestamps["gnss"] = sorted(ts_list)

    # LiDAR
    lidar_root = os.path.join(dst_scene_path, "ref", "lidar")
    if os.path.exists(lidar_root):
        for model_name in os.listdir(lidar_root):
            model_dir = os.path.join(lidar_root, model_name)
            if not os.path.isdir(model_dir):
                continue
            ts_list = []
            for f in glob.glob(os.path.join(model_dir, "*.bin")):
                try:
                    ts = int(os.path.splitext(os.path.basename(f))[0])
                    ts_list.append(ts)
                except ValueError:
                    continue
            if ts_list:
                timestamps[f"ref_lidar_{model_name}"] = sorted(ts_list)

    # Camera
    cam_root = os.path.join(dst_scene_path, "ref", "cam")
    if os.path.exists(cam_root):
        for pos_name in os.listdir(cam_root):
            pos_dir = os.path.join(cam_root, pos_name)
            if not os.path.isdir(pos_dir):
                continue
            ts_list = []
            for f in glob.glob(os.path.join(pos_dir, "*.png")):
                try:
                    ts = int(os.path.splitext(os.path.basename(f))[0])
                    ts_list.append(ts)
                except ValueError:
                    continue
            if ts_list:
                timestamps[f"ref_cam_{pos_name}"] = sorted(ts_list)

    # Radar
    radar_root = os.path.join(dst_scene_path, "ref", "radar")
    if os.path.exists(radar_root):
        for pos_name in os.listdir(radar_root):
            pos_dir = os.path.join(radar_root, pos_name)
            if not os.path.isdir(pos_dir):
                continue

            scan_dir = os.path.join(pos_dir, "scan")
            if os.path.exists(scan_dir):
                ts_list = []
                for f in glob.glob(os.path.join(scan_dir, "*.bin")):
                    try:
                        ts = int(os.path.splitext(os.path.basename(f))[0])
                        ts_list.append(ts)
                    except ValueError:
                        continue
                if ts_list:
                    timestamps[f"ref_radar_{pos_name}_scan"] = sorted(ts_list)

            track_dir = os.path.join(pos_dir, "track")
            if os.path.exists(track_dir):
                ts_list = []
                for f in glob.glob(os.path.join(track_dir, "*.json")):
                    try:
                        ts = int(os.path.splitext(os.path.basename(f))[0])
                        ts_list.append(ts)
                    except ValueError:
                        continue
                if ts_list:
                    timestamps[f"ref_radar_{pos_name}_track"] = sorted(ts_list)

    # Perception
    percep_root = os.path.join(dst_scene_path, "ref", "perception")
    if os.path.exists(percep_root):
        for type_name in os.listdir(percep_root):
            type_dir = os.path.join(percep_root, type_name)
            if not os.path.isdir(type_dir):
                continue
            ts_list = []
            for f in glob.glob(os.path.join(type_dir, "*.json")):
                try:
                    ts = int(os.path.splitext(os.path.basename(f))[0])
                    ts_list.append(ts)
                except ValueError:
                    continue
            if ts_list:
                timestamps[f"ref_perception_{type_name}"] = sorted(ts_list)

    return timestamps


def _find_closest_timestamp(target: int, timestamps: List[int], max_diff: int = 50_000) -> Optional[int]:
    """타겟 타임스탬프에 가장 가까운 타임스탬프를 찾습니다."""
    if not timestamps:
        return None

    idx = bisect.bisect_left(timestamps, target)

    candidates = []
    if idx > 0:
        candidates.append(timestamps[idx - 1])
    if idx < len(timestamps):
        candidates.append(timestamps[idx])

    if not candidates:
        return None

    closest = min(candidates, key=lambda x: abs(x - target))

    if abs(closest - target) <= max_diff:
        return closest
    return None


def _generate_matching_csv(dst_scene_path: str, reference_sensor: str = "ref_perception_object") -> int:
    """matching.csv를 생성합니다.

    Args:
        dst_scene_path: 출력 Source 데이터 씬 경로
        reference_sensor: 기준 센서 키 (기본값: ref_perception_object)
            - "gnss": GNSS (100Hz)
            - "ref_lidar_*": LiDAR
            - "ref_cam_*": Camera
            - "ref_radar_*_scan": Radar
            - "ref_perception_*": Perception
    """
    all_timestamps = _collect_output_timestamps(dst_scene_path)

    # 기준 센서 자동 탐색: 정확히 일치하는 키가 없으면 prefix로 검색
    ref_key = None
    if reference_sensor in all_timestamps:
        ref_key = reference_sensor
    else:
        # prefix 매칭 (예: ref_perception_object -> ref_perception_object)
        for key in all_timestamps.keys():
            if key.startswith(reference_sensor) or reference_sensor in key:
                ref_key = key
                break

    if ref_key is None or not all_timestamps.get(ref_key):
        print(f"[Matching] 기준 센서 '{reference_sensor}'를 찾을 수 없습니다.")
        print(f"[Matching] 사용 가능한 센서: {list(all_timestamps.keys())}")
        # fallback: 가장 적은 프레임 수를 가진 센서 선택
        if all_timestamps:
            ref_key = min(all_timestamps.keys(), key=lambda k: len(all_timestamps[k]))
            print(f"[Matching] Fallback: '{ref_key}' 사용 ({len(all_timestamps[ref_key])} 프레임)")
        else:
            print("[Matching] 타임스탬프 데이터가 없습니다.")
            return 0

    ref_timestamps = all_timestamps[ref_key]
    print(f"[Matching] 기준 센서: {ref_key} ({len(ref_timestamps)} 프레임)")

    other_sensors = sorted([k for k in all_timestamps.keys() if k != ref_key])
    fieldnames = ["idx", ref_key] + other_sensors

    all_rows = []
    for idx, ref_ts in enumerate(ref_timestamps):
        row = {"idx": idx, ref_key: ref_ts}

        for sensor in other_sensors:
            sensor_ts_list = all_timestamps.get(sensor, [])
            closest = _find_closest_timestamp(ref_ts, sensor_ts_list)
            row[sensor] = closest if closest else ""

        all_rows.append(row)

    def is_complete_row(row):
        for sensor in other_sensors:
            if row.get(sensor) == "" or row.get(sensor) is None:
                return False
        return True

    start_idx = 0
    for i, row in enumerate(all_rows):
        if is_complete_row(row):
            start_idx = i
            break

    end_idx = len(all_rows) - 1
    for i in range(len(all_rows) - 1, -1, -1):
        if is_complete_row(all_rows[i]):
            end_idx = i
            break

    trimmed_rows = []
    for i in range(start_idx, end_idx + 1):
        row = all_rows[i]
        if is_complete_row(row):
            new_row = {"idx": len(trimmed_rows)}
            new_row[ref_key] = row[ref_key]
            for sensor in other_sensors:
                new_row[sensor] = row[sensor]
            trimmed_rows.append(new_row)

    original_count = len(all_rows)
    trimmed_count = len(trimmed_rows)
    removed_start = start_idx
    removed_end = len(all_rows) - 1 - end_idx
    removed_middle = (end_idx - start_idx + 1) - trimmed_count

    print(f"[Matching] 트리밍 결과:")
    print(f"  원본 프레임: {original_count}")
    print(f"  시작 제거: {removed_start} 프레임")
    print(f"  끝 제거: {removed_end} 프레임")
    print(f"  중간 제거: {removed_middle} 프레임 (부분 누락)")
    print(f"  최종 프레임: {trimmed_count}")

    meta_dir = os.path.join(dst_scene_path, "meta")
    _ensure_dir(meta_dir)
    csv_path = os.path.join(meta_dir, "matching.csv")

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trimmed_rows)

    print(f"[Matching] matching.csv 생성 완료: {trimmed_count} 프레임")
    return trimmed_count


def _convert_single_scene(input_path: str, output_path: str, max_diff_us: int = 50_000,
                          reference_sensor: str = "ref_perception_object") -> bool:
    """단일 씬을 변환합니다."""
    print(f"=== Raw → Source 변환 시작 ===")
    print(f"원본: {input_path}")
    print(f"대상: {output_path}")
    print(f"시간 허용 범위: ±{MAX_TIME_DIFF_US / 1000:.0f}ms")

    if not os.path.exists(input_path):
        print("오류: 원본 경로가 존재하지 않습니다.")
        return False

    try:
        # 1. 모든 센서의 시간 범위 수집
        print("\n[1/8] 센서별 시간 범위 분석 중...")
        all_ranges = _collect_all_sensor_time_ranges(input_path)

        if not all_ranges:
            print("오류: 센서 데이터를 찾을 수 없습니다.")
            return False

        # 2. 교집합 시간 범위 계산
        common_start, common_end = _calculate_intersection_time_range(all_ranges)

        # 3. 출력 디렉토리 생성
        _ensure_dir(output_path)

        # 4. Meta Copy
        print("\n[2/8] Meta 데이터 복사 중...")
        _copy_meta(input_path, output_path)

        # 5. GNSS
        print("\n[3/8] GNSS 데이터 변환 중...")
        gnss_count = _convert_gnss(input_path, output_path, common_start, common_end)

        # 6. LiDAR
        print("\n[4/8] LiDAR 데이터 변환 중...")
        lidar_count = _convert_lidar(input_path, output_path, common_start, common_end)

        # 7. Camera
        print("\n[5/8] Camera 데이터 변환 중...")
        camera_count = _convert_camera(input_path, output_path, common_start, common_end)

        # 8. Radar
        print("\n[6/8] Radar 데이터 변환 중...")
        radar_count = _convert_radar(input_path, output_path, common_start, common_end)

        # 9. Perception
        print("\n[7/8] Perception 데이터 변환 중...")
        perception_count = _convert_perception(input_path, output_path, common_start, common_end)

        # 10. Matching CSV 생성
        print("\n[8/8] matching.csv 생성 중...")
        matching_count = _generate_matching_csv(output_path, reference_sensor)

        # 결과 요약
        print("\n" + "=" * 50)
        print("=== 변환 완료 요약 ===")
        print(f"  GNSS: {gnss_count} 프레임")
        print(f"  LiDAR: {lidar_count} 파일")
        print(f"  Camera: {camera_count} 프레임")
        print(f"  Radar: {radar_count} 스캔")
        print(f"  Perception: {perception_count} 프레임")
        print(f"  Matching: {matching_count} 프레임")
        print(f"\n  공통 시간 범위: {common_start} ~ {common_end}")
        print("=" * 50)

        return True

    except Exception as e:
        print(f"변환 중 오류 발생: {e}")
        return False


def _find_scene_folders(input_path: str) -> list:
    """입력 경로에서 씬 폴더들을 탐색합니다."""
    input_dir = Path(input_path)

    scene_indicators = ['ref', 'gnss', 'meta']
    if any((input_dir / indicator).exists() for indicator in scene_indicators):
        return [str(input_dir)]

    scenes = []
    for item in sorted(input_dir.iterdir()):
        if item.is_dir():
            if any((item / indicator).exists() for indicator in scene_indicators):
                scenes.append(str(item))

    return scenes


def convert_raw_to_source(input_path: str, output_path: str, max_diff_us: int = 50_000,
                          reference_sensor: str = "ref_perception_object") -> None:
    """Raw 데이터셋을 Source 포맷으로 변환합니다.

    주요 변환:
    - Camera: AVI 세그먼트 → PNG 프레임
    - LiDAR: BIN 유지 (복사)
    - Radar: H5 통합파일 → scan(BIN) + track(JSON) 분할
    - Perception: JSONL 통합파일 → JSON 개별 파일 분할
    - GNSS: TXT 통합파일 → JSON 개별 파일 분할

    Args:
        input_path: 입력 Raw 데이터셋 경로 (단일 씬 또는 씬들의 부모 폴더)
        output_path: 출력 Source 데이터셋 경로
        max_diff_us: 센서 간 최대 시간 차이 허용치 (마이크로초)
        reference_sensor: matching.csv 기준 센서 (기본값: ref_perception_object)
            - "gnss": GNSS (100Hz)
            - "ref_lidar_*": LiDAR (10Hz)
            - "ref_cam_*": Camera (10Hz)
            - "ref_radar_*_scan": Radar
            - "ref_perception_object": Perception Object (10Hz)

    사용 예시:
        # 단일 씬 변환
        convert_raw_to_source(
            "dataset/raw/20260114_172307",
            "dataset/source/20260114_172307",
            max_diff_us=50_000  # 50ms
        )

        # 다중 씬 배치 변환 (raw 폴더 내 모든 씬)
        convert_raw_to_source(
            "dataset/raw",
            "dataset/source",
            max_diff_us=50_000
        )
    """
    print(f"\n{'='*60}")
    print(f"Raw → Source 변환")
    print(f"{'='*60}")
    print(f"  입력: {input_path}")
    print(f"  출력: {output_path}")
    print(f"  최대 시간 차이: {max_diff_us / 1000}ms")
    print(f"  매칭 기준 센서: {reference_sensor}")

    # 씬 폴더 탐색
    scenes = _find_scene_folders(input_path)

    if not scenes:
        print(f"\n✗ 변환할 씬을 찾을 수 없습니다: {input_path}")
        raise ValueError(f"변환할 씬을 찾을 수 없습니다: {input_path}")

    print(f"\n발견된 씬: {len(scenes)}개")
    for scene in scenes:
        print(f"  - {Path(scene).name}")

    # 출력 디렉토리 생성
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 변환 결과 추적
    success_count = 0
    fail_count = 0
    skip_count = 0
    failed_scenes = []
    skipped_scenes = []

    # 씬별 변환 진행
    input_base = Path(input_path)

    print(f"\n{'='*60}")
    print("변환 시작...")
    print(f"{'='*60}\n")

    for scene_path in tqdm(scenes, desc="씬 변환 진행", unit="씬"):
        scene_name = Path(scene_path).name

        # 입력 경로 자체가 씬인 경우
        if str(input_base) == scene_path:
            dst_scene_path = str(output_dir)
        else:
            dst_scene_path = str(output_dir / scene_name)

        # 이미 변환된 씬인지 확인
        dst_path = Path(dst_scene_path)
        if dst_path.exists() and any((dst_path / indicator).exists() for indicator in ['ref', 'gnss']):
            skip_count += 1
            skipped_scenes.append(scene_name)
            tqdm.write(f"  ⊘ {scene_name} 스킵 (이미 존재)")
            continue

        tqdm.write(f"\n[{success_count + fail_count + 1}/{len(scenes) - skip_count}] {scene_name} 변환 중...")

        if _convert_single_scene(scene_path, dst_scene_path, max_diff_us, reference_sensor):
            success_count += 1
            tqdm.write(f"  ✓ {scene_name} 완료")
        else:
            fail_count += 1
            failed_scenes.append(scene_name)

    # 결과 요약
    print(f"\n{'='*60}")
    print("변환 완료 요약")
    print(f"{'='*60}")
    print(f"  총 씬: {len(scenes)}개")
    print(f"  성공: {success_count}개")
    print(f"  스킵: {skip_count}개 (이미 존재)")
    print(f"  실패: {fail_count}개")

    if failed_scenes:
        print(f"\n  실패한 씬:")
        for scene in failed_scenes:
            print(f"    - {scene}")

    if fail_count > 0:
        raise RuntimeError(f"{fail_count}개 씬 변환 실패")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Raw → Source 변환")
    parser.add_argument("input", help="입력 Raw 데이터셋 경로 (단일 씬 또는 씬들의 부모 폴더)")
    parser.add_argument("output", help="출력 Source 데이터셋 경로")
    parser.add_argument("--max-diff", type=int, default=50000, help="최대 시간 차이 (us)")
    parser.add_argument("--reference-sensor", type=str, default="ref_perception_object",
                        help="매칭 기준 센서 (기본값: ref_perception_object)")

    args = parser.parse_args()

    convert_raw_to_source(args.input, args.output, args.max_diff, args.reference_sensor)
