#! /usr/bin/env python3
import re
from pathlib import Path
import logging

# Define Sanskrit vowels
vowels = "अआइईउऊऋॠऌॡएऐओऔ"

def fix_m_ending(line1, line2):
    """
    If line1 ends with म् immediately before }, and the first character after {
    in line2 is not a Sanskrit vowel, replace म् with ं.
    """
    pattern = r'(म्)\}(\s*(%.*)?\n?)$'
    match = re.search(pattern, line1)
    if match:
        # Check the first character after '{' in line2
        first_char = line2[1]
        if first_char not in vowels:
            return re.sub(pattern, r'ं}\2', line1)
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
            l1, l2, l3, l4 = lines[i+1:i+5]
            orig = (l1, l3)
            l1_fixed = fix_m_ending(l1, l2)
            l3_fixed = fix_m_ending(l3, l4)
            if (l1 != l1_fixed) or (l3 != l3_fixed):
                changed = True
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
for tex_file in Path('.').rglob('*.tex'):
    process_file(tex_file)
