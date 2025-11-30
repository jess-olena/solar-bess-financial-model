#src/config_loader.py
import yaml
import os

def load_config(path=None):
    # Automatically resolve path relative to project root
    if path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "config.yaml")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found at: {path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)
