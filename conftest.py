"""
Root conftest.py — ensures the project root is on sys.path for all tests.
"""
import sys
from pathlib import Path

# Add project root so `from src.agent...` imports work in every test file
sys.path.insert(0, str(Path(__file__).parent))
