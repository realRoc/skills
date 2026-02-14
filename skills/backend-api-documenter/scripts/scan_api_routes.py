#!/usr/bin/env python3
"""
Scan backend API routes and extract endpoint information.

Usage:
    python3 scan_api_routes.py <backend_dir>

Example:
    python3 scan_api_routes.py ./backend
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any
import ast


def extract_routes_from_file(file_path: Path) -> List[Dict[str, Any]]:
    """Extract route information from a Python API route file."""
    routes = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find all router decorator patterns
        route_pattern = r'@router\.(get|post|put|patch|delete)\s*\((.*?)\)'
        matches = re.finditer(route_pattern, content, re.DOTALL)

        for match in matches:
            method = match.group(1).upper()
            params = match.group(2)

            # Extract path
            path_match = re.search(r'["\']([^"\']+)["\']', params)
            path = path_match.group(1) if path_match else ""

            # Extract summary
            summary_match = re.search(r'summary\s*=\s*["\']([^"\']+)["\']', params)
            summary = summary_match.group(1) if summary_match else ""

            # Extract description
            desc_match = re.search(r'description\s*=\s*["\']([^"\']+)["\']', params)
            description = desc_match.group(1) if desc_match else ""

            routes.append({
                'method': method,
                'path': path,
                'summary': summary,
                'description': description,
                'file': file_path.name
            })

    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)

    return routes


def scan_api_directory(backend_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """Scan all API route files in the backend directory."""
    api_dir = Path(backend_dir) / "app" / "api" / "v1"

    if not api_dir.exists():
        print(f"API directory not found: {api_dir}", file=sys.stderr)
        return {}

    routes_by_module = {}

    for py_file in api_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue

        routes = extract_routes_from_file(py_file)
        if routes:
            module_name = py_file.stem
            routes_by_module[module_name] = routes

    return routes_by_module


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scan_api_routes.py <backend_dir>")
        sys.exit(1)

    backend_dir = sys.argv[1]
    routes_by_module = scan_api_directory(backend_dir)

    # Print results
    print(f"Found {len(routes_by_module)} API modules:\n")

    for module, routes in sorted(routes_by_module.items()):
        print(f"## {module}.py ({len(routes)} endpoints)")
        for route in routes:
            print(f"  {route['method']} {route['path']}")
            if route['summary']:
                print(f"    Summary: {route['summary']}")
        print()


if __name__ == "__main__":
    main()
