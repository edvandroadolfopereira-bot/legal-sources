#!/usr/bin/env python3
"""
Haiti Ministry of Economy and Finance — Key Laws

Laws, decrees, and arrêtés from mef.gouv.ht/cadre-reglementaire/.
8 laws + 14 decrees + 15 arrêtés = 37 total documents.
PDFs downloaded and text extracted via pdfplumber.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SOURCE_ID = "HT/MEF-Lois"
BASE_URL = "https://mef.gouv.ht"

# Known documents from the laws page (static list — only 8 documents)
DOCUMENTS = [
    {
        "id": "loi-2016-05-04",
        "title": "Loi du 4 Mai 2016 remplaçant le Décret du 16 février 2005 sur le processus d'Élaboration et d'Exécution des lois de finances",
        "date": "2016-05-04",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/621/ff9/ea9/621ff9ea99351107048036.pdf",
    },
    {
        "id": "loi-2014-03-12",
        "title": "Loi du 12 Mars 2014 portant prévention et répression de la corruption",
        "date": "2014-03-12",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ed/a10/6220eda10c466188048338.pdf",
    },
    {
        "id": "loi-2009-06-12",
        "title": "Loi du 12 Juin 2009 fixant les règles générales relatives aux marchés publics et aux conventions de concession d'ouvrage de service public",
        "date": "2009-06-12",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ee/0ab/6220ee0ab9202931486005.pdf",
    },
    {
        "id": "loi-2002-12-18",
        "title": "Loi du 18 Décembre 2002 créant un organisme financier de gestion et d'entretien routier dénommé Fonds d'Entretien Routier (FER)",
        "date": "2002-12-18",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/118/b9b/622118b9bd15d605351044.pdf",
    },
    {
        "id": "loi-1996-08-20",
        "title": "Loi du 20 Août 1996 établissant des droits internes comme complément aux recettes communales",
        "date": "1996-08-20",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/119/0fe/6221190fee238794689378.pdf",
    },
    {
        "id": "loi-1996-06-18",
        "title": "Loi du 18 Juin 1996 créant un fonds de gestion et de développement des collectivités territoriales",
        "date": "1996-06-18",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/119/50b/62211950b22b6036258513.pdf",
    },
    {
        "id": "loi-1971-05-26",
        "title": "Loi du 26 Mai 1971 sur le fonds d'assistance sociale",
        "date": "1971-05-26",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/119/d9c/622119d9cc5ec956826389.pdf",
    },
    {
        "id": "loi-1966-09-16",
        "title": "Loi du 16 Septembre 1966 créant le fonds d'urgence",
        "date": "1966-09-16",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/11a/9fd/62211a9fdb647622854838.pdf",
    },
    # --- Decrees ---
    {
        "id": "decret-2023-01-20-fiscal",
        "title": "Décret du 20 janvier 2023 portant Code Fiscal",
        "date": "2023-01-20",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/64b/6f8/bdb/64b6f8bdb0581583070335.pdf",
    },
    {
        "id": "decret-2023-03-21-douanes",
        "title": "Décret du 21 mars 2023 portant Code des Douanes",
        "date": "2023-03-21",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/64b/6f9/9d7/64b6f99d71669581394408.pdf",
    },
    {
        "id": "decret-2016-01-06-mpce",
        "title": "Décret du 6 Janvier 2016 organisant le Ministère de la Planification et de la Coopération Externe",
        "date": "2016-01-06",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/003/f91/622003f9172ce164208742.pdf",
    },
    {
        "id": "decret-2016-01-06-amend",
        "title": "Décret du 6 Janvier 2016 Portant amendement du décret du 17 Mai 2005",
        "date": "2016-01-06",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fb/dd4/6220fbdd46b5a304807921.pdf",
    },
    {
        "id": "decret-2016-01-06-pip",
        "title": "Décret du 6 janvier 2016 établissant les procédures et les modalités pour la gestion du PIP",
        "date": "2016-01-06",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fc/4ed/6220fc4ed950f487791501.pdf",
    },
    {
        "id": "decret-2015-10-09-pension",
        "title": "Décret du 9 Octobre 2015 Modifiant celui du 18 Février 2011 (Pension Civile)",
        "date": "2015-10-09",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fc/989/6220fc98951f1364533445.pdf",
    },
    {
        "id": "decret-igf",
        "title": "Décret créant l'Inspection Générale des Finances au MEF",
        "date": None,
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fc/e33/6220fce332ab5242075778.pdf",
    },
    {
        "id": "decret-2005-11-23-cscca",
        "title": "Décret du 23 Novembre 2005 sur la Cour Supérieure des Comptes",
        "date": "2005-11-23",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fd/243/6220fd2436470601165280.pdf",
    },
    {
        "id": "decret-2005-09-29-impot",
        "title": "Décret du 29 Septembre 2005 Relatif à l'impôt sur le revenu",
        "date": "2005-09-29",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/115/104/622115104dc18361072714.pdf",
    },
    {
        "id": "decret-2005-05-17-fonction",
        "title": "Décret du 17 Mai 2005 Portant Révision du Statut Général de la Fonction Publique",
        "date": "2005-05-17",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/114/4fe/6221144fe8182128667875.pdf",
    },
    {
        "id": "decret-2005-05-17-admin",
        "title": "Décret du 17 Mai 2005 Portant Organisation de l'administration Centrale",
        "date": "2005-05-17",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/115/79b/62211579bc814535571340.pdf",
    },
    {
        "id": "decret-1987-09-28-dgi",
        "title": "Décret du 28 Septembre 1987 Modifiant les Structures de la Direction Générale des Impôts",
        "date": "1987-09-28",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/116/851/62211685195ca137615740.pdf",
    },
    {
        "id": "decret-1987-05-05-agd",
        "title": "Décret du 5 Mai 1987 Réorganisant l'Administration Générale des Douanes",
        "date": "1987-05-05",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/116/d32/622116d322117237032067.pdf",
    },
    {
        "id": "decret-1987-03-05-budget",
        "title": "Décret du 5 Mars 1987 réorganisant l'office du Budget",
        "date": "1987-03-05",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/117/304/622117304293f087337216.pdf",
    },
    # --- Arrêtés ---
    {
        "id": "arrete-2020-08-30-cloture",
        "title": "Arrêté du 30 août 2020 fixant la date de clôture anticipée des engagements de l'Exercice Fiscal 2019-2020",
        "date": "2020-08-30",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/621/ffb/0a0/621ffb0a00368408154393.pdf",
    },
    {
        "id": "arrete-2019-01-09-marches",
        "title": "Arrêté du 9 Janvier 2019 révisant celui du 30 Août 2017 sur les marchés intéressant la défense ou la sécurité nationale",
        "date": "2019-01-09",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ee/613/6220ee613b912828162880.pdf",
    },
    {
        "id": "arrete-2018-10-01-salaire",
        "title": "Arrêté du 1er Octobre 2018 fixant le salaire minimum",
        "date": "2018-10-01",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ee/a5a/6220eea5a5a37757058470.pdf",
    },
    {
        "id": "arrete-2018-02-22-vehicules",
        "title": "Arrêté du 22 février 2018 portant règlementation de la location de Véhicules au sein de l'Administration Publique",
        "date": "2018-02-22",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ee/eb1/6220eeeb19183209718773.pdf",
    },
    {
        "id": "arrete-2017-07-12-privileges",
        "title": "Arrêté du 12 Juillet 2017 réservant des privilèges et avantages aux Chefs d'état Élus",
        "date": "2017-07-12",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ef/2bc/6220ef2bc0ab0269402886.pdf",
    },
    {
        "id": "arrete-2017-03-29-train",
        "title": "Arrêté du 29 Mars 2017 relatif au Train de Vie de l'État",
        "date": "2017-03-29",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ef/8cd/6220ef8cd1f5b479036215.pdf",
    },
    {
        "id": "arrete-2017-03-23-subventions",
        "title": "Arrêté du 23 Mars 2017 Portant sur les subventions de l'administration publique",
        "date": "2017-03-23",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0ef/cac/6220efcac3391838012342.pdf",
    },
    {
        "id": "arrete-2016-01-06-pip",
        "title": "Arrêté du 6 Janvier 2016 fixant les modalités d'inscription d'un projet dans le programme d'investissement public",
        "date": "2016-01-06",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f0/364/6220f0364ef96036622418.pdf",
    },
    {
        "id": "arrete-2015-09-23-privileges",
        "title": "Arrêté du 23 Septembre 2015 relatif aux Privilèges accordés aux anciens Chefs d'État et de Gouvernement",
        "date": "2015-09-23",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f0/7db/6220f07dbfbb4065496933.pdf",
    },
    {
        "id": "arrete-2015-07-22-formation",
        "title": "Arrêté du 22 Juillet 2015 relatif à la formation et au perfectionnement des fonctionnaires",
        "date": "2015-07-22",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f0/bd6/6220f0bd6bc57835457331.pdf",
    },
    {
        "id": "arrete-2014-09-10-bourses",
        "title": "Arrêté du 10 septembre 2014 fixant la procédure d'octroi et de Gestion des Bourses d'études",
        "date": "2014-09-10",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f0/f13/6220f0f130135952116629.pdf",
    },
    {
        "id": "arrete-2013-04-02-deontologie",
        "title": "Arrêté du 2 Avril 2013 définissant la règle déontologique applicable aux agents de la fonction publique",
        "date": "2013-04-02",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f4/9b2/6220f49b21648853451698.pdf",
    },
    {
        "id": "arrete-2013-04-02-concours",
        "title": "Arrêté du 2 Avril 2013 fixant les procédures et les modalités d'organisation des concours de recrutement",
        "date": "2013-04-02",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f4/d6c/6220f4d6cc5cd583888116.pdf",
    },
    {
        "id": "arrete-2012-05-25-seuils",
        "title": "Arrêté du 25 Mai 2012 Fixant les seuils de Passation des Marchés Publics",
        "date": "2012-05-25",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0f5/771/6220f57716659819044607.pdf",
    },
    {
        "id": "arrete-2005-02-16-comptabilite",
        "title": "Arrêté du 16 février 2005 portant règlement Général de la Comptabilité Publique",
        "date": "2005-02-16",
        "pdf_url": f"{BASE_URL}/storage/app/uploads/public/622/0fb/21b/6220fb21b4d1a539025986.pdf",
    },
]


def curl_download(url: str, dest: str, max_attempts: int = 3) -> bool:
    """Download a file via curl."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '60',
                 '-H', 'User-Agent: Mozilla/5.0 (compatible; LegalDataHunter/1.0)',
                 '-o', dest, url],
                capture_output=True, text=True, timeout=70
            )
            if result.returncode == 0 and os.path.getsize(dest) > 100:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
        delay = min(5 * (2 ** attempt), 30)
        logger.warning(f"Download attempt {attempt + 1} failed for {url}")
        time.sleep(delay)
    return False


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF using pdfplumber, cleaning up CID artifacts."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Clean up CID artifacts from font encoding issues
                    text = re.sub(r'\(cid:\d+\)', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    parts.append(text.strip())
                try:
                    page.flush_cache(); page.get_textmap.cache_clear()
                except Exception:
                    pass
            return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"PDF extraction failed for {pdf_path}: {e}")
        return ""


