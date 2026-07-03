#!/usr/bin/env python3
"""
KH/CambodiaLawDataset -- Cambodia Law Dataset from GitHub

Fetches Cambodian laws from the open-source rinn7e/cambodia-law-dataset
GitHub repository. Laws are in structured Markdown format with full text.

Strategy:
  - Use GitHub API to list markdown files in dataset/ directory
  - Fetch raw content of English (-en.md) files
  - Parse title, date, and full text from Markdown structure

Usage:
  python bootstrap.py bootstrap          # Full pull
  python bootstrap.py bootstrap --sample # 10+ sample records
  python bootstrap.py test               # Connectivity test
"""

import sys
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common.base_scraper import BaseScraper
from common.http_client import HttpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("legal-data-hunter.KH.CambodiaLawDataset")

GITHUB_API = "https://api.github.com"
REPO = "rinn7e/cambodia-law-dataset"
RAW_BASE = "https://raw.githubusercontent.com/rinn7e/cambodia-law-dataset/master"

HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "application/vnd.github.v3+json",
}

RAW_HEADERS = {
    "User-Agent": "LegalDataHunter/1.0 (Open Data Research)",
    "Accept": "text/plain",
}


class CambodiaLawDatasetScraper(BaseScraper):
    """
    Scraper for KH/CambodiaLawDataset.
    Fetches Cambodian laws from a public GitHub repository.
    """

    def __init__(self):
        source_dir = Path(__file__).parent
        super().__init__(source_dir)
        self.api_client = HttpClient(
            base_url=GITHUB_API,
            headers=HEADERS,
            timeout=30,
        )
        self.raw_client = HttpClient(
            base_url=RAW_BASE,
            headers=RAW_HEADERS,
            timeout=30,
        )

    def _list_dataset_files(self) -> List[Dict[str, str]]:
        """List all English markdown files in the dataset/ directory."""
        self.rate_limiter.wait()
        resp = self.api_client.get(
            f"/repos/{REPO}/git/trees/master",
            params={"recursive": "1"},
        )
        resp.raise_for_status()
        data = resp.json()

        files = []
        for item in data.get("tree", []):
            path = item.get("path", "")
            if (
                path.startswith("dataset/")
                and path.endswith("-en.md")
                and item.get("type") == "blob"
            ):
                files.append({"path": path, "sha": item.get("sha", "")})

        logger.info(f"Found {len(files)} English law files in dataset/")
        return files

    def _fetch_file_content(self, path: str) -> str:
        """Fetch raw content of a file from the repo."""
        self.rate_limiter.wait()
        # URL-encode the path for raw.githubusercontent.com
        encoded_path = path.replace(" ", "%20")
        resp = self.raw_client.get(f"/{encoded_path}")
        resp.raise_for_status()
        return resp.text

    def _parse_title(self, content: str, filename: str) -> str:
        """Extract the law title from markdown content."""
        # Primary: derive from directory name (most reliable)
        parts = filename.split("/")
        dirname = parts[1] if len(parts) > 1 else filename
        name = dirname
        name = re.sub(r"^\d+-", "", name)  # Remove leading number
        name = re.sub(r"-\d{4}$", "", name)  # Remove year suffix
        name = re.sub(r"-[\u1780-\u17FF\u200B_]+.*", "", name)  # Remove Khmer
        name = name.rstrip("-")
        dir_title = name.replace("-", " ").title()

        # Try to find a better title from # headings in content
        skip_lower = {
            "contents", "law", "code", "kingdom of cambodia",
            "nation religion king", "royal decree", "royal code",
            "preamble", "we", "on", "table of contents", "promulgate",
        }
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# ") and len(line) > 3:
                title = line[2:].strip()
                title_clean = re.sub(r"\s*\([\u1780-\u17FF\u200B\s]+\)\s*", "", title).strip()
                low = title_clean.lower()
                if low in skip_lower or len(title_clean) < 10:
                    continue
                if low.startswith("chapter ") or low.startswith("royal "):
                    continue
                # Good title found — use it if it contains "law" or "code"
                if any(w in low for w in ("law ", "code ", "statute", "constitution")):
                    return title
                # Otherwise, prefer dir_title if it's meaningful
                if len(dir_title) > 10:
                    return dir_title
                return title

        return dir_title

    def _parse_date(self, content: str, dirname: str) -> str:
        """Extract the year/date from content or directory name."""
        # Check directory name for year
        year_match = re.search(r"-(\d{4})(?:/|-en\.md)", dirname)
        if year_match:
            return f"{year_match.group(1)}-01-01"

        # Look for year in first 20 lines
        for line in content.split("\n")[:20]:
            year_m = re.search(r"\b(19|20)\d{2}\b", line)
            if year_m:
                return f"{year_m.group(0)}-01-01"

        return ""

    def _parse_decree_number(self, content: str) -> str:
        """Extract the decree/law number."""
        for line in content.split("\n")[:15]:
            # Pattern: "Number: NS/RKM/..." or "No. ..."
            m = re.search(r"(?:Number|No\.?)\s*:?\s*(NS/[^\s]+|[\w/-]+)", line)
            if m:
                return m.group(1)
        return ""

    def fetch_all(self) -> Generator[dict, None, None]:
        """Yield all English law documents from the dataset."""
        files = self._list_dataset_files()
        total = 0

        for file_info in files:
            path = file_info["path"]
            try:
                content = self._fetch_file_content(path)

                if not content or len(content.strip()) < 100:
                    logger.warning(f"Skipping empty/tiny file: {path}")
                    continue

                yield {
                    "path": path,
                    "sha": file_info["sha"],
                    "content": content,
                }
                total += 1

            except Exception as e:
                logger.warning(f"Failed to fetch {path}: {e}")
                continue

        logger.info(f"Fetched {total} law documents")

    def fetch_updates(self, since: datetime) -> Generator[dict, None, None]:
        """Yield all documents (no incremental update for static repo)."""
        yield from self.fetch_all()

    def normalize(self, raw: dict) -> dict:
        """Transform raw markdown file into standard schema."""
        path = raw.get("path", "")
        content = raw.get("content", "")

        # Clean the markdown: remove image refs, clean up formatting
        # Strip Markdown formatting for text field but keep structure
        text = content.strip()

        title = self._parse_title(content, path)
        date_str = self._parse_date(content, path)
        decree_num = self._parse_decree_number(content)

        # Build a stable ID from the directory name
        parts = path.split("/")
        dirname = parts[1] if len(parts) > 1 else path
        # Remove Khmer characters and -en.md suffix for clean ID
        clean_id = re.sub(r"-[\u1780-\u17FF\u200B]+", "", dirname)
        clean_id = clean_id.rstrip("-")

        url = f"https://github.com/{REPO}/blob/master/{path}"

        return {
            "_id": f"KH-LAW-{clean_id}",
            "_source": "KH/CambodiaLawDataset",
            "_type": "legislation",
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "text": text,
            "date": date_str,
            "url": url,
            "decree_number": decree_num,
            "language": "en",
            "file_path": path,
            "sha": raw.get("sha", ""),
        }

    def test_connection(self):
        """Quick connectivity test."""
        print("Testing GitHub API access...")

        try:
            resp = self.api_client.get(f"/repos/{REPO}")
            repo = resp.json()
            print(f"  Repo: {repo.get('full_name')}")
            print(f"  Stars: {repo.get('stargazers_count')}")
            print(f"  License: {repo.get('license', {}).get('spdx_id')}")
            print(f"  Updated: {repo.get('updated_at')}")
        except Exception as e:
            print(f"  ERROR: {e}")
            return

        print("\nListing dataset files...")
        try:
            files = self._list_dataset_files()
            print(f"  Found {len(files)} English law files")
            if files:
                print(f"  Sample: {files[0]['path']}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\nTest complete!")


def main():
    scraper = CambodiaLawDatasetScraper()

    if len(sys.argv) < 2:
        print("Usage: python bootstrap.py [bootstrap|update|test] [--sample] [--sample-size N]")
        sys.exit(1)

    command = sys.argv[1]
    sample_mode = "--sample" in sys.argv
    sample_size = 12
    if "--sample-size" in sys.argv:
        idx = sys.argv.index("--sample-size")
        sample_size = int(sys.argv[idx + 1])

    if command == "test":
        scraper.test_connection()
    elif command == "bootstrap":
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
            print(f"\nSample complete: {stats.get('sample_records_saved', 0)} records saved")
        else:
            stats = scraper.bootstrap()
            print(f"\nBootstrap complete: {stats['records_new']} new, "
                  f"{stats['records_updated']} updated")
        print(json.dumps(stats, indent=2))
    elif command == "update":
        stats = scraper.update()
        print(f"\nUpdate complete: {stats['records_new']} new")
        print(json.dumps(stats, indent=2))
    elif command == "bootstrap-fast":
        if sample_mode:
            stats = scraper.run_sample(n=sample_size)
        else:
            stats = scraper.bootstrap()
        print(json.dumps(stats, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
