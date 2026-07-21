from pathlib import Path


def clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in "'\"" and value[-1] in "'\"":
        value = value[1:-1]
    return value.strip().rstrip(",")


def main() -> None:
    path = Path(".env")
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        lines.append(f"{key.strip()}={clean(value)}")

    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"rewrote {len(lines)} vars")


if __name__ == "__main__":
    main()
