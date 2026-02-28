import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import shutil

from integrity.hashing import sha256_file
from integrity.audit_logger import log_recovery
from core.carver import FileCarver
from core.entropy import calculate_entropy, sliding_window_entropy
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

    # Create subdirectories for successful and failed files
    successful_dir = output_dir / "successful"
    failed_dir = output_dir / "failed"
    successful_dir.mkdir(exist_ok=True)
    failed_dir.mkdir(exist_ok=True)

    # Compute disk hash
    disk_sha256 = sha256_file(str(image_path))
    if args.verbose:
        print(f"Disk SHA256: {disk_sha256}")

    # Create carver
    carver = FileCarver(str(image_path), str(output_dir), verbose=args.verbose)

    # Carve files
    jpeg_files = carver.carve_jpeg()
    pdf_files = carver.carve_pdf()
    png_files = carver.carve_png()
    video_files = carver.carve_video()
    all_files = jpeg_files + pdf_files + png_files + video_files

    # Process each file: entropy, repair, AI
    for i, file_meta in enumerate(all_files):
        if args.verbose and (i % 10 == 0 or i == len(all_files) - 1):
            print(f"Processing file {i+1}/{len(all_files)}: {file_meta['file_name']}")
        
        file_path = output_dir / file_meta['file_name']
        entropy = calculate_entropy(str(file_path))
        file_meta['entropy'] = entropy
        
        # Optional: Sliding window entropy for research (JPEG only)
        if file_meta['file_type'] == 'jpeg' and file_meta['size'] < 10 * 1024 * 1024:  # <10MB
            try:
                sliding_entropies = sliding_window_entropy(str(file_path))
                file_meta['sliding_window_entropy'] = sliding_entropies
            except:
                file_meta['sliding_window_entropy'] = []
        
        # Initialize confidence from validation (for JPEG)
        base_confidence = file_meta.get('validation', {}).get('confidence', 50)
        
        # Adjust confidence based on entropy (typical JPEG range 7.0-8.0)
        if 7.0 <= entropy <= 8.0:
            base_confidence += 10
        elif entropy < 6.0 or entropy > 9.0:
            base_confidence -= 10
        
        file_meta['confidence'] = max(0, min(100, base_confidence))
        
        if args.verbose:
            print(f"  Entropy: {entropy:.4f}, Confidence: {file_meta['confidence']}")

        # Repair for JPEG - Always attempt repair
        if file_meta['file_type'] == 'jpeg':
            repair_result = repair_jpeg(file_path)
            file_meta.update(repair_result)
            if repair_result['repair_attempted']:
                file_meta['confidence'] -= 30  # Penalty for repair
            if repair_result['decode_success']:
                file_meta['confidence'] += 20
                file_meta['status'] = 'repaired'
            else:
                file_meta['status'] = 'corrupted'
            if args.verbose:
                print(f"  Repair: {repair_result}")
        elif file_meta['file_type'] == 'png':
            # For PNG, just validate
            if file_meta['size'] > 50 * 1024 * 1024:  # 50MB
                file_meta['repair_attempted'] = False
                file_meta['repair_actions'] = ["Skipped validation for large file"]
                file_meta['decode_success'] = False
                file_meta['status'] = 'large_file'
                file_meta['confidence'] -= 20
                if args.verbose:
                    print(f"  Validation: Skipped for large file")
            else:
                try:
                    with Image.open(file_path) as img:
                        img.verify()
                    file_meta['repair_attempted'] = False
                    file_meta['repair_actions'] = []
                    file_meta['decode_success'] = True
                    file_meta['status'] = 'valid'
                    file_meta['confidence'] += 20
                    if args.verbose:
                        print(f"  Validation: Success")
                except Exception:
                    file_meta['repair_attempted'] = False
                    file_meta['repair_actions'] = []
                    file_meta['decode_success'] = False
                    file_meta['status'] = 'corrupted'
                    file_meta['confidence'] -= 30
                    if args.verbose:
                        print(f"  Validation: Failed")
        else:
            file_meta['repair_attempted'] = False
            file_meta['repair_actions'] = []
            file_meta['decode_success'] = True  # Assume PDF and videos are ok
            file_meta['status'] = 'carved'
            # Keep existing confidence for videos
            if args.verbose:
                print(f"  Repair: Skipped for {file_meta['file_type']}")

        # AI analysis
        if args.ai_mode == 'cloud':
            ai_result = call_ai(file_meta)
            file_meta['ai_analysis'] = ai_result
            if args.verbose:
                print(f"  AI Analysis: {ai_result}")
        else:
            file_meta['ai_analysis'] = None

        # Final SHA256
        file_meta['final_sha256'] = sha256_file(str(file_path))
        if args.verbose:
            print(f"  SHA256: {file_meta['final_sha256']}")

        # Move file to appropriate subdirectory based on decode success
        if file_meta.get('decode_success', True):  # Default to True for non-JPEG files
            target_dir = successful_dir
            file_meta['final_location'] = str(successful_dir / file_meta['file_name'])
        else:
            target_dir = failed_dir
            file_meta['final_location'] = str(failed_dir / file_meta['file_name'])

        # Move the file
        shutil.move(str(file_path), str(target_dir / file_meta['file_name']))
        if args.verbose:
            print(f"  Moved to: {target_dir / file_meta['file_name']}")

    end_time = datetime.now().isoformat()

    # Log JSON
    log_recovery(args.case_id, disk_sha256, all_files, output_dir, start_time, end_time)

    # Generate PDF
    generate_pdf_report(args.case_id, disk_sha256, all_files, output_dir)

    # Print summary
    successful_count = len(list(successful_dir.glob("*")))
    failed_count = len(list(failed_dir.glob("*")))

    print(f"Case ID: {args.case_id}")
    print(f"Total files recovered: {len(all_files)}")
    print(f"Successfully decoded: {successful_count} files")
    print(f"Failed to decode: {failed_count} files")
    print(f"Output directory: {output_dir}")
    print(f"  Successful files: {successful_dir}")
    print(f"  Failed files: {failed_dir}")

if __name__ == "__main__":
    main()
