from itertools import chain
from pathlib import Path

try:
    import tomllib as toml
except ImportError:
    try:
        import toml
    except ImportError:
        print("Use Python 3.11 or install `toml` by running `pip install toml`.")


def dumps_file(string, path, utf8=True, lf_newline=True):
    encoding = "utf8" if utf8 else None
    newline = "\n" if lf_newline else None
    with open(path, "w", encoding=encoding, newline=newline) as f:
        f.write(string)
    return path


def read_toml(path: str):
    """Reads a TOML file.

    Args:
        path (str): Path to the file.

    Returns:
        data (JSONOutput): The data.
    """
    with open(path, "r") as f:
        return toml.load(f)


api_dir = Path(__file__).resolve().parent.parent.parent.parent
all_deps = set()
project_names = set()
# Go through the pyproject files
for pyproj in [api_dir / "pyproject.toml"]:
    project = read_toml(pyproj)["project"]
    project_names.add(project["name"])
    deps = project["dependencies"] + list(
        chain.from_iterable(project["optional-dependencies"].values())
    )
    all_deps.update(deps)
# Only keep external dependencies
all_deps = [dep for dep in all_deps if not any(dep.startswith(name) for name in project_names)]
all_deps = sorted(all_deps, key=lambda x: x.lower())
print(all_deps)
dumps_file("\n".join(all_deps), api_dir / "requirements.txt")
