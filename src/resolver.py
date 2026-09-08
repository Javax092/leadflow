from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from rapidfuzz.fuzz import ratio


INPUT_FILE = Path("data/processed/manaus_dentistas_enriched.csv")
OUTPUT_FILE = Path("data/processed/manaus_dentistas_resolved.csv")


SOCIAL_DOMAINS = {
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "linkedin.com",
    "www.linkedin.com",
}

DIRECTORY_DOMAINS = {
    "locaisdobrasil.com.br",
    "www.locaisdobrasil.com.br",
    "paginaamarela.com.br",
    "www.paginaamarela.com.br",
    "econodata.com.br",
    "www.econodata.com.br",
    "oggo.com.br",
    "www.oggo.com.br",
    "eguias.net",
    "www.eguias.net",
    "guiaja.net",
    "www.guiaja.net",
    "dentmap.com.br",
    "www.dentmap.com.br",
}


def normalize(text: str) -> str:
    text = text or ""

    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def name_similarity(name: str, result_title: str) -> float:
    return ratio(
        normalize(name),
        normalize(result_title),
    )


def evaluate_result(
    lead: dict[str, str],
    title: str,
    url: str,
    snippet: str,
) -> dict:
    combined = f"{title} {snippet}"

    normalized_combined = normalize(combined)

    score = 0
    reasons = []

    similarity = name_similarity(
        lead["name"],
        title,
    )

    # Nome
        # Domínio contém identidade do negócio
    host = domain(url)

    host_normalized = normalize(
        host.replace("www.", "").split(".")[0]
    ).replace(" ", "")

    name_tokens = [
        token
        for token in normalize(lead["name"]).split()
        if len(token) >= 4
    ]

    domain_matches = sum(
        token in host_normalized
        for token in name_tokens
    )

    if domain_matches >= 2:
        score += 20
        reasons.append("dominio_forte")

    elif domain_matches == 1:
        score += 10
        reasons.append("dominio_parcial")
    if similarity >= 85:
        score += 35
        reasons.append("nome_forte")

    elif similarity >= 65:
        score += 20
        reasons.append("nome_parcial")

    # Cidade
    if "manaus" in normalized_combined:
        score += 20
        reasons.append("manaus")

    # Estado
    if (
        "amazonas" in normalized_combined
        or re.search(r"\bam\b", normalized_combined)
    ):
        score += 5
        reasons.append("amazonas")

    # Bairro
    neighbourhood = normalize(
        lead.get("neighbourhood", "")
    )

    if (
        neighbourhood
        and neighbourhood in normalized_combined
    ):
        score += 15
        reasons.append("bairro")

    # Rua
    address = normalize(
        lead.get("address", "")
    )

    address_words = [
        word
        for word in address.split()
        if len(word) >= 4
    ]

    matches = sum(
        word in normalized_combined
        for word in address_words
    )

    if address_words and matches >= max(1, len(address_words) // 2):
        score += 15
        reasons.append("endereco")

    # Telefone
    lead_phone = digits(
        lead.get("phone", "")
    )

    result_phone = digits(combined)

    if (
        lead_phone
        and len(lead_phone) >= 8
        and lead_phone[-8:] in result_phone
    ):
        score += 25
        reasons.append("telefone")

    # Penalidades geográficas explícitas
    other_cities = [
        "belem",
        "sao paulo",
        "rio de janeiro",
        "brasilia",
        "fortaleza",
        "recife",
    ]

    for city in other_cities:
        if city in normalized_combined and "manaus" not in normalized_combined:
            score -= 40
            reasons.append(f"outra_cidade:{city}")

    score = max(0, min(score, 100))

    return {
        "score": score,
        "similarity": round(similarity, 1),
        "reasons": reasons,
        "domain": domain(url),
    }


def classify_source(url: str) -> str:
    host = domain(url)

    if host in SOCIAL_DOMAINS:
        return "social"

    if host in DIRECTORY_DOMAINS:
        return "directory"

    return "website_candidate"


def resolve_lead(lead: dict[str, str]) -> dict[str, str]:
    candidates = []

    for position in range(1, 4):
        title = lead.get(
            f"result_{position}_title",
            "",
        )

        url = lead.get(
            f"result_{position}_url",
            "",
        )

        snippet = lead.get(
            f"result_{position}_snippet",
            "",
        )

        if not url:
            continue

        evaluation = evaluate_result(
            lead,
            title,
            url,
            snippet,
        )

        candidates.append(
            {
                "position": position,
                "title": title,
                "url": url,
                "snippet": snippet,
                **evaluation,
            }
        )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    output = lead.copy()

    if not candidates:
        output["confidence_score"] = "0"
        output["confidence_status"] = "UNRESOLVED"
        return output

    best = candidates[0]

    score = best["score"]

    if score >= 75:
        status = "HIGH"
    elif score >= 50:
        status = "MEDIUM"
    else:
        status = "LOW"

    output["confidence_score"] = str(score)
    output["confidence_status"] = status

    output["best_result_url"] = best["url"]
    output["best_result_title"] = best["title"]

    output["best_result_type"] = classify_source(
        best["url"]
    )

    output["match_reasons"] = ",".join(
        best["reasons"]
    )

    output["name_similarity"] = str(
        best["similarity"]
    )

    return output


def main() -> None:
    with INPUT_FILE.open(
        encoding="utf-8",
    ) as file:
        leads = list(csv.DictReader(file))

    resolved = [
        resolve_lead(lead)
        for lead in leads
    ]

    resolved.sort(
        key=lambda lead: int(
            lead.get("confidence_score", 0)
        ),
        reverse=True,
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=resolved[0].keys(),
        )

        writer.writeheader()
        writer.writerows(resolved)

    print()
    print("=" * 80)
    print("LEADFLOW ZERO — CONFIDENCE RESOLVER")
    print("=" * 80)

    for lead in resolved:
        print()
        print(
            f"{lead['confidence_score']:>3} "
            f"[{lead['confidence_status']}] "
            f"{lead['name']}"
        )

        print(
            f"    {lead.get('best_result_type', '')} | "
            f"{lead.get('best_result_url', '')}"
        )

        print(
            f"    evidências: "
            f"{lead.get('match_reasons', '')}"
        )

    print()
    print(f"Arquivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
