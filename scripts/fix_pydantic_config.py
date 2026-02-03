#!/usr/bin/env python3
"""Script to update Pydantic models from V1 Config to V2 ConfigDict."""

import re
import os
from pathlib import Path


def fix_pydantic_config(file_path: Path):
    """Fix Pydantic config in a single file."""
    print(f"Processing {file_path}")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Add ConfigDict import if needed
    if 'from pydantic import' in content and 'ConfigDict' not in content:
        content = re.sub(
            r'from pydantic import ([^,\n]+)(?:, ([^,\n]+))*',
            lambda m: f"from pydantic import {m.group(1)}, ConfigDict" + 
                     (f", {m.group(2)}" if m.group(2) else ""),
            content
        )
    
    # Find and replace Config classes
    config_pattern = r'(\s+)class Config:\s*\n(\s+)(.*?)\n(?=\s*\n|\s*[a-zA-Z_]|\Z)'
    
    def replace_config(match):
        indent = match.group(1)
        content_indent = match.group(2)
        config_content = match.group(3)
        
        # Extract the config content and reformat
        if 'json_schema_extra' in config_content:
            return f"{indent}model_config = ConfigDict(\n{content_indent}{config_content}\n{indent})"
        else:
            return f"{indent}model_config = ConfigDict({config_content})"
    
    # This is a more complex pattern - let's handle it manually for each case
    # Look for the specific pattern: class Config: followed by json_schema_extra
    pattern = r'(\s+)class Config:\s*\n(\s+)json_schema_extra\s*=\s*({[^}]+}(?:[^}]*{[^}]*})*[^}]*})'
    
    def replace_simple_config(match):
        indent = match.group(1)
        json_content = match.group(3)
        return f"{indent}model_config = ConfigDict(\n{indent}    json_schema_extra={json_content}\n{indent})"
    
    content = re.sub(pattern, replace_simple_config, content, flags=re.MULTILINE | re.DOTALL)
    
    # Write back
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {file_path}")


def main():
    """Main function to process all API files."""
    api_dir = Path("src/api")
    
    if not api_dir.exists():
        print("API directory not found - make sure you're in the right directory")
        return
    
    # Process all Python files in the API directory
    for py_file in api_dir.glob("*.py"):
        if py_file.name != "__init__.py":
            fix_pydantic_config(py_file)
    
    print("Done!")


if __name__ == "__main__":
    main()