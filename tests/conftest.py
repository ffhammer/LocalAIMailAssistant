import os
import sys

# Set environment variables early
os.environ["TEST_BACKEND"] = "True"

# Ensure current dir is on sys.path
sys.path.insert(0, os.path.abspath("."))
