# imghdr_compat.py
import os
import struct

def what(file):
    with open(file, 'rb') as f:
        head = f.read(32)
    if len(head) < 32:
        return None
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    elif head.startswith(b'\xff\xd8'):
        return 'jpeg'
    elif head.startswith(b'GIF'):
        return 'gif'
    elif head.startswith(b'BM'):
        return 'bmp'
    return None