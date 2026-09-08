from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.discovery import slugify
from src.niches import NicheConfig, normalize, resolve_niche
from src.verifier_v2 import business_tokens


PROCESSED_DIR = Path("data/processed")

CONFIRMED_PHONE_STATUSES = {
    "VERIFIED",
    "OSM_MATCH",
}

WHATSAPP_STATUSES = {
    "VERIFIED",
    "REVIEW",
    "NOT_FOUND",
    "REJECTED",
    "NONE",
}

PHONE_RE = re.compile(
    r"(?:\+?55[\s().-]*)?(?:\(?\d{2}\)?[\s().-]*)?(?:9?\d{4})[\s.-]?\d{4}"
)

WHATSAPP_LINK_RE = re.compile(
    r"https?://(?:wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)/[^\s\"'<>]+",
    re.I,
)

COMMERCIAL_TERMS = (
    "fale conosco",
    "atendimento",
    "orcamento",
    "orçamento",
    "contato",
    "vendas",
    "clique",
    "chame",
    "agende",
    "agendar",
    "orcamento pelo whatsapp",
    "orçamento pelo whatsapp",
    "fale pelo whatsapp",
    "atendimento whatsapp",
    "contato whatsapp",
    "vendas whatsapp",
)


def build_input_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return PROCESSED_DIR / (
        f"{slugify(city)}_{niche.key}_verified_v2.csv"
    )


def build_output_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return PROCESSED_DIR / (
        f"{slugify(city)}_{niche.key}_whatsapp.csv"
    )


def br_phone_digits(
    value: str,
) -> str:
    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if (
        digits.startswith("55")
        and len(digits) in {12, 13}
    ):
        digits = digits[2:]

    return digits if len(digits) in {10, 11} else ""


def br_phone_international(
    value: str,
) -> str:
    digits = br_phone_digits(
        value
    )

    return f"55{digits}" if digits else ""


def phone_variants(
    value: str,
) -> set[str]:
    national = br_phone_digits(
        value
    )

    if not national:
        return set()

    return {
        national,
        f"55{national}",
    }


def phones_in_text(
    text: str,
) -> set[str]:
    phones = set()

    for match in PHONE_RE.findall(
        text or ""
    ):
        phone = br_phone_digits(
            match
        )

        if phone:
            phones.add(
                phone
            )

    return phones


def phone_from_whatsapp_link(
    url: str,
) -> str:
    parsed = urlparse(
        url
    )

    if parsed.netloc.lower().endswith("wa.me"):
        return br_phone_digits(
            parsed.path
        )

    query = parse_qs(
        parsed.query
    )

    for value in query.get(
        "phone",
        [],
    ):
        phone = br_phone_digits(
            value
        )

        if phone:
            return phone

    return br_phone_digits(
        unquote(url)
    )


def evidence_fields(
    row: dict[str, str],
) -> list[tuple[str, str, str]]:
    fields = []

    for search_type in (
        "identity",
        "contact",
        "digital",
    ):
        for position in range(1, 4):
            prefix = f"{search_type}_result_{position}"
            source = (
                row.get(
                    f"{prefix}_url",
                    "",
                )
                or ""
            )
            text = " ".join(
                (
                    row.get(
                        f"{prefix}_title",
                        "",
                    )
                    or "",
                    source,
                    row.get(
                        f"{prefix}_snippet",
                        "",
                    )
                    or "",
                )
            )

            if text.strip():
                fields.append(
                    (
                        f"{search_type}:{position}",
                        source,
                        text,
                    )
                )

    return fields


def source_host(
    url: str,
) -> str:
    try:
        host = urlparse(
            url
        ).netloc.lower()

        return host[4:] if host.startswith("www.") else host

    except Exception:
        return ""


def instagram_handle(
    value: str,
) -> str:
    parsed = urlparse(
        value or ""
    )

    if "instagram.com" in parsed.netloc.lower():
        return parsed.path.strip("/").split("/")[0].lower()

    return (
        value.lower()
        .replace("@", "")
        .strip("/")
        .strip()
    )


def is_verified_status(
    value: str,
) -> bool:
    return (
        value or ""
    ).strip().upper() in CONFIRMED_PHONE_STATUSES


