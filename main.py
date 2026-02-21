from integrity import hashing as hash
from core import carver as c
from pathlib import Path

print("Image hash:", hash.sha256_file("test.img"))

file = c.FileCarver("test.img", "./temp")

count = file.carve_jpeg()

print("Recovered files:", count)
