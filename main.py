import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from integrity.hashing import sha256_file
from integrity.audit_logger import log_recovery
from core.carver import FileCarver
from core.entropy import shannon_entropy
from core.jpeg_repair import repair_jpeg
from ai_engine.client import call_ai
from report.generator import generate_pdf_report

def main():
    parser = argparse.ArgumentParser(description="SmartRec - AI-assisted digital forensic recovery CLI")
    parser.add_argument('--image', required=True, help='Path to the disk image (.img / .dd)')
    parser.add_argument('--output', required=True, help='Output directory for recovered files')
    parser.add_argument('--ai-mode', choices=['cloud', 'none'], default='none', help='Enable AI analysis mode')
    parser.add_argument('--case-id', default='default_case', help='Case identifier')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')

    args = parser.parse_args()

    start_time = datetime.now().isoformat()

    image_path = Path(args.image)
    output_dir = Path(args.output) / args.case_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compute disk hash
    disk_sha256 = sha256_file(str(image_path))
    if args.verbose:
        print(f"Disk SHA256: {disk_sha256}")

    # Create carver
    carver = FileCarver(str(image_path), str(output_dir))

    # Carve files
    jpeg_files = carver.carve_jpeg()
    pdf_files = carver.carve_pdf()
    png_files = carver.carve_png()
    video_files = carver.carve_video()
    all_files = jpeg_files + pdf_files + png_files + video_files

    # Process each file: entropy, repair, AI
    for file_meta in all_files:
        file_path = output_dir / file_meta['file_name']
        with open(file_path, 'rb') as f:
            data = f.read()
        entropy = shannon_entropy(data)
        file_meta['entropy'] = entropy

        # Repair for JPEG
        if file_meta['file_type'] == 'jpeg':
            repair_result = repair_jpeg(file_path)
            file_meta.update(repair_result)
        elif file_meta['file_type'] == 'png':
            # For PNG, just validate
            try:
                with Image.open(file_path) as img:
                    img.verify()
                file_meta['repair_attempted'] = False
                file_meta['repair_actions'] = []
                file_meta['decode_success'] = True
            except Exception:
                file_meta['repair_attempted'] = False
                file_meta['repair_actions'] = []
                file_meta['decode_success'] = False
        else:
            file_meta['repair_attempted'] = False
            file_meta['repair_actions'] = []
            file_meta['decode_success'] = True  # Assume PDF and videos are ok

        # AI analysis
        if args.ai_mode == 'cloud':
            ai_result = call_ai(file_meta)
            file_meta['ai_analysis'] = ai_result
        else:
            file_meta['ai_analysis'] = None

        # Final SHA256
        file_meta['final_sha256'] = sha256_file(str(file_path))

    end_time = datetime.now().isoformat()

    # Log JSON
    log_recovery(args.case_id, disk_sha256, all_files, output_dir, start_time, end_time)

    # Generate PDF
    generate_pdf_report(args.case_id, disk_sha256, all_files, output_dir)

    # Print summary
    print(f"Case ID: {args.case_id}")
    print(f"Total files recovered: {len(all_files)}")
    print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    main()