def source_strength(
    row: dict[str, str],
    source: str,
) -> str:
    host = source_host(
        source
    )

    website = row.get(
        "website_candidate_v2",
        "",
    )
    website_host = source_host(
        website
    )

    if (
        website_host
        and is_verified_status(
            row.get(
                "website_verification_status_v2",
                "",
            )
        )
        and host == website_host
    ):
        return "FIRST_PARTY"

    if (
        host.endswith("instagram.com")
        and is_verified_status(
            row.get(
                "instagram_verification_status_v2",
                "",
            )
        )
        and instagram_handle(source)
        == instagram_handle(
            row.get(
                "instagram_candidate_v2",
                "",
            )
        )
    ):
        return "FIRST_PARTY"

    return "SECONDARY"


def identity_match(
    row: dict[str, str],
    text: str,
    niche: NicheConfig,
    city: str,
) -> bool:
    normalized = normalize(
        text
    )

    name_tokens = business_tokens(
        row.get(
            "name",
            "",
        ),
        niche,
    ) - {
        "casa",
    }

    strong_name = bool(
        name_tokens
    ) and any(
        token in normalized
        for token in name_tokens
    )

    has_city = normalize(
        city
    ) in normalized

    has_context = any(
        normalize(term) in normalized
        for term in niche.context_terms
    )

    return strong_name and (
        has_city
        or has_context
    )


def resolve_row(
    row: dict[str, str],
    city: str,
    niche: NicheConfig,
) -> dict[str, str]:
    phone_status = (
        row.get(
            "phone_verification_status_v2",
            "NONE",
        )
        or "NONE"
    ).strip().upper()

    phone = br_phone_digits(
        row.get(
            "phone_candidate_v2",
            "",
        )
    )

    result = {
        "whatsapp_candidate": "",
        "whatsapp_status": "NONE",
        "whatsapp_confidence": "0",
        "whatsapp_evidence_count": "0",
        "whatsapp_source_count": "0",
        "whatsapp_sources": "",
        "commercial_contact_status": "NONE",
        "commercial_contact_confidence": "0",
        "commercial_contact_reasons": "",
    }

    if (
        not phone
        or phone_status not in CONFIRMED_PHONE_STATUSES
    ):
        return result

    result["whatsapp_candidate"] = br_phone_international(
        phone
    )
    result["whatsapp_status"] = "NOT_FOUND"
    result["commercial_contact_status"] = "NOT_FOUND"

    whatsapp_first_party = 0
    whatsapp_secondary_sources: set[str] = set()
    commercial_first_party = 0
    commercial_secondary_sources: set[str] = set()
    negative = 0
    reasons: list[str] = []
    sources: set[str] = set()

    for label, source, text in evidence_fields(
        row
    ):
        normalized = normalize(
            text
        )
        host = source_host(
            source
        )
        has_identity = identity_match(
            row,
            text,
            niche,
            city,
        )
        has_whatsapp_word = "whatsapp" in normalized or "zap" in normalized
        has_commercial_word = any(
            normalize(term) in normalized
            for term in COMMERCIAL_TERMS
        )
        text_phones = phones_in_text(
            text
        )
        same_phone = phone in text_phones
        other_phones = text_phones - {phone}

        link_phones = {
            phone_from_whatsapp_link(
                link
            )
            for link in WHATSAPP_LINK_RE.findall(
                text
            )
        }
        link_phones.discard("")

        link_same_phone = phone in link_phones
        link_other_phone = bool(
            link_phones
            and not link_same_phone
        )
        strength = source_strength(
            row,
            source,
        )

        if link_other_phone:
            negative += 1
            reasons.append(
                f"{label}:whatsapp_numero_divergente"
            )
            continue

        if (
            has_whatsapp_word
            and other_phones
            and not link_same_phone
        ):
            negative += 1
            reasons.append(
                f"{label}:whatsapp_numero_divergente"
            )
            continue

        explicit_whatsapp = (
            link_same_phone
            or (
                same_phone
                and has_whatsapp_word
                and not other_phones
            )
        )

        if not explicit_whatsapp:
            continue

        source_key = host or label

        if not has_identity:
            reasons.append(
                f"{label}:whatsapp_sem_identidade_forte"
            )
            continue

        sources.add(
            source_key
        )
        reasons.append(
            f"{label}:whatsapp_publico_{strength.lower()}"
        )

        if strength == "FIRST_PARTY":
            whatsapp_first_party += 1
        else:
            whatsapp_secondary_sources.add(
                source_key
            )

        if has_commercial_word:
            reasons.append(
                f"{label}:contato_comercial_{strength.lower()}"
            )

            if strength == "FIRST_PARTY":
                commercial_first_party += 1
            else:
                commercial_secondary_sources.add(
                    source_key
                )

    evidence = (
        whatsapp_first_party
        + len(
            whatsapp_secondary_sources
        )
    )
    commercial = (
        commercial_first_party
        + len(
            commercial_secondary_sources
        )
    )

    confidence = min(
        100,
        whatsapp_first_party * 70
        + len(whatsapp_secondary_sources) * 35
        + len(sources) * 15
        + commercial_first_party * 20
        + len(commercial_secondary_sources) * 10
        - negative * 30,
    )
    confidence = max(
        0,
        confidence,
    )

    result["whatsapp_evidence_count"] = str(
        evidence
    )
    result["whatsapp_source_count"] = str(
        len(sources)
    )
    result["whatsapp_sources"] = "|".join(
        sorted(sources)
    )
    result["whatsapp_confidence"] = str(
        confidence
    )
    result["commercial_contact_confidence"] = str(
        min(
            100,
            commercial_first_party * 75
            + len(commercial_secondary_sources) * 35
            + len(sources) * 5,
        )
    )
    result["commercial_contact_reasons"] = ",".join(
        reasons
    )

    whatsapp_verified = (
        whatsapp_first_party >= 1
        or (
            len(whatsapp_secondary_sources) >= 2
            and not negative
        )
    )
    commercial_verified = (
        commercial_first_party >= 1
        or (
            len(commercial_secondary_sources) >= 2
            and not negative
        )
    )

    # Evidência conflitante bloqueia validação baseada só em fontes fracas.
    if negative and not evidence:
        result["whatsapp_status"] = "REJECTED"
        result["commercial_contact_status"] = "REJECTED"

    elif whatsapp_verified:
        result["whatsapp_status"] = "VERIFIED"
        result["commercial_contact_status"] = (
            "VERIFIED" if commercial_verified else "REVIEW"
        )

    elif evidence:
        result["whatsapp_status"] = "REVIEW"
        result["commercial_contact_status"] = "REVIEW"

    return result


