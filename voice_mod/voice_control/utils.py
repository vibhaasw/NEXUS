from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def compact_json(data: Any) -> str:
    if is_dataclass(data):
        data = asdict(data)
    return json.dumps(data, ensure_ascii=True, sort_keys=True)
