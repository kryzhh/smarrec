import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

def log_recovery(case_id: str, disk_sha256: str, files_recovered: List[Dict[str, Any]], output_dir: Path, start_time: str, end_time: str):
    """
    Log the recovery data to a JSON file.

    Args:
        case_id: The case identifier.
        disk_sha256: SHA256 hash of the disk image.
        files_recovered: List of dictionaries with file recovery metadata.
        output_dir: The output directory to save the log.
        start_time: Start time of the process.
        end_time: End time of the process.
    """
    log_data = {
        "case_id": case_id,
        "disk_sha256": disk_sha256,
        "start_time": start_time,
        "files_recovered": files_recovered,
        "total_files": len(files_recovered),
        "end_time": end_time
    }

    log_path = output_dir / "recovery_log.json"
    with open(log_path, 'w') as f:
        json.dump(log_data, f, indent=4)