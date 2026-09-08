from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


INPUT_FILE = Path(
    "data/processed/manaus_dentistas_enriched_v2.csv"
)

OUTPUT_FILE = Path(
    "data/processed/manaus_dentistas_extracted.csv"
)


DIRECTORY_DOMAINS = {
    "dentmap.com.br",
    "saudecidade.com",
    "applocal.com.br",
    "eguias.net",
    "guiaja.net",
    "guiafacil.com",
    "todosnegocios.com",
    "br.todosnegocios.com",
    "solutudo.com.br",
    "guiabare.com.br",
    "near-place.com",
    "br.near-place.com",
    "locaisdobrasil.com.br",
    "hospitaleclinicas.com.br",
    "mapy.com",
    "zaubee.com",
    "moovitapp.com",
    "melhorguiabrasil.com.br",
    "qualotelefone.com",
    "dentistas.net.br",
    "assistenciamedica.com.br",
    "agendarconsulta.com",
    "guia.agendarconsulta.com",
    "avaliacoesbrasil.com",
}


SOCIAL_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "linkedin.com",
}


IGNORED_DOMAINS = {
    "youtube.com",
    "wikipedia.org",
    "google.com",
}


PHONE_PATTERN = re.compile(
    r"""
    (?:
        (?:\+?55[\s.-]?)?
        (?:\(?\d{2}\)?[\s.-]?)?
        (?:9?\d{4})[\s.-]?\d{4}
    )
    """,
    re.VERBOSE,
)


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+"
    r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


def normalize(text: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        text or "",
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def host(url: str) -> str:
    try:
        hostname = (
            urlparse(url).netloc
            .lower()
            .split(":")[0]
        )

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:
        return ""


def root_domain_matches(
    candidate: str,
    domains: set[str],
) -> bool:

    return any(
        candidate == domain
        or candidate.endswith("." + domain)
        for domain in domains
    )


def clean_phone(value: str) -> str:
    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]

    return digits


def valid_phone(value: str) -> bool:
    digits = clean_phone(value)

    return len(digits) in {10, 11}


def extract_phones(text: str) -> list[str]:
    phones = []

    for match in PHONE_PATTERN.findall(
        text or ""
    ):
        phone = clean_phone(match)

        if valid_phone(phone):
            phones.append(phone)

    return phones


def extract_emails(text: str) -> list[str]:
    return EMAIL_PATTERN.findall(
        text or ""
    )


def instagram_handle(url: str) -> str:
    if "instagram.com" not in host(url):
        return ""

    path = urlparse(url).path.strip("/")

    if not path:
        return ""

    first = path.split("/")[0]

    blocked = {
        "p",
        "reel",
        "reels",
        "explore",
        "stories",
    }

    if first.lower() in blocked:
        return ""

    return first


def candidate_website(url: str) -> str:
    domain = host(url)

    if not domain:
        return ""

    if root_domain_matches(
        domain,
        SOCIAL_DOMAINS,
    ):
        return ""

    if root_domain_matches(
        domain,
        DIRECTORY_DOMAINS,
    ):
        return ""

    if root_domain_matches(
        domain,
        IGNORED_DOMAINS,
    ):
        return ""

    return url


def iter_evidence(
    lead: dict[str, str],
):
    for search_type in (
        "identity",
        "contact",
        "digital",
    ):
        for position in range(1, 4):

            prefix = (
                f"{search_type}_result_"
                f"{position}"
            )

            title = lead.get(
                f"{prefix}_title",
                "",
            )

            url = lead.get(
                f"{prefix}_url",
                "",
            )

            snippet = lead.get(
                f"{prefix}_snippet",
                "",
            )

            if not (
                title
                or url
                or snippet
            ):
                continue

            yield {
                "search_type": search_type,
                "position": position,
                "title": title,
                "url": url,
                "snippet": snippet,
                "text": (
                    f"{title} {snippet}"
                ),
            }


