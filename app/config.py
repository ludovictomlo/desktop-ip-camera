"""
Configuration manager.

Loads / saves settings from a JSON file and provides defaults.
"""

import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "camera": {
        "ip": "192.168.1.100",
        "username": "admin",
        "password": "",
        "rtsp_port": 554,
        "stream_path": "/stream1",
    },
    "recording": {
        "output_folder": "recordings",
        "max_storage_mb": 5000,
        "segment_duration_seconds": 60,
        "pre_record_seconds": 5,
        "post_record_seconds": 10,
        "video_format": "mp4",
        "fps": 15,
    },
    "detection": {
        "enabled": True,
        "sensitivity": 25,
        "min_area": 500,
        "cooldown_seconds": 3,
        "zones": [],
    },
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


def load_config(path: str = CONFIG_PATH) -> dict:
    """Load config from JSON file, falling back to defaults."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                user_config = json.load(f)
            # Merge user config into defaults
            _deep_merge(config, user_config)
            logger.info("Configuration loaded from %s", path)
        except Exception as e:
            logger.error("Failed to load config from %s: %s", path, e)
    else:
        logger.info("No config file found, using defaults")
        save_config(config, path)

    return config


def save_config(config: dict, path: str = CONFIG_PATH):
    """Save config to JSON file."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(config, f, indent=4)
        logger.info("Configuration saved to %s", path)
    except Exception as e:
        logger.error("Failed to save config: %s", e)


def _deep_merge(base: dict, override: dict):
    """Recursively merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
