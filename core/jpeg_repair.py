from pathlib import Path
from PIL import Image

def repair_jpeg(path: Path) -> dict:
    """
    Attempt to repair a JPEG file by appending EOI if missing and validate it.

    Args:
        path: Path to the JPEG file.

    Returns:
        A dictionary with repair status and validation result.
    """
    repair_attempted = False
    repair_actions = []
    decode_success = False

    try:
        # Try to open the image to check if it's valid
        with Image.open(path) as img:
            img.verify()  # Verify the image
        decode_success = True
    except Exception as e:
        # If it fails, check if EOI is missing
        with open(path, 'rb') as f:
            data = f.read()

        if not data.endswith(b'\xFF\xD9'):
            # Append EOI
            with open(path, 'ab') as f:
                f.write(b'\xFF\xD9')
            repair_attempted = True
            repair_actions.append("Appended EOI marker")

            # Try to verify again
            try:
                with Image.open(path) as img:
                    img.verify()
                decode_success = True
            except Exception as e2:
                decode_success = False
        else:
            decode_success = False

    return {
        "repair_attempted": repair_attempted,
        "repair_actions": repair_actions,
        "decode_success": decode_success
    }