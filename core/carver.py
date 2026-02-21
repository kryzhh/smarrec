from pathlib import Path

JPEG_SOI = b'\xFF\xD8'  # Start of Image
JPEG_EOI = b'\xFF\xD9'  # End of Image


class FileCarver:
    def __init__(self, image_path, output_dir):
        self.image_path = Path(image_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def carve_jpeg(self):
        recovered_count = 0

        with open(self.image_path, "rb") as f:
            data = f.read()

        start = 0

        while True:
            soi_index = data.find(JPEG_SOI, start)
            if soi_index == -1:
                break

            eoi_index = data.find(JPEG_EOI, soi_index)

            if eoi_index == -1:
                break  # truncated case handled later

            eoi_index += 2  # include EOI marker

            jpeg_data = data[soi_index:eoi_index]

            output_file = self.output_dir / f"recovered_{recovered_count}.jpg"
            with open(output_file, "wb") as out:
                out.write(jpeg_data)

            recovered_count += 1
            start = eoi_index

        return recovered_count
