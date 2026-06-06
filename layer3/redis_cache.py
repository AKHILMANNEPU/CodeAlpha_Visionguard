import json
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Optional Redis cache for real-time state.

    If Redis is not running, this class silently falls back
    to an in-memory dict. The rest of the app never knows.

    Stores:
        live_tracks       → current active track states
        line_counts       → running in/out counts per line
        fps               → current processing FPS
        density_levels    → current zone density levels
        last_alert        → most recent alert message + time

    TTL (time-to-live) on all keys prevents stale data.
    """

    def __init__(self, config: dict):
        cfg  = config.get("redis", {})
        host = cfg.get("host", "localhost")
        port = cfg.get("port", 6379)
        db   = cfg.get("db", 0)
        self.ttl = cfg.get("ttl_seconds", 10)

        self._redis   = None
        self._fallback: Dict[str, Any] = {}    # in-memory fallback

        self._try_connect(host, port, db)

    def _try_connect(self, host: str, port: int, db: int):
        """Try to connect to Redis. Silently fall back if not available."""
        try:
            import redis
            client = redis.Redis(host=host, port=port, db=db,
                                 decode_responses=True,
                                 socket_connect_timeout=2)
            client.ping()
            self._redis = client
            logger.info(f"Redis connected: {host}:{port}")
        except Exception as e:
            logger.warning(f"Redis not available ({e}). Using in-memory fallback.")
            self._redis = None

    @property
    def is_connected(self) -> bool:
        return self._redis is not None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store a value. Serializes dicts/lists to JSON automatically."""
        serialized = json.dumps(value) if not isinstance(value, str) else value
        try:
            if self._redis:
                self._redis.setex(key, ttl or self.ttl, serialized)
            else:
                self._fallback[key] = {"value": serialized, "ts": time.time()}
        except Exception as e:
            logger.debug(f"Cache set error: {e}")
            self._fallback[key] = {"value": serialized, "ts": time.time()}

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value. Auto-deserializes JSON."""
        try:
            if self._redis:
                raw = self._redis.get(key)
            else:
                entry = self._fallback.get(key)
                if entry and (time.time() - entry["ts"]) < self.ttl:
                    raw = entry["value"]
                else:
                    return None

            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        except Exception:
            return None

    def delete(self, key: str):
        try:
            if self._redis:
                self._redis.delete(key)
            else:
                self._fallback.pop(key, None)
        except Exception:
            pass

    def increment(self, key: str, amount: int = 1) -> int:
        """Atomic counter increment — useful for running totals."""
        try:
            if self._redis:
                return self._redis.incrby(key, amount)
            else:
                current = self._fallback.get(key, {"value": "0"})
                new_val = int(current.get("value", 0)) + amount
                self._fallback[key] = {"value": str(new_val), "ts": time.time()}
                return new_val
        except Exception:
            return 0

    # ── Convenience methods for common state ─────────────────────────────

    def update_live_tracks(self, tracks: list):
        """Store current active tracks as lightweight dicts."""
        lightweight = [
            {
                "id"    : t["track_id"],
                "class" : t["class_name"],
                "action": t.get("action", ""),
                "cx"    : t["center"][0],
                "cy"    : t["center"][1],
                "zones" : t.get("zones", [])
            }
            for t in tracks
        ]
        self.set("live_tracks", lightweight, ttl=5)

    def update_fps(self, fps: float):
        self.set("current_fps", round(fps, 1), ttl=5)

    def update_line_counts(self, counts: dict):
        self.set("line_counts", counts, ttl=30)

    def update_density(self, density_levels: dict):
        self.set("density_levels", density_levels, ttl=10)

    def push_alert(self, message: str):
        self.set("last_alert", {"message": message, "ts": time.time()}, ttl=60)

    def get_live_tracks(self) -> list:
        return self.get("live_tracks") or []

    def get_fps(self) -> float:
        return self.get("current_fps") or 0.0

    def get_line_counts(self) -> dict:
        return self.get("line_counts") or {}

    def get_last_alert(self) -> Optional[dict]:
        return self.get("last_alert")
