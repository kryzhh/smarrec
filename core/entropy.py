import math
from collections import Counter

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