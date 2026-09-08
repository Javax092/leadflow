from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from rapidfuzz.fuzz import ratio


INPUT_FILE = Path(
    "data/processed/manaus_dentistas_extracted.csv"
)

OUTPUT_FILE = Path(
    "data/processed/manaus_dentistas_verified.csv"
)


BAD_WEBSITE_DOMAINS = {
    "wanderlog.com",
    "acnur.org",
    "pmc.ncbi.nlm.nih.gov",
    "arquivosdeneuropsiquiatria.org",
    "rentechdigital.com",
    "helpmecovid.com",
    "ortosena.com.br",
    "moovitapp.com",
    "science.gov",
}


GENERIC_INSTAGRAMS = {
    "prefeiturademanaus",
    "banzeiromanaus.oficial",
    "trinitaclinica",
}


STOPWORDS = {
    "clinica",
    "clinica odontologica",
    "odontologica",
    "odontologico",
    "odontologia",
    "consultorio",
    "consultorio odontologico",
    "instituto",
    "dra",
    "dr",
    "de",
    "da",
    "do",
    "e",
    "em",
    "manaus",
}


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


def tokens(text: str) -> set[str]:
    return {
        token
        for token in normalize(text).split()
        if len(token) >= 3
        and token not in STOPWORDS
    }


def host(url: str) -> str:
    try:
        value = urlparse(
            url
        ).netloc.lower()

        if value.startswith("www."):
            value = value[4:]

        return value

    except Exception:
        return ""


def evidence_text(
    lead: dict[str, str],
) -> str:

    parts = []

    for key, value in lead.items():

        if (
            "_title" in key
            or "_snippet" in key
        ):
            parts.append(
                value or ""
            )

    return " ".join(parts)


def identity_score(
    lead: dict[str, str],
    candidate_text: str,
) -> tuple[int, list[str]]:

    score = 0
    reasons = []

    name = normalize(
        lead["name"]
    )

    candidate = normalize(
        candidate_text
    )

    similarity = ratio(
        name,
        candidate,
    )

    if similarity >= 85:
        score += 40
        reasons.append("nome_forte")

    elif similarity >= 60:
        score += 20
        reasons.append("nome_parcial")

    lead_tokens = tokens(
        lead["name"]
    )

    candidate_tokens = tokens(
        candidate_text
    )

    common = (
        lead_tokens
        & candidate_tokens
    )

    if len(common) >= 2:
        score += 25
        reasons.append("tokens_identidade")

    elif len(common) == 1:
        score += 10
        reasons.append("token_identidade")

    if "manaus" in candidate:
        score += 15
        reasons.append("manaus")

    neighbourhood = normalize(
        lead.get(
            "neighbourhood",
            ""
        )
    )

    if (
        neighbourhood
        and neighbourhood
        in candidate
    ):
        score += 10
        reasons.append("bairro")

    return min(
        score,
        100,
    ), reasons


def find_candidate_context(
    lead: dict[str, str],
    candidate: str,
) -> str:

    if not candidate:
        return ""

    candidate_normalized = normalize(
        candidate
    )

    pieces = []

    for key, value in lead.items():

        if not value:
            continue

        value_normalized = normalize(
            value
        )

        if (
            candidate_normalized
            and candidate_normalized
            in value_normalized
        ):
            pieces.append(
                value
            )

            prefix = key.rsplit(
                "_",
                1,
            )[0]

            for suffix in (
                "title",
                "url",
                "snippet",
            ):
                sibling = lead.get(
                    f"{prefix}_{suffix}",
                    ""
                )

                if sibling:
                    pieces.append(
                        sibling
                    )

    return " ".join(
        dict.fromkeys(pieces)
    )


def verify_phone(
    lead: dict[str, str],
) -> tuple[str, int, str]:

    candidate = lead.get(
        "phone_candidate",
        ""
    )

    if not candidate:
        return "", 0, "NONE"

    evidence = int(
        lead.get(
            "phone_evidence",
            "0",
        )
        or 0
    )

    osm_phone = re.sub(
        r"\D",
        "",
        lead.get(
            "phone",
            "",
        ),
    )

    candidate_digits = re.sub(
        r"\D",
        "",
        candidate,
    )

    if (
        osm_phone
        and candidate_digits
        and osm_phone[-8:]
        == candidate_digits[-8:]
    ):
        return (
            candidate,
            100,
            "OSM_MATCH",
        )

    context = find_candidate_context(
        lead,
        candidate,
    )

    identity, _ = identity_score(
        lead,
        context,
    )

    score = identity

    if evidence >= 2:
        score += 30

    elif evidence == 1:
        score += 10

    score = min(
        score,
        100,
    )

    if score >= 75:
        status = "VERIFIED"

    elif score >= 50:
        status = "REVIEW"

    else:
        status = "REJECTED"

    return (
        candidate,
        score,
        status,
    )


