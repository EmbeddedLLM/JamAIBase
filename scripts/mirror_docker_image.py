"""
Docker Image Mirror Tool
Mirrors selected Docker images from source to destination registry using `skopeo`.
"""

import json
import subprocess
import sys


def run_command(cmd, capture_output=True):
    """Run a shell command and return output."""
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        else:
            return subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        return None
    except FileNotFoundError:
        print("Error: 'skopeo' not found. Please install it first.")
        sys.exit(1)


def check_skopeo_installed() -> bool:
    """Check if skopeo is installed."""
    try:
        subprocess.run(["skopeo", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def list_tags(image_path) -> list[str] | None:
    """List all tags for a given image."""
    print(f"\nFetching tags from {image_path}...")

    output = run_command(["skopeo", "list-tags", f"docker://{image_path}"])
    if not output:
        return None

    try:
        data = json.loads(output)
        return [t for t in data.get("Tags", []) if "sha256" not in t]
    except json.JSONDecodeError as e:
        print(f"Error parsing tags: {e}")
        return None


def copy_image(source, destination, tag):
    """Copy a single image tag using skopeo."""
    if ":" in source:
        source = source.split(":")[0]
    if ":" in destination:
        destination = destination.split(":")[0]
    source_full = f"docker://{source}:{tag}"
    dest_full = f"docker://{destination}:{tag}"

    print(f"\nCopying {tag}...")
    print(f"  From: {source_full}")
    print(f"  To:   {dest_full}")

    cmd = ["skopeo", "copy", source_full, dest_full]
    return run_command(cmd, capture_output=False) is not None


def main():
    print("=" * 60)
    print("Docker Image Mirror Tool")
    print("=" * 60)

    # Check if skopeo is installed
    if not check_skopeo_installed():
        print("\n❌ Error: skopeo is not installed.")
        print("\nInstallation instructions:")
        print("  Ubuntu/Debian: sudo apt-get install skopeo")
        print("  macOS: brew install skopeo")
        print("  Fedora/RHEL: sudo dnf install skopeo")
        sys.exit(1)

    print("✅ skopeo is installed")

    # Get source and destination
    source_image = input("\nEnter source image path (tag is optional): ").strip()
    if not source_image:
        print("Error: Source image cannot be empty")
        sys.exit(1)

    destination_image = input("Enter destination image path (exclude tag): ").strip()
    if not destination_image:
        destination_image = f"ghcr.io/embeddedllm/{source_image}"
        print(f'Defaulting to "{destination_image}"')

    # List available tags
    if ":" in source_image:
        src_tag = source_image.split(":")[-1]
        if ":" in destination_image and src_tag != destination_image.split(":")[-1]:
            print("Error: When specifying tags in source and destination, they must match")
            sys.exit(1)
        tags = [src_tag]
    else:
        tags = list_tags(source_image)
        if not tags:
            print("Error: No tags found")
            sys.exit(1)
    if len(tags) == 1:
        selected_tags = tags
    else:
        print(f"\nAvailable tags ({len(tags)} total):")
        for tag in tags:
            print(f"  - {tag}")

        # Get user selection
        print("\nEnter tags to mirror (comma-separated):")
        print("Example: latest,v1.0.0,v1.1.0")
        selection = input("Tags: ").strip()

        if not selection:
            print("Error: No tags selected")
            sys.exit(1)

        selected_tags = [tag.strip() for tag in selection.split(",")]

        # Validate selected tags
        invalid_tags = [tag for tag in selected_tags if tag not in tags]
        if invalid_tags:
            print(f"\nError: Invalid tags: {', '.join(invalid_tags)}")
            sys.exit(1)

    # Confirm
    print(f"\nWill mirror {len(selected_tags)} tag(s):")
    for tag in selected_tags:
        print(f"  - {tag}")

    confirm = input("\nProceed? (Y/n): ").strip().lower()
    if confirm not in ("", "y"):
        print("Cancelled")
        sys.exit(0)

    # Copy images
    print("\nStarting mirror process...")
    success_count = 0
    failed_tags = []

    for idx, tag in enumerate(selected_tags, 1):
        print(f"\n[{idx}/{len(selected_tags)}]")
        if copy_image(source_image, destination_image, tag):
            success_count += 1
            print(f"✅ Success: {tag}")
        else:
            failed_tags.append(tag)
            print(f"❌ Failed: {tag}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Summary: {success_count}/{len(selected_tags)} successful")
    if failed_tags:
        print(f"Failed tags: {', '.join(failed_tags)}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
