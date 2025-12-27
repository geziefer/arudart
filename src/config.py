import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def load_config(config_path):
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        return tomllib.load(f)
