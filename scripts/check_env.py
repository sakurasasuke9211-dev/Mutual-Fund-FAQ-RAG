from pathlib import Path

from dotenv import dotenv_values

path = Path(".env")
print("exists:", path.exists())
print("size:", path.stat().st_size)
raw = path.read_bytes()
print("starts_with_bom:", raw.startswith(b"\xef\xbb\xbf"))

for i, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
    if not line.strip():
        print(f"{i}: empty")
        continue
    if "=" in line:
        key, value = line.split("=", 1)
        value = value.strip()
        print(
            f"{i}: key={key.strip()!r} value_len={len(value)} "
            f"has_hash={'#' in value} has_space={' ' in value} "
            f"has_equal={'=' in value} starts_with_quote={value[:1] in '\"'}"
        )
    else:
        print(f"{i}: invalid line")

parsed = dotenv_values(path)
print("parsed_keys:", sorted(parsed.keys()))
print("api_key_set:", bool(parsed.get("CHROMA_API_KEY")))
print("tenant_set:", bool(parsed.get("CHROMA_TENANT")))
print("database_set:", bool(parsed.get("CHROMA_DATABASE")))
