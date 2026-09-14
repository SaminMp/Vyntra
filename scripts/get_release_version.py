"""
Determines the release tag and release name for GitHub Actions.
Supports both manual git tag triggers (e.g. v1.2.0) and automated releases
on every push to the main branch with automatic patch version incrementing.
Ensures vyntra/__init__.py __version__ matches the compiled binary and release tag.
"""

import os
from pathlib import Path
import re
import subprocess
import sys


def update_init_version(root_dir: Path, version: str):
    """Syncs __version__ in vyntra/__init__.py to match the release version."""
    init_path = root_dir / "vyntra" / "__init__.py"
    if init_path.exists():
        content = init_path.read_text(encoding="utf-8")
        updated = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
        if updated != content:
            init_path.write_text(updated, encoding="utf-8")
            print(f"[Release] Updated {init_path} with __version__ = \"{version}\"")


def get_release_tag_and_name():
    root_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root_dir))

    # Fetch remote tags to ensure local view is up to date
    subprocess.run(["git", "fetch", "--tags", "--force"], cwd=str(root_dir), check=False)

    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/v"):
        tag_name = ref.replace("refs/tags/", "")
        version = tag_name.lstrip("v")
        release_name = f"Vyntra {tag_name}"
        print(f"[Release] Using explicit git tag: {tag_name}")
    else:
        import vyntra
        base_version = getattr(vyntra, "__version__", "1.2.1").strip()
        print(f"[Release] Base version from vyntra/__init__.py: {base_version}")

        # Query all existing tags
        res = subprocess.run(
            ["git", "tag", "-l"],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        existing_tags = set(res.stdout.split())

        tag_name = f"v{base_version}"
        if tag_name in existing_tags:
            # Tag already exists on remote - auto-increment patch
            parts = []
            for part in base_version.split("."):
                digits = "".join(filter(str.isdigit, part))
                parts.append(int(digits) if digits else 0)
            while len(parts) < 3:
                parts.append(0)

            while f"v{parts[0]}.{parts[1]}.{parts[2]}" in existing_tags:
                parts[2] += 1

            tag_name = f"v{parts[0]}.{parts[1]}.{parts[2]}"
            version = f"{parts[0]}.{parts[1]}.{parts[2]}"
            print(f"[Release] Tag v{base_version} already exists. Auto-incremented to new tag: {tag_name}")
        else:
            version = base_version
            print(f"[Release] Tag {tag_name} is new and available.")

        release_name = f"Vyntra {tag_name}"

    # Synchronize codebase version so built binary and release tag match 100%
    update_init_version(root_dir, version)

    # Export to GitHub Actions output if running in CI
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"tag_name={tag_name}\n")
            f.write(f"release_name={release_name}\n")
            f.write(f"version={version}\n")

    print(f"[Release] Final release tag: {tag_name}")
    print(f"[Release] Final release name: {release_name}")
    print(f"[Release] Final version: {version}")
    return tag_name, release_name, version


if __name__ == "__main__":
    get_release_tag_and_name()
