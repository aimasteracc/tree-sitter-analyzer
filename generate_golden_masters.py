"""
Generate Golden Master Reference Files

This script generates golden master reference files for format regression testing.
It analyzes sample files and creates reference outputs for each format type.
"""

from pathlib import Path

from tree_sitter_analyzer.api import analyze_file
from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter


def generate_golden_master(file_path: str, format_type: str, output_name: str) -> None:
    """Generate golden master for a specific format"""
    print(f"Generating golden master: {output_name} ({format_type} format)")

    # Analyze the file to get the structure
    result = analyze_file(file_path)

    if not result.get("success", False):
        print(f"  ✗ Failed to analyze: {file_path}")
        return

    # Extract elements for formatting
    elements = result.get("elements", [])

    # Create structure dictionary for formatter
    structure = {
        "file_path": file_path,
        "language": result.get("language_info", {}).get("language", "unknown"),
        "format_type": format_type,  # Add format_type to structure
        "package": None,
        "imports": [],
        "classes": [],
        "functions": [],
        "variables": [],
    }

    # Extract package, imports, and classes from elements
    for elem in elements:
        elem_type = elem.get("type", "")
        if elem_type == "package":
            structure["package"] = {"name": elem.get("name", "")}
        elif elem_type == "import":
            structure["imports"].append(
                {
                    "name": elem.get("name", ""),
                    "import_statement": elem.get(
                        "import_statement", elem.get("name", "")
                    ),
                }
            )
        elif elem_type == "class":
            class_info = {
                "name": elem.get("name", ""),
                "modifiers": elem.get("modifiers", []),
                "line_number": elem.get("line_number", 0),
                "methods": [],
                "fields": [],
            }

            # Get methods and fields for this class
            for child in elements:
                child_class = child.get("class_name", child.get("parent", ""))
                if child_class == elem.get("name", ""):
                    if child.get("type") == "method":
                        class_info["methods"].append(
                            {
                                "name": child.get("name", ""),
                                "return_type": child.get("return_type", ""),
                                "parameters": child.get("parameters", []),
                                "modifiers": child.get("modifiers", []),
                                "line_number": child.get("line_number", 0),
                                "is_constructor": child.get("is_constructor", False),
                            }
                        )
                    elif child.get("type") == "field":
                        class_info["fields"].append(
                            {
                                "name": child.get("name", ""),
                                "field_type": child.get(
                                    "field_type", child.get("return_type", "")
                                ),
                                "modifiers": child.get("modifiers", []),
                                "line_number": child.get("line_number", 0),
                            }
                        )

            structure["classes"].append(class_info)

    # Format using LegacyTableFormatter
    formatter = LegacyTableFormatter()
    formatted_output = formatter.format_structure(structure)

    output_dir = Path("tests/golden_masters") / format_type
    output_dir.mkdir(parents=True, exist_ok=True)

    extension = "csv" if format_type == "csv" else "md"
    output_file = output_dir / f"{output_name}.{extension}"

    output_file.write_text(formatted_output, encoding="utf-8")
    print(f"  ✓ Created: {output_file}")


def main():
    """Generate all golden master files"""
    print("=" * 60)
    print("Golden Master Generation")
    print("=" * 60)

    # Sample.java - Multiple classes test case
    sample_java = "examples/Sample.java"

    # Generate golden masters for Sample.java
    generate_golden_master(sample_java, "full", "java_sample_multiclass_full")
    generate_golden_master(sample_java, "compact", "java_sample_multiclass_compact")
    generate_golden_master(sample_java, "csv", "java_sample_multiclass_csv")

    # UserService.java - Single class test case (if exists in test data)
    user_service_candidates = [
        Path("tests/test_data/java/UserService.java"),
        Path("tests/format_testing/test_data/UserService.java"),
    ]

    user_service_java = None
    for candidate in user_service_candidates:
        if candidate.exists():
            user_service_java = str(candidate)
            break

    if user_service_java:
        generate_golden_master(user_service_java, "full", "java_userservice_full")
        generate_golden_master(user_service_java, "compact", "java_userservice_compact")
        generate_golden_master(user_service_java, "csv", "java_userservice_csv")
    else:
        print("  ⚠ UserService.java not found - skipping")

    # BigService.java - Large class test case
    big_service_java = "examples/BigService.java"
    if Path(big_service_java).exists():
        generate_golden_master(big_service_java, "full", "java_bigservice_full")
        generate_golden_master(big_service_java, "compact", "java_bigservice_compact")
        generate_golden_master(big_service_java, "csv", "java_bigservice_csv")
    else:
        print("  ⚠ BigService.java not found - skipping")

    print()
    print("=" * 60)
    print("Golden Master Generation Complete")
    print("=" * 60)
    print()
    print("Generated files are in: tests/golden_masters/")
    print()
    print("Next steps:")
    print("1. Review generated files to ensure they are correct")
    print("2. Run tests to validate: pytest tests/format_testing/")
    print("3. Commit golden master files to repository")


if __name__ == "__main__":
    main()
