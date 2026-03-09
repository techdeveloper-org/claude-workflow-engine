#!/usr/bin/env python3
"""Check for colon-backslash patterns in post-tool-tracker.py"""

with open('scripts/post-tool-tracker.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')

    found_patterns = []
    for i, line in enumerate(lines, 1):
        if b':\\' in line:
            found_patterns.append((i, line.decode('utf-8', errors='ignore')))

    if found_patterns:
        print(f"Found {len(found_patterns)} lines with :\\ pattern:")
        for line_num, line_content in found_patterns[:20]:
            print(f"  Line {line_num}: {line_content[:100]}")
    else:
        print("No :\\ patterns found in post-tool-tracker.py")
