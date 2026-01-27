"""Pytest configuration for Automation Mutation Tester tests."""

import sys
from pathlib import Path

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))
