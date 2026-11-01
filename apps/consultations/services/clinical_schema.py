from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings


def input_schema():
    path = Path(os.getenv("CLINICAL_FIELDS_PATH", "configs/clinical_fields.json"))
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    return json.loads(path.read_text(encoding="utf-8"))
