import math
from collections import Counter
from typing import List

def shannon_entropy(data: bytes) -> float:
    """
    Calculate the Shannon entropy of the given data.

    Args:
        data: The bytes data to calculate entropy for.

    Returns:
        The Shannon entropy as a float.
    """
    if not data:
        return 0.0

    counter = Counter(data)
    length = len(data)
    entropy = 0.0

    for count in counter.values():
        probability = count / length
        entropy -= probability * math.log2(probability)

    return entropy

def calculate_entropy(file_path: str, chunk_size: int = 8192) -> float:
    """
    Calculate the Shannon entropy of a file by reading it in chunks.

    Args:
        file_path: Path to the file.
        chunk_size: Size of chunks to read.

    Returns:
        The Shannon entropy as a float.
    """
    counter = Counter()
    total_length = 0

    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            counter.update(chunk)
            total_length += len(chunk)

    if total_length == 0:
        return 0.0

    entropy = 0.0
    for count in counter.values():
        probability = count / total_length
        entropy -= probability * math.log2(probability)

    return entropy

def sliding_window_entropy(file_path: str, window_size: int = 1024) -> List[float]:
    """
    Calculate sliding window entropy for anomaly detection.
    Returns list of entropy values for each window.
    
    Args:
        file_path: Path to the file.
        window_size: Size of sliding window.
    
    Returns:
        List of entropy values.
    """
    entropies = []
    
    with open(file_path, 'rb') as f:
        window = f.read(window_size)
        while window:
            if len(window) >= 256:  # Minimum for meaningful entropy
                counter = Counter(window)
                length = len(window)
                entropy = 0.0
                for count in counter.values():
                    probability = count / length
                    entropy -= probability * math.log2(probability)
                entropies.append(entropy)
            
            # Slide window
            next_byte = f.read(1)
            if not next_byte:
                break
            window = window[1:] + next_byte
    
    return entropies