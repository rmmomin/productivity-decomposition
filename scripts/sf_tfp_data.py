from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SF_TFP_URL = "https://www.frbsf.org/wp-content/uploads/quarterly_tfp.xlsx"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_WORKBOOK_PATH = REPO_ROOT / "data" / "quarterly_tfp.xlsx"


def resolve_path(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    return path


def download_latest_workbook(destination: Path, url: str = SF_TFP_URL, timeout: int = 60) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "prod-decomp/1.0"},
    )
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f"{destination.stem}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            shutil.copyfileobj(response, tmp_file)
    tmp_path.replace(destination)
    return destination


def prepare_workbook(input_path: Path, refresh_data: bool, url: str = SF_TFP_URL) -> Path:
    resolved = resolve_path(input_path)
    if refresh_data or not resolved.exists():
        try:
            return download_latest_workbook(resolved, url=url)
        except (urllib.error.URLError, TimeoutError) as exc:
            if resolved.exists():
                print(
                    f"Warning: could not refresh workbook from {url}; using cached file at {resolved}.",
                    file=sys.stderr,
                )
                print(f"Refresh error: {exc}", file=sys.stderr)
                return resolved
            raise
    return resolved
