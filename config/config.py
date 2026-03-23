import os
import json

BASE_DIR = os.getcwd()
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
print(CONFIG_FILE)
config = None


def load_config_from_json():
    global config
    try:
        if config:
            return config
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        logger.error(
            "Config file not found. You need to create file config: config.json on same path of exec file.")
        input("Press Enter to exit...")
        sys.exit(1)