def extract_lead(
    lead: dict[str, str],
) -> dict[str, str]:

    output = lead.copy()

    phone_counter = Counter()
    email_counter = Counter()
    instagram_counter = Counter()
    website_counter = Counter()

    # OSM é uma evidência própria.
    osm_phone = clean_phone(
        lead.get("phone", "")
    )

    if valid_phone(osm_phone):
        phone_counter[osm_phone] += 2

    osm_email = (
        lead.get("email", "")
        .strip()
        .lower()
    )

    if osm_email:
        email_counter[osm_email] += 2

    osm_instagram = (
        lead.get("instagram", "")
        .strip()
    )

    if osm_instagram:
        instagram_counter[
            osm_instagram
        ] += 2

    osm_website = (
        lead.get("website", "")
        .strip()
    )

    if osm_website:
        website_counter[
            osm_website
        ] += 2

    # Evidências provenientes da busca.
    for evidence in iter_evidence(lead):

        text = evidence["text"]
        url = evidence["url"]

        for phone in extract_phones(text):
            phone_counter[phone] += 1

        for email in extract_emails(text):
            email_counter[
                email.lower()
            ] += 1

        handle = instagram_handle(url)

        if handle:
            instagram_counter[
                handle
            ] += 1

        website = candidate_website(url)

        if website:
            website_counter[
                website
            ] += 1

    best_phone = (
        phone_counter.most_common(1)
    )

    best_email = (
        email_counter.most_common(1)
    )

    best_instagram = (
        instagram_counter.most_common(1)
    )

    best_website = (
        website_counter.most_common(1)
    )

    output["phone_candidate"] = (
        best_phone[0][0]
        if best_phone
        else ""
    )

    output["phone_evidence"] = (
        str(best_phone[0][1])
        if best_phone
        else "0"
    )

    output["email_candidate"] = (
        best_email[0][0]
        if best_email
        else ""
    )

    output["email_evidence"] = (
        str(best_email[0][1])
        if best_email
        else "0"
    )

    output["instagram_candidate"] = (
        best_instagram[0][0]
        if best_instagram
        else ""
    )

    output["instagram_evidence"] = (
        str(best_instagram[0][1])
        if best_instagram
        else "0"
    )

    output["website_candidate"] = (
        best_website[0][0]
        if best_website
        else ""
    )

    output["website_evidence"] = (
        str(best_website[0][1])
        if best_website
        else "0"
    )

    return output


def confidence(
    evidence: str,
) -> str:

    count = int(evidence or 0)

    if count >= 2:
        return "HIGH"

    if count == 1:
        return "REVIEW"

    return "NONE"


def main() -> None:

    with INPUT_FILE.open(
        encoding="utf-8",
    ) as file:

        leads = list(
            csv.DictReader(file)
        )

    extracted = [
        extract_lead(lead)
        for lead in leads
    ]

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
            fieldnames=extracted[0].keys(),
        )

        writer.writeheader()
        writer.writerows(extracted)

    print()
    print("=" * 88)
    print(
        "LEADFLOW ZERO — EXTRACTOR REPORT"
    )
    print("=" * 88)

    for lead in extracted:

        print()
        print(lead["name"])

        print(
            "  Telefone :",
            lead["phone_candidate"]
            or "N/D",
            f"[{confidence(lead['phone_evidence'])}]",
        )

        print(
            "  Instagram:",
            lead["instagram_candidate"]
            or "N/D",
            f"[{confidence(lead['instagram_evidence'])}]",
        )

        print(
            "  Website  :",
            lead["website_candidate"]
            or "N/D",
            f"[{confidence(lead['website_evidence'])}]",
        )

        print(
            "  Email    :",
            lead["email_candidate"]
            or "N/D",
            f"[{confidence(lead['email_evidence'])}]",
        )

    print()
    print(
        f"Arquivo salvo: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
