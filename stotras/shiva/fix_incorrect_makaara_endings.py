#! /usr/bin/env python3
import re
from pathlib import Path
import sys
import logging

# Define Sanskrit vowels
vowels = "अआइईउऊऋॠऌॡएऐओऔ"

def fix_m_ending(line1, line2):
    """
    If line1 ends with म् immediately before }, and the first character after {
    in line2 is not a Sanskrit vowel, replace म् with ं.
    """
    pattern = r'(म्)\}(\s*(%.*)?\n?)$'
    match = re.search(pattern, line1.strip())
    if match:
        # Check the first character after '{' in line2
        print("Match found:", match.group(0))
        print("Line1:", line1.strip())
        print("Line2:", line2.strip())
        first_char = line2[1]
        print(first_char)
        if first_char not in vowels:
            return re.sub(pattern, r'ं}\2', line1.strip())
    return line1

def process_file(path):
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    changed = False

    while i < len(lines):
        line = lines[i]
        match = re.match(r'\\fourlineindentedshloka\*?\s*$', line.strip())
        if match and i + 4 < len(lines):
            # Extract the next four lines
            l1, l2, l3, l4 = lines[i+1:i+5]
            print (l1, l2, l3, l4)
            orig = (l1, l3)
            l1_fixed = fix_m_ending(l1, l2)
            l3_fixed = fix_m_ending(l3, l4)
            if (l1 != l1_fixed) or (l3 != l3_fixed):
                changed = True
                print("Changed:", orig, "->", (l1_fixed, l3_fixed))
            new_lines.extend([line, l1_fixed, l2, l3_fixed, l4])
            i += 5
        else:
            new_lines.append(line)
            i += 1

    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Fixed: {path}")

# Walk through all .tex files and process
# for tex_file in Path('.').rglob('*.tex'):
#     print(f"Processing: {tex_file}")
#     process_file(tex_file)

for tex_file in sys.argv[1:]:
    print(f"Processing: {tex_file}")
    process_file(tex_file)