def normalize(doc: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    """Normalize a document record."""
    if not text or len(text) < 50:
        return None
    return {
        "_id": f"ht-mef-{doc['id']}",
        "_source": SOURCE_ID,
        "_type": "legislation",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "title": doc["title"],
        "text": text,
        "date": doc["date"],
        "url": doc["pdf_url"],
        "pdf_url": doc["pdf_url"],
    }


def fetch_all(sample: bool = False) -> Iterator[Dict[str, Any]]:
    """Fetch all documents with full text from PDFs."""
    docs = DOCUMENTS[:15] if sample else DOCUMENTS
    count = 0

    for doc in docs:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            logger.info(f"Downloading: {doc['title'][:60]}")
            if not curl_download(doc["pdf_url"], tmp_path):
                logger.warning(f"Failed to download: {doc['pdf_url']}")
                continue

            text = extract_pdf_text(tmp_path)
            if not text or len(text) < 50:
                logger.warning(f"No text extracted for: {doc['title']}")
                continue

            record = normalize(doc, text)
            if record:
                count += 1
                logger.info(f"[{count}] {doc['title'][:60]} ({len(text)} chars)")
                yield record
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        time.sleep(2.0)

    logger.info(f"Total records: {count}")


def save_samples(records: List[Dict], sample_dir: Path):
    """Save sample records to JSON files."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        fname = re.sub(r'[^\w\-]', '_', r["_id"])[:80] + ".json"
        path = sample_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Saved {len(records)} samples to {sample_dir}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HT/MEF-Lois bootstrap")
    sub = parser.add_subparsers(dest="command")

    boot = sub.add_parser("bootstrap", help="Fetch legislation")
    boot.add_argument("--sample", action="store_true", help="Sample mode")
    boot.add_argument("--full", action="store_true", help="Full fetch")

    sub.add_parser("bootstrap-fast", help="Quick sample fetch")

    args = parser.parse_args()

    if args.command in ("bootstrap", "bootstrap-fast"):
        sample_dir = Path(__file__).parent / "sample"
        records = list(fetch_all(sample=True))
        if records:
            save_samples(records, sample_dir)
            print(f"SUCCESS: {len(records)} records with full text")
        else:
            print("ERROR: No records fetched")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
