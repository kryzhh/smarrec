from pathlib import Path
from PIL import Image

def repair_jpeg(path: Path) -> dict:
    """
    Attempt to repair a JPEG file by appending EOI if missing and validate it.
    Now more aggressive - attempts repair even if structurally valid but PIL fails.

    Args:
        path: Path to the JPEG file.

    Returns:
        A dictionary with repair status and validation result.
    """
    repair_attempted = False
    repair_actions = []
    decode_success = False

    # First attempt: Try to decode with PIL
    try:
        with Image.open(path) as img:
            img.verify()  # Verify the image
        decode_success = True
        return {
            "repair_attempted": repair_attempted,
            "repair_actions": repair_actions,
            "decode_success": decode_success
        }
    except Exception as e:
        # PIL failed - attempt repairs
        pass

    # Read the file data
    with open(path, 'rb') as f:
        data = f.read()

    # Repair attempt 1: Check for missing EOI
    if not data.endswith(b'\xFF\xD9'):
        # Append EOI
        with open(path, 'ab') as f:
            f.write(b'\xFF\xD9')
        repair_attempted = True
        repair_actions.append("Appended EOI marker")

        # Test if this fixed it
        try:
            with Image.open(path) as img:
                img.verify()
            decode_success = True
            return {
                "repair_attempted": repair_attempted,
                "repair_actions": repair_actions,
                "decode_success": decode_success
            }
        except Exception as e2:
            # EOI append didn't work, revert
            with open(path, 'rb+') as f:
                f.seek(0, 2)  # Seek to end
                f.truncate(len(data))  # Remove the EOI we added
            repair_actions.append("EOI append failed, reverted")

    # Repair attempt 2: Check for truncated segments
    # Look for incomplete segment lengths
    pos = 2  # After SOI
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        pos += 2

        if marker in [0xD8, 0xD9]:  # SOI or EOI
            continue
        elif marker == 0x00:  # Stuffing byte
            continue
        else:
            # Regular segment
            if pos + 2 > len(data):
                # Truncated length field - try padding
                padding_needed = (pos + 2) - len(data)
                if padding_needed > 0 and padding_needed <= 4:
                    with open(path, 'ab') as f:
                        f.write(b'\x00' * padding_needed)
                    repair_attempted = True
                    repair_actions.append(f"Padded truncated segment ({padding_needed} bytes)")

                    try:
                        with Image.open(path) as img:
                            img.verify()
                        decode_success = True
                        return {
                            "repair_attempted": repair_attempted,
                            "repair_actions": repair_actions,
                            "decode_success": decode_success
                        }
                    except Exception:
                        # Padding didn't work, revert
                        with open(path, 'rb+') as f:
                            f.seek(0, 2)
                            f.truncate(len(data))
                        repair_actions.append("Padding failed, reverted")
                break

            length = int.from_bytes(data[pos:pos+2], 'big')
            pos += length

    # Repair attempt 3: Try removing trailing garbage after EOI
    eoi_pos = data.rfind(b'\xFF\xD9')
    if eoi_pos != -1 and eoi_pos + 2 < len(data):
        # Truncate after EOI
        with open(path, 'rb+') as f:
            f.seek(0, 2)
            f.truncate(eoi_pos + 2)
        repair_attempted = True
        repair_actions.append(f"Truncated trailing data after EOI ({len(data) - (eoi_pos + 2)} bytes removed)")

        try:
            with Image.open(path) as img:
                img.verify()
            decode_success = True
            return {
                "repair_attempted": repair_attempted,
                "repair_actions": repair_actions,
                "decode_success": decode_success
            }
        except Exception:
            # Truncation didn't work, revert
            with open(path, 'wb') as f:
                f.write(data)
            repair_actions.append("Truncation failed, reverted")

    # Final attempt: Force decode even if verification fails
    try:
        with Image.open(path) as img:
            # Try to load the image data without verification
            img.load()
        decode_success = True
        repair_actions.append("Force decoded without verification")
        repair_attempted = True
    except Exception:
        decode_success = False

    return {
        "repair_attempted": repair_attempted,
        "repair_actions": repair_actions,
        "decode_success": decode_success
    }