def verify_website(
    lead: dict[str, str],
) -> tuple[str, int, str]:

    candidate = lead.get(
        "website_candidate",
        ""
    )

    if not candidate:
        return "", 0, "NONE"

    domain = host(
        candidate
    )

    if any(
        domain == bad
        or domain.endswith(
            "." + bad
        )
        for bad in BAD_WEBSITE_DOMAINS
    ):
        return (
            candidate,
            0,
            "REJECTED",
        )

    context = find_candidate_context(
        lead,
        candidate,
    )

    identity, reasons = identity_score(
        lead,
        context,
    )

    business_tokens = tokens(
        lead["name"]
    )

    domain_compact = normalize(
        domain.split(".")[0]
    ).replace(
        " ",
        "",
    )

    domain_matches = sum(
        token in domain_compact
        for token in business_tokens
    )

    score = identity

    if domain_matches >= 2:
        score += 40

    elif domain_matches == 1:
        score += 25

    score = min(
        score,
        100,
    )

    if score >= 70:
        status = "VERIFIED"

    elif score >= 45:
        status = "REVIEW"

    else:
        status = "REJECTED"

    return (
        candidate,
        score,
        status,
    )


def verify_instagram(
    lead: dict[str, str],
) -> tuple[str, int, str]:

    candidate = lead.get(
        "instagram_candidate",
        ""
    )

    if not candidate:
        return "", 0, "NONE"

    if (
        candidate.lower()
        in GENERIC_INSTAGRAMS
    ):
        return (
            candidate,
            0,
            "REJECTED",
        )

    context = find_candidate_context(
        lead,
        candidate,
    )

    identity, _ = identity_score(
        lead,
        context,
    )

    handle = normalize(
        candidate
    ).replace(
        " ",
        "",
    )

    business_tokens = tokens(
        lead["name"]
    )

    matches = sum(
        token in handle
        for token in business_tokens
    )

    score = identity

    if matches >= 2:
        score += 35

    elif matches == 1:
        score += 20

    score = min(
        score,
        100,
    )

    if score >= 70:
        status = "VERIFIED"

    elif score >= 45:
        status = "REVIEW"

    else:
        status = "REJECTED"

    return (
        candidate,
        score,
        status,
    )


def verify_email(
    lead: dict[str, str],
) -> tuple[str, int, str]:

    candidate = lead.get(
        "email_candidate",
        ""
    )

    if not candidate:
        return "", 0, "NONE"

    context = find_candidate_context(
        lead,
        candidate,
    )

    identity, _ = identity_score(
        lead,
        context,
    )

    if identity >= 70:
        status = "VERIFIED"

    elif identity >= 45:
        status = "REVIEW"

    else:
        status = "REJECTED"

    return (
        candidate,
        identity,
        status,
    )


def verify_lead(
    lead: dict[str, str],
) -> dict[str, str]:

    output = lead.copy()

    phone, phone_score, phone_status = (
        verify_phone(
            lead
        )
    )

    website, website_score, website_status = (
        verify_website(
            lead
        )
    )

    instagram, instagram_score, instagram_status = (
        verify_instagram(
            lead
        )
    )

    email, email_score, email_status = (
        verify_email(
            lead
        )
    )

    output[
        "verified_phone"
    ] = (
        phone
        if phone_status
        in {"VERIFIED", "OSM_MATCH"}
        else ""
    )

    output[
        "phone_verification_score"
    ] = str(
        phone_score
    )

    output[
        "phone_verification_status"
    ] = phone_status

    output[
        "verified_website"
    ] = (
        website
        if website_status == "VERIFIED"
        else ""
    )

    output[
        "website_verification_score"
    ] = str(
        website_score
    )

    output[
        "website_verification_status"
    ] = website_status

    output[
        "verified_instagram"
    ] = (
        instagram
        if instagram_status == "VERIFIED"
        else ""
    )

    output[
        "instagram_verification_score"
    ] = str(
        instagram_score
    )

    output[
        "instagram_verification_status"
    ] = instagram_status

    output[
        "verified_email"
    ] = (
        email
        if email_status == "VERIFIED"
        else ""
    )

    output[
        "email_verification_score"
    ] = str(
        email_score
    )

    output[
        "email_verification_status"
    ] = email_status

    return output


def main() -> None:

    with INPUT_FILE.open(
        encoding="utf-8",
    ) as file:

        leads = list(
            csv.DictReader(file)
        )

    verified = [
        verify_lead(
            lead
        )
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
            fieldnames=verified[0].keys(),
        )

        writer.writeheader()
        writer.writerows(
            verified
        )

    print()
    print("=" * 92)
    print(
        "LEADFLOW ZERO — ENTITY VERIFICATION"
    )
    print("=" * 92)

    for lead in verified:

        print()
        print(
            lead["name"]
        )

        print(
            "  PHONE     ",
            lead["phone_candidate"]
            or "N/D",
            "→",
            lead[
                "phone_verification_status"
            ],
            lead[
                "phone_verification_score"
            ],
        )

        print(
            "  WEBSITE   ",
            lead["website_candidate"]
            or "N/D",
            "→",
            lead[
                "website_verification_status"
            ],
            lead[
                "website_verification_score"
            ],
        )

        print(
            "  INSTAGRAM ",
            lead["instagram_candidate"]
            or "N/D",
            "→",
            lead[
                "instagram_verification_status"
            ],
            lead[
                "instagram_verification_score"
            ],
        )

        print(
            "  EMAIL     ",
            lead["email_candidate"]
            or "N/D",
            "→",
            lead[
                "email_verification_status"
            ],
            lead[
                "email_verification_score"
            ],
        )

    print()
    print(
        f"Arquivo salvo: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
