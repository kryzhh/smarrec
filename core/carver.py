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

CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks
OVERLAP = 1024 * 1024  # 1MB overlap


class FileCarver:
    def __init__(self, image_path: str, output_dir: str):
        self.image_path = Path(image_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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

                    # Extract the data
                    f.seek(soi_abs)
                    jpeg_data = f.read(eoi_abs - soi_abs)
                    size = len(jpeg_data)

                    if size >= 2048:  # Ignore < 2KB
                        output_file = self.output_dir / f"recovered_{recovered_count}.jpg"
                        with open(output_file, "wb") as out:
                            out.write(jpeg_data)

                        metadata = {
                            "file_name": output_file.name,
                            "file_type": "jpeg",
                            "offset_start": soi_abs,
                            "offset_end": eoi_abs - 1,
                            "size": size
                        }
                        recovered_files.append(metadata)
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

            with open(self.image_path, "rb") as f:
                f.seek(start_pos)
                video_data = f.read(end_pos - start_pos)
                size = len(video_data)

                if size < 2048:
                    continue

                # Determine type
                if start_pos + 8 < file_size:
                    f.seek(start_pos + 4)
                    brand = f.read(4)
                    file_type = 'mov' if brand == b'qt  ' else 'mp4'
                else:
                    file_type = 'mp4'

                output_file = self.output_dir / f"recovered_{recovered_count}.{file_type}"
                with open(output_file, "wb") as out:
                    out.write(video_data)

                metadata = {
                    "file_name": output_file.name,
                    "file_type": file_type,
                    "offset_start": start_pos,
                    "offset_end": end_pos - 1,
                    "size": size
                }
                recovered_files.append(metadata)
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
                            end_pos = abs_pos + 8 + riff_size
                            if end_pos > file_size:
                                end_pos = file_size

                            f.seek(abs_pos)
                            avi_data = f.read(end_pos - abs_pos)
                            size = len(avi_data)

                            if size >= 2048:
                                output_file = self.output_dir / f"recovered_{avi_count}.avi"
                                with open(output_file, "wb") as out:
                                    out.write(avi_data)

                                metadata = {
                                    "file_name": output_file.name,
                                    "file_type": "avi",
                                    "offset_start": abs_pos,
                                    "offset_end": end_pos - 1,
                                    "size": size
                                }
                                recovered_files.append(metadata)
                                avi_count += 1

                    chunk_pos = rel + 1
                pos += CHUNK_SIZE - OVERLAP

        return recovered_files
