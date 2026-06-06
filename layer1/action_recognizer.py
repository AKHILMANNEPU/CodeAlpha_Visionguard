import numpy as np
from collections import defaultdict, deque
import time

class ActionRecognizer:
    """
    Recognizes actions from track position history using math.
    Zero additional models — uses existing ByteTrack data only.
    """

    def __init__(self, config: dict):
        cfg = config.get("action", {})

        self.walk_speed_min    = cfg.get("walk_speed_min", 5)
        self.run_speed_min     = cfg.get("run_speed_min", 12)
        self.loiter_seconds    = cfg.get("loiter_seconds", 15)
        self.loiter_radius     = cfg.get("loiter_radius", 60)
        self.fall_drop_ratio   = cfg.get("fall_drop_ratio", 0.4)
        self.history_len       = cfg.get("history_len", 30)

        self._positions  = defaultdict(lambda: deque(maxlen=self.history_len))
        self._bboxes     = defaultdict(lambda: deque(maxlen=self.history_len))
        self._timestamps = defaultdict(lambda: deque(maxlen=self.history_len))
        self._actions    = {}

    def update(self, tracks: list, pose_data: dict = None) -> list:
        now = time.time()

        for track in tracks:
            tid  = track["track_id"]
            bbox = track["bbox"]
            cx, cy = track["center"]

            self._positions[tid].append((cx, cy))
            self._bboxes[tid].append(bbox)
            self._timestamps[tid].append(now)

            action = self._classify(tid, now, pose_data)
            track["action"] = action
            self._actions[tid] = action

        active_ids = {t["track_id"] for t in tracks}
        for tid in list(self._positions.keys()):
            if tid not in active_ids:
                del self._positions[tid]
                del self._bboxes[tid]
                del self._timestamps[tid]
                self._actions.pop(tid, None)

        return tracks

    def _classify(self, tid: int, now: float, pose_data: dict = None) -> str:
        positions = self._positions[tid]
        bboxes    = self._bboxes[tid]

        if len(positions) < 2:
            return "Initializing"

        # Speed calculation
        recent = list(positions)[-10:]
        if len(recent) >= 2:
            distances = [
                np.hypot(recent[i][0] - recent[i-1][0],
                         recent[i][1] - recent[i-1][1])
                for i in range(1, len(recent))
            ]
            avg_speed = np.mean(distances)
        else:
            avg_speed = 0

        # Fall detection
        if len(bboxes) >= 5:
            recent_bboxes = list(bboxes)[-5:]
            first_bbox = recent_bboxes[0]
            last_bbox  = recent_bboxes[-1]

            first_h = first_bbox[3] - first_bbox[1]
            last_h  = last_bbox[3]  - last_bbox[1]
            first_w = first_bbox[2] - first_bbox[0]
            last_w  = last_bbox[2]  - last_bbox[0]

            if first_h > 0 and last_h > 0:
                height_ratio = last_h / first_h
                width_ratio  = last_w / max(first_w, 1)
                if height_ratio < (1 - self.fall_drop_ratio) and width_ratio > 1.2:
                    return "⚠ Falling"

        # Loitering detection
        timestamps = list(self._timestamps[tid])
        if len(positions) >= 10 and len(timestamps) >= 2:
            all_pos   = list(positions)
            center_x  = np.mean([p[0] for p in all_pos])
            center_y  = np.mean([p[1] for p in all_pos])
            max_dist  = max(
                np.hypot(p[0] - center_x, p[1] - center_y)
                for p in all_pos
            )
            time_span = timestamps[-1] - timestamps[0]

            if max_dist < self.loiter_radius and time_span > self.loiter_seconds:
                return "⚠ Loitering"

        # Speed-based classification
        if avg_speed >= self.run_speed_min:
            return "Running"
        elif avg_speed >= self.walk_speed_min:
            return "Walking"
        else:
            # 3D Skeletal Classification (Sitting vs Standing)
            if pose_data and len(bboxes) > 0:
                last_bbox = bboxes[-1]
                
                # Find matching skeleton via IoU
                best_pose = None
                best_iou = 0
                for i, p_data in pose_data.items():
                    iou = self._calculate_iou(last_bbox, p_data["bbox"])
                    if iou > 0.4 and iou > best_iou:
                        best_iou = iou
                        best_pose = p_data
                        
                if best_pose:
                    kps = best_pose["keypoints"]
                    l_hip, r_hip = kps[11], kps[12]
                    l_knee, r_knee = kps[13], kps[14]
                    
                    # If knees and hips are visible
                    if (l_hip[2] > 0.4 and l_knee[2] > 0.4) or (r_hip[2] > 0.4 and r_knee[2] > 0.4):
                        hip_y = (l_hip[1] + r_hip[1]) / 2 if l_hip[2] > 0.4 and r_hip[2] > 0.4 else (l_hip[1] if l_hip[2] > 0.4 else r_hip[1])
                        knee_y = (l_knee[1] + r_knee[1]) / 2 if l_knee[2] > 0.4 and r_knee[2] > 0.4 else (l_knee[1] if l_knee[2] > 0.4 else r_knee[1])
                        
                        box_h = last_bbox[3] - last_bbox[1]
                        y_dist = knee_y - hip_y
                        
                        # If the vertical distance between knee and hip is tiny, legs are bent (sitting)
                        if y_dist < 0.18 * box_h:
                            return "Sitting"
                        return "Standing"

            # Fallback to crude 2D bounding box logic if skeleton not found or knees hidden
            if len(bboxes) > 0:
                last_bbox = bboxes[-1]
                w = last_bbox[2] - last_bbox[0]
                h = max(last_bbox[3] - last_bbox[1], 1)
                if (w / h) > 0.85: # Increased threshold to reduce false positives for sitting
                    return "Sitting"
            return "Standing"

    def _calculate_iou(self, boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        if float(boxAArea + boxBArea - interArea) == 0:
            return 0.0
        return interArea / float(boxAArea + boxBArea - interArea)

    def get_action(self, track_id: int) -> str:
        return self._actions.get(track_id, "Unknown")
