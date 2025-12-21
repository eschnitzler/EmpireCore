import sys

sys.path.insert(0, "src")

try:
    print("All core modules imported successfully.")
except Exception as e:
    print(f"Error importing core modules: {e}")
    sys.exit(1)
