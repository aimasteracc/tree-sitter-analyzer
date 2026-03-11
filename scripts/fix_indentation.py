#!/usr/bin/env python3
"""Fix indentation in SQL plugin."""

# Read the file
with open("tree_sitter_analyzer/languages/sql_plugin.py", encoding="utf-8") as f:
    lines = f.readlines()

# Fix the indentation starting from line 1461 (0-indexed: 1460)
# The issue is that after "if match:" the code has extra indentation
fixed_lines = []
in_fix_zone = False
for i, line in enumerate(lines):
    line_num = i + 1

    # Start fixing after "if match:"
    if line_num == 1461 and line.strip() == "if match:":
        fixed_lines.append(line)
        in_fix_zone = True
        continue

    # Stop fixing at the "else:" that corresponds to "if match:"
    if (
        in_fix_zone
        and line_num >= 1530
        and line.strip().startswith("else:")
        and line.startswith("                else:")
    ):
        # This is the problematic else - it should be at the same level as "if match:"
        fixed_lines.append("            else:\n")
        in_fix_zone = False
        continue

    # Fix indentation in the zone
    if in_fix_zone and line.startswith("                    "):
        # Remove 4 extra spaces
        fixed_lines.append(line[4:])
    else:
        fixed_lines.append(line)

# Write back
with open("tree_sitter_analyzer/languages/sql_plugin.py", "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)

print("Fixed indentation!")
