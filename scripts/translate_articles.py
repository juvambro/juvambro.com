import hashlib
import os
import re
from pathlib import Path

import markdown
import requests
import yaml
from bs4 import BeautifulSoup

SOURCE_DIR = Path("articles")
TARGET_DIR = Path("pt/articles")
DEEPL_URL = "https://api.deepl.com/v2/translate"
AUTH_KEY = os.environ.get("DEEPL_AUTH_KEY")

if not AUTH_KEY:
    raise SystemExit("Missing DEEPL_AUTH_KEY GitHub Actions secret.")

def split_frontmatter(text, filename):
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)\Z", text, re.S)
    if not match:
        raise ValueError(f"{filename}: YAML frontmatter not found.")
    return yaml.safe_load(match.group(1)) or {}, match.group(2).strip()

def translate(text, html=False):
    if not text or not text.strip():
        return text
    data = {"text": text, "source_lang": "EN", "target_lang": "PT-PT"}
    if html:
        data["tag_handling"] = "html"
    response = requests.post(
        DEEPL_URL,
        headers={"Authorization": f"DeepL-Auth-Key {AUTH_KEY}"},
        data=data,
        timeout=60,
    )
    if response.status_code == 456:
        raise RuntimeError("DeepL character quota reached; no translation saved.")
    response.raise_for_status()
    return response.json()["translations"][0]["text"]

def translate_html_blocks(html):
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for node in list(soup.contents):
        block = str(node).strip()
        if block:
            result.append(translate(block, html=True))
    return "\n\n".join(result)

def main():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for source in sorted(SOURCE_DIR.glob("*.md")):
        raw = source.read_text(encoding="utf-8")
        meta, body = split_frontmatter(raw, source.name)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        target = TARGET_DIR / source.name

        if target.exists():
            old_meta, _ = split_frontmatter(target.read_text(encoding="utf-8"), target.name)
            if old_meta.get("source_sha256") == digest:
                print(f"Skipping unchanged article: {source.name}")
                continue

        translated_meta = dict(meta)
        translated_meta["title"] = translate(str(meta.get("title", source.stem)))
        translated_meta["description"] = translate(str(meta.get("description", "")))
        translated_meta["source_sha256"] = digest

        html = markdown.markdown(body, extensions=["extra", "sane_lists", "tables"])
        translated_body = translate_html_blocks(html)

        frontmatter = "---\n" + yaml.safe_dump(
            translated_meta, allow_unicode=True, sort_keys=False
        ) + "---\n\n"
        target.write_text(frontmatter + translated_body.strip() + "\n", encoding="utf-8")
        print(f"Translated {source.name} -> {target}")

if __name__ == "__main__":
    main()
