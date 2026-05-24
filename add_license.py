# SPDX-FileCopyrightText: 2026 Firdaus Hakimi <hakimifirdaus944@gmail.com>
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

license_header = """\
# SPDX-FileCopyrightText: 2026 Firdaus Hakimi <hakimifirdaus944@gmail.com>
# SPDX-License-Identifier: Apache-2.0
"""


def add_license_header(file_path) -> bool:
    with open(file_path, "r+") as f:
        content = f.read()

        if license_header in content:
            return False

        f.seek(0, 0)
        f.write(license_header.lstrip("\n") + "\n" + content)
        return True


def main() -> None:
    hidden_dirs: set[Path] = set(Path(".").glob(".*"))

    for file in Path(".").rglob("*.py"):
        if hidden_dirs.intersection(file.parents):
            continue

        add_license_header(file) and print(f"-> Added license header to {file}")


if __name__ == "__main__":
    main()
