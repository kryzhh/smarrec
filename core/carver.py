from pathlib import Path
from typing import List, Dict, Any
import os

JPEG_SOI = b'\xFF\xD8\xFF'  # Start of Image with APP0 marker
JPEG_EOI = b'\xFF\xD9'  # End of Image
PDF_START = b'%PDF'
PDF_END = b'%%EOF'
MP4_START = b'ftyp'  # MP4 ftyp box
AVI_START = b'RIFF'  # AVI RIFF header
PNG_START = b'\x89PNG\r\n\x1a\n'  # PNG signature
PNG_END = b'IEND'  # PNG IEND chunk (plus 4 bytes CRC, but approximate)

# Known MP4 brands
MP4_BRANDS = [b'isom', b'mp41', b'mp42', b'avc1', b'dash', b'qt  ']

CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks
OVERLAP = 1024 * 1024  # 1MB overlap
WRITE_CHUNK_SIZE = 1 * 1024 * 1024  # 1MB write chunks
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB max file size


class FileCarver:
    def __init__(self, image_path: str, output_dir: str, verbose: bool = False):
        self.image_path = Path(image_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
    def _validate_mp4_structure(self, start_pos: int) -> bool:
        """
        Validate MP4 structure by parsing first few boxes.
        Returns True if structure looks valid.
        """
        try:
            with open(self.image_path, "rb") as f:
                f.seek(start_pos)
                # Read ftyp box
                ftyp_size = int.from_bytes(f.read(4), byteorder='big')
                if ftyp_size < 8 or ftyp_size > 1024:
                    return False
                f.seek(start_pos + ftyp_size)
                
                # Try to read next box
                box_size = int.from_bytes(f.read(4), byteorder='big')
                if box_size < 8 or box_size > MAX_FILE_SIZE:
                    return False
                box_type = f.read(4)
                # Check if known box types
                known_boxes = [b'moov', b'mdat', b'free', b'skip', b'meta']
                if box_type not in known_boxes:
                    return False
                return True
        except:
            return False

    def _validate_jpeg_structure(self, data: bytes) -> dict:
        """
        Fast Object Validation for JPEG structure.
        Returns dict with validation results and confidence score.
        """
        if len(data) < 4:
            return {"valid": False, "confidence": 0, "issues": ["too_small"]}

        confidence = 0
        issues = []

        # Check SOI
        if not data.startswith(b'\xFF\xD8'):
            return {"valid": False, "confidence": 0, "issues": ["no_soi"]}

        confidence += 20

        # Check EOI
        if not data.endswith(b'\xFF\xD9'):
            issues.append("no_eoi")
            confidence -= 30
        else:
            confidence += 20

        # Parse markers
        pos = 2  # After SOI
        has_sos = False
        has_eoi = False

        while pos < len(data) - 1:
            if data[pos] != 0xFF:
                issues.append("invalid_marker")
                break

            marker = data[pos + 1]
            pos += 2

            if marker == 0xD8:  # SOI - should only appear at start
                if pos != 4:
                    issues.append("multiple_soi")
                    confidence -= 20
            elif marker == 0xD9:  # EOI
                has_eoi = True
                if pos < len(data):
                    issues.append("data_after_eoi")
                    confidence -= 20
                break
            elif marker == 0xDA:  # SOS
                has_sos = True
                confidence += 15
                # SOS is followed by scan data until next marker
                # For simplicity, assume valid if we reach here
            elif marker >= 0xC0 and marker <= 0xCF:  # SOF markers
                confidence += 10
            elif marker == 0xC4:  # DHT
                confidence += 5
            elif marker == 0xCC:  # DAC
                confidence += 5
            elif marker >= 0xE0 and marker <= 0xEF:  # APP markers
                confidence += 5
            elif marker == 0xFE:  # COM
                confidence += 5
            elif marker == 0xDD:  # DRI
                confidence += 5
            elif marker == 0xDB:  # DQT
                confidence += 5

            # Skip segment data
            if marker not in [0xD8, 0xD9, 0x00]:  # Not SOI, EOI, or stuffing
                if pos + 2 > len(data):
                    issues.append("truncated_segment")
                    confidence -= 30
                    break
                length = int.from_bytes(data[pos:pos+2], 'big')
                pos += length

        if not has_sos:
            issues.append("no_sos")
            confidence -= 20

        if not has_eoi:
            issues.append("no_eoi")
            confidence -= 30

        # Trailing data check
        eoi_pos = data.rfind(b'\xFF\xD9')
        if eoi_pos != -1 and eoi_pos + 2 < len(data):
            issues.append("trailing_bytes")
            confidence -= 20

        valid = len(issues) == 0 and confidence >= 30
        confidence = max(0, min(100, confidence))

        return {
            "valid": valid,
            "confidence": confidence,
            "issues": issues,
            "trailing_bytes_detected": "trailing_bytes" in issues
        }

    def carve_jpeg(self) -> List[Dict[str, Any]]:
        recovered_files = []
        file_size = os.path.getsize(self.image_path)
        recovered_count = 0

        with open(self.image_path, "rb") as f:
            pos = 0
            while pos < file_size:
                chunk_start = pos
                f.seek(pos)
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Find SOI in this chunk
                chunk_pos = 0
                while True:
                    soi_rel = chunk.find(JPEG_SOI, chunk_pos)
                    if soi_rel == -1:
                        break

                    soi_abs = chunk_start + soi_rel

                    # From SOI, read forward to find EOI
                    f.seek(soi_abs)
                    data = f.read(CHUNK_SIZE * 4)  # Read up to 256MB forward
                    eoi_rel = data.find(JPEG_EOI)
                    if eoi_rel == -1:
                        # EOI not found, skip this SOI
                        chunk_pos = soi_rel + 1
                        continue

                    eoi_abs = soi_abs + eoi_rel + 2  # Include EOI

                    # Extract candidate data
                    f.seek(soi_abs)
                    jpeg_data = f.read(eoi_abs - soi_abs)
                    size = len(jpeg_data)

                    if size < 2048:  # Minimum size threshold
                        chunk_pos = soi_rel + 1
                        continue

                    # Fast Object Validation
                    validation = self._validate_jpeg_structure(jpeg_data)

                    if size >= 2048:  # Ignore < 2KB
                        output_file = self.output_dir / f"recovered_{recovered_count}.jpg"
                        with open(output_file, "wb") as out:
                            out.write(jpeg_data)

                        metadata = {
                            "file_name": output_file.name,
                            "file_type": "jpeg",
                            "offset_start": soi_abs,
                            "offset_end": eoi_abs - 1,
                            "size": size,
                            "validation": validation,
                            "status": "valid" if validation["valid"] else "invalid_structure"
                        }
                        recovered_files.append(metadata)
                        if self.verbose:
                            print(f"Carved JPEG: {output_file.name}, size: {size} bytes, confidence: {validation['confidence']}")
                        recovered_count += 1

                    chunk_pos = soi_rel + 1

                pos += CHUNK_SIZE - OVERLAP
                if pos < 0:
                    pos = 0

        return recovered_files

    def carve_pdf(self) -> List[Dict[str, Any]]:
        recovered_files = []
        file_size = os.path.getsize(self.image_path)
        recovered_count = 0

        with open(self.image_path, "rb") as f:
            pos = 0
            while pos < file_size:
                chunk_start = pos
                f.seek(pos)
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Find PDF_START in this chunk
                chunk_pos = 0
                while True:
                    pdf_rel = chunk.find(PDF_START, chunk_pos)
                    if pdf_rel == -1:
                        break

                    pdf_abs = chunk_start + pdf_rel

                    # From PDF_START, read forward to find PDF_END
                    f.seek(pdf_abs)
                    data = f.read(CHUNK_SIZE * 4)  # Read up to 256MB forward
                    eof_rel = data.find(PDF_END)
                    if eof_rel == -1:
                        # EOF not found, skip this PDF
                        chunk_pos = pdf_rel + 1
                        continue

                    eof_abs = pdf_abs + eof_rel + len(PDF_END)

                    # Extract the data
                    f.seek(pdf_abs)
                    pdf_data = f.read(eof_abs - pdf_abs)
                    size = len(pdf_data)

                    if size >= 2048:  # Ignore < 2KB
                        output_file = self.output_dir / f"recovered_{recovered_count}.pdf"
                        with open(output_file, "wb") as out:
                            out.write(pdf_data)

                        metadata = {
                            "file_name": output_file.name,
                            "file_type": "pdf",
                            "offset_start": pdf_abs,
                            "offset_end": eof_abs - 1,
                            "size": size
                        }
                        recovered_files.append(metadata)
                        if self.verbose:
                            print(f"Carved PDF: {output_file.name}, size: {size} bytes")
                        recovered_count += 1

                    chunk_pos = pdf_rel + 1

                pos += CHUNK_SIZE - OVERLAP
                if pos < 0:
                    pos = 0

        return recovered_files

    def carve_png(self) -> List[Dict[str, Any]]:
        recovered_files = []
        file_size = os.path.getsize(self.image_path)
        recovered_count = 0

        with open(self.image_path, "rb") as f:
            pos = 0
            while pos < file_size:
                chunk_start = pos
                f.seek(pos)
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Find PNG_START in this chunk
                chunk_pos = 0
                while True:
                    png_rel = chunk.find(PNG_START, chunk_pos)
                    if png_rel == -1:
                        break

                    png_abs = chunk_start + png_rel

                    # From PNG_START, read forward to find PNG_END
                    f.seek(png_abs)
                    data = f.read(CHUNK_SIZE * 4)  # Read up to 256MB forward
                    iend_rel = data.find(PNG_END)
                    if iend_rel == -1:
                        # IEND not found, skip this PNG
                        chunk_pos = png_rel + 1
                        continue

                    iend_abs = png_abs + iend_rel + len(PNG_END) + 4  # Include IEND + CRC

                    # Extract the data
                    f.seek(png_abs)
                    png_data = f.read(iend_abs - png_abs)
                    size = len(png_data)

                    if size >= 2048:  # Ignore < 2KB
                        output_file = self.output_dir / f"recovered_{recovered_count}.png"
                        with open(output_file, "wb") as out:
                            out.write(png_data)

                        metadata = {
                            "file_name": output_file.name,
                            "file_type": "png",
                            "offset_start": png_abs,
                            "offset_end": iend_abs - 1,
                            "size": size
                        }
                        recovered_files.append(metadata)
                        if self.verbose:
                            print(f"Carved PNG: {output_file.name}, size: {size} bytes")
                        recovered_count += 1

                    chunk_pos = png_rel + 1

                pos += CHUNK_SIZE - OVERLAP
                if pos < 0:
                    pos = 0

        return recovered_files

    def carve_video(self) -> List[Dict[str, Any]]:
        recovered_files = []
        file_size = os.path.getsize(self.image_path)
        recovered_count = 0

        # First, find all MP4 ftyp positions
        ftyp_positions = []
        with open(self.image_path, "rb") as f:
            pos = 0
            while pos < file_size:
                f.seek(pos)
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_pos = 0
                while True:
                    rel = chunk.find(MP4_START, chunk_pos)
                    if rel == -1:
                        break
                    abs_pos = pos + rel
                    ftyp_positions.append(abs_pos)
                    chunk_pos = rel + 1
                pos += CHUNK_SIZE - OVERLAP

        # Sort and unique
        ftyp_positions = sorted(set(ftyp_positions))

        # Carve MP4/MOV
        for i, start_pos in enumerate(ftyp_positions):
            end_pos = ftyp_positions[i + 1] if i + 1 < len(ftyp_positions) else file_size

            size = end_pos - start_pos
            if size < 2048 or size > MAX_FILE_SIZE:
                continue

            # Determine type and validate brand
            if start_pos + 8 < file_size:
                with open(self.image_path, "rb") as f:
                    f.seek(start_pos + 4)
                    brand = f.read(4)
                if brand not in MP4_BRANDS:
                    continue
                file_type = 'mov' if brand == b'qt  ' else 'mp4'
            else:
                continue

            # Validate structure
            if not self._validate_mp4_structure(start_pos):
                continue

            output_file = self.output_dir / f"recovered_{recovered_count}.{file_type}"
            with open(output_file, "wb") as out:
                with open(self.image_path, "rb") as f:
                    f.seek(start_pos)
                    remaining = size
                    while remaining > 0:
                        chunk = f.read(min(WRITE_CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        out.write(chunk)
                        remaining -= len(chunk)

            metadata = {
                "file_name": output_file.name,
                "file_type": file_type,
                "offset_start": start_pos,
                "offset_end": end_pos - 1,
                "size": size
            }
            recovered_files.append(metadata)
            if self.verbose:
                print(f"Carved {file_type.upper()}: {output_file.name}, size: {size} bytes")
            recovered_count += 1

        # AVI carving
        avi_count = recovered_count
        with open(self.image_path, "rb") as f:
            pos = 0
            while pos < file_size:
                f.seek(pos)
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_pos = 0
                while True:
                    rel = chunk.find(AVI_START, chunk_pos)
                    if rel == -1:
                        break
                    abs_pos = pos + rel
                    # Check if AVI
                    if abs_pos + 12 < file_size:
                        f.seek(abs_pos + 8)
                        avi_check = f.read(4)
                        if avi_check == b'AVI ':
                            f.seek(abs_pos + 4)
                            riff_size = int.from_bytes(f.read(4), byteorder='little')
                            if riff_size > MAX_FILE_SIZE:
                                riff_size = MAX_FILE_SIZE
                            end_pos = abs_pos + 8 + riff_size
                            if end_pos > file_size:
                                end_pos = file_size

                            size = end_pos - abs_pos
                            if size >= 2048:
                                output_file = self.output_dir / f"recovered_{avi_count}.avi"
                                with open(output_file, "wb") as out:
                                    f.seek(abs_pos)
                                    remaining = size
                                    while remaining > 0:
                                        chunk = f.read(min(WRITE_CHUNK_SIZE, remaining))
                                        if not chunk:
                                            break
                                        out.write(chunk)
                                        remaining -= len(chunk)

                                metadata = {
                                    "file_name": output_file.name,
                                    "file_type": "avi",
                                    "offset_start": abs_pos,
                                    "offset_end": end_pos - 1,
                                    "size": size
                                }
                                recovered_files.append(metadata)
                                if self.verbose:
                                    print(f"Carved AVI: {output_file.name}, size: {size} bytes")
                                avi_count += 1

                    chunk_pos = rel + 1
                pos += CHUNK_SIZE - OVERLAP

        return recovered_files