def resolve_whatsapp(
    city: str,
    niche_name: str,
    verbose: bool = True,
) -> tuple[list[dict[str, str]], Path]:
    niche = resolve_niche(
        niche_name
    )
    input_file = build_input_file(
        city,
        niche,
    )
    output_file = build_output_file(
        city,
        niche,
    )

    if not input_file.exists():
        raise FileNotFoundError(
            f"Verifier não encontrado: {input_file}"
        )

    with input_file.open(
        encoding="utf-8",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    output_rows = []

    for row in rows:
        output_rows.append(
            {
                **row,
                **resolve_row(
                    row,
                    city,
                    niche,
                ),
            }
        )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_rows:
        with output_file.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=output_rows[0].keys(),
            )
            writer.writeheader()
            writer.writerows(
                output_rows
            )

    if verbose:
        verified = sum(
            row["whatsapp_status"] == "VERIFIED"
            for row in output_rows
        )
        commercial = sum(
            row["commercial_contact_status"] == "VERIFIED"
            for row in output_rows
        )

        print()
        print("=" * 84)
        print(
            "LEADFLOW ZERO — WHATSAPP RESOLVER"
        )
        print("=" * 84)
        print(
            f"Leads analisados     : {len(output_rows)}"
        )
        print(
            f"WhatsApp VERIFIED    : {verified}"
        )
        print(
            f"Comercial VERIFIED   : {commercial}"
        )
        print(
            f"Arquivo salvo        : {output_file}"
        )

    return output_rows, output_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="whatsapp",
        description=(
            "LeadFlow Zero — validação pública "
            "de WhatsApp comercial."
        ),
    )
    parser.add_argument(
        "--city",
        default="Manaus",
    )
    parser.add_argument(
        "--niche",
        default="dentistas",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        resolve_whatsapp(
            city=args.city,
            niche_name=args.niche,
            verbose=not args.quiet,
        )

    except (
        ValueError,
        FileNotFoundError,
    ) as error:
        raise SystemExit(
            f"Erro: {error}"
        )


if __name__ == "__main__":
    main()
