from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.discovery import slugify
from src.niches import NicheConfig, resolve_niche


PROCESSED_DIR = Path("data/processed")


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


# Diretórios, agregadores e fontes de terceiros.
# Eles podem fornecer evidência sobre uma empresa,
# mas NÃO devem virar "website próprio".
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
    "avaliacoesbrasil.com.br",
    "avaliacoesbrasil.com",
    "guiamapa.com",
    "magicpin.com",
    "yelp.com",
    "m.yelp.com",
    "wanderboat.ai",
    "infoisinfo-br.com",
    "starngage.com",
    "rocketreach.co",
    "aeroleads.com",
    "anuncioemfoco.com.br",
}


SOCIAL_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
}


def build_input_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return PROCESSED_DIR / (
        f"{slugify(city)}_"
        f"{niche.key}_enriched_v2.csv"
    )


def build_output_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return PROCESSED_DIR / (
        f"{slugify(city)}_"
        f"{niche.key}_candidates.csv"
    )


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


def domain_matches(
    candidate: str,
    domains: set[str],
) -> bool:
    return any(
        candidate == domain
        or candidate.endswith(
            "." + domain
        )
        for domain in domains
    )


def clean_phone(
    value: str,
) -> str:
    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if (
        digits.startswith("55")
        and len(digits) >= 12
    ):
        digits = digits[2:]

    return digits


def valid_phone(
    value: str,
) -> bool:
    return len(
        clean_phone(value)
    ) in {
        10,
        11,
    }


def instagram_handle(
    url: str,
) -> str:
    if not domain_matches(
        host(url),
        {"instagram.com"},
    ):
        return ""

    path = urlparse(
        url
    ).path.strip("/")

    if not path:
        return ""

    first = path.split(
        "/"
    )[0]

    blocked = {
        "p",
        "reel",
        "reels",
        "explore",
        "stories",
        "popular",
    }

    if first.lower() in blocked:
        return ""

    return first


def website_candidate(
    url: str,
) -> str:
    domain = host(
        url
    )

    if not domain:
        return ""

    if domain_matches(
        domain,
        DIRECTORY_DOMAINS,
    ):
        return ""

    if domain_matches(
        domain,
        SOCIAL_DOMAINS,
    ):
        return ""

    return url


def add_candidate(
    pool: Any,
    kind: str,
    value: str,
    source: str,
    search_type: str,
    position: int,
    title: str,
    snippet: str,
) -> None:
    if not value:
        return

    key = (
        kind,
        value.lower(),
    )

    pool[key]["type"] = kind
    pool[key]["value"] = value

    pool[key]["evidence"].append(
        {
            "source": source,
            "search_type": search_type,
            "position": position,
            "title": title,
            "snippet": snippet,
        }
    )


def extract_candidates(
    lead: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Candidate generator.

    Importante:
    candidato != fato verificado.

    Esta função deve ter recall relativamente alto.
    A decisão VERIFIED / REVIEW / REJECTED pertence
    ao verifier.
    """

    pool = defaultdict(
        lambda: {
            "type": "",
            "value": "",
            "evidence": [],
        }
    )

    # ========================================================
    # OSM
    # ========================================================

    osm_phone = clean_phone(
        lead.get(
            "phone",
            "",
        )
    )

    if valid_phone(
        osm_phone
    ):
        add_candidate(
            pool,
            "phone",
            osm_phone,
            "osm",
            "osm",
            0,
            lead.get(
                "name",
                "",
            ),
            "OSM source",
        )

    osm_website = (
        lead.get(
            "website",
            "",
        )
        or ""
    ).strip()

    if osm_website:
        add_candidate(
            pool,
            "website",
            osm_website,
            "osm",
            "osm",
            0,
            lead.get(
                "name",
                "",
            ),
            "OSM source",
        )

    osm_instagram = (
        lead.get(
            "instagram",
            "",
        )
        or ""
    ).strip()

    if osm_instagram:
        add_candidate(
            pool,
            "instagram",
            osm_instagram,
            "osm",
            "osm",
            0,
            lead.get(
                "name",
                "",
            ),
            "OSM source",
        )

    osm_email = (
        lead.get(
            "email",
            "",
        )
        or ""
    ).strip().lower()

    if osm_email:
        add_candidate(
            pool,
            "email",
            osm_email,
            "osm",
            "osm",
            0,
            lead.get(
                "name",
                "",
            ),
            "OSM source",
        )

    # ========================================================
    # SEARCH RESULTS
    # ========================================================

    for search_type in (
        "identity",
        "contact",
        "digital",
    ):
        for position in range(
            1,
            4,
        ):
            prefix = (
                f"{search_type}_result_"
                f"{position}"
            )

            title = (
                lead.get(
                    f"{prefix}_title",
                    "",
                )
                or ""
            )

            url = (
                lead.get(
                    f"{prefix}_url",
                    "",
                )
                or ""
            )

            snippet = (
                lead.get(
                    f"{prefix}_snippet",
                    "",
                )
                or ""
            )

            if not (
                title
                or url
                or snippet
            ):
                continue

            source = host(
                url
            )

            text = (
                f"{title} {snippet}"
            )

            # ------------------------------------------------
            # PHONE
            # ------------------------------------------------

            for match in (
                PHONE_PATTERN.findall(
                    text
                )
            ):
                phone = clean_phone(
                    match
                )

                if valid_phone(
                    phone
                ):
                    add_candidate(
                        pool,
                        "phone",
                        phone,
                        source,
                        search_type,
                        position,
                        title,
                        snippet,
                    )

            # ------------------------------------------------
            # EMAIL
            # ------------------------------------------------

            for email in (
                EMAIL_PATTERN.findall(
                    text
                )
            ):
                add_candidate(
                    pool,
                    "email",
                    email.lower(),
                    source,
                    search_type,
                    position,
                    title,
                    snippet,
                )

            # ------------------------------------------------
            # INSTAGRAM
            # ------------------------------------------------

            handle = (
                instagram_handle(
                    url
                )
            )

            if handle:
                add_candidate(
                    pool,
                    "instagram",
                    handle,
                    source,
                    search_type,
                    position,
                    title,
                    snippet,
                )

            # ------------------------------------------------
            # WEBSITE
            # ------------------------------------------------

            website = (
                website_candidate(
                    url
                )
            )

            if website:
                add_candidate(
                    pool,
                    "website",
                    website,
                    source,
                    search_type,
                    position,
                    title,
                    snippet,
                )

    return list(
        pool.values()
    )


def load_leads(
    input_file: Path,
    limit: int | None = None,
) -> list[dict[str, str]]:
    if not input_file.exists():
        raise FileNotFoundError(
            f"Arquivo de enrichment não encontrado: "
            f"{input_file}"
        )

    with input_file.open(
        encoding="utf-8",
    ) as file:
        leads = list(
            csv.DictReader(
                file
            )
        )

    if (
        limit is not None
        and limit > 0
    ):
        leads = leads[:limit]

    return leads


def candidate_rows(
    leads: list[dict[str, str]],
    verbose: bool = True,
) -> list[dict[str, Any]]:
    rows: list[
        dict[str, Any]
    ] = []

    for lead in leads:
        candidates = (
            extract_candidates(
                lead
            )
        )

        if verbose:
            print()
            print(
                f"{lead.get('name', '')} "
                f"({len(candidates)} candidatos)"
            )

        for candidate in candidates:
            # Fonte independente != ocorrência.
            sources = {
                evidence["source"]
                for evidence
                in candidate["evidence"]
                if evidence["source"]
            }

            row = {
                "lead": lead.get(
                    "name",
                    "",
                ),
                "type": candidate[
                    "type"
                ],
                "value": candidate[
                    "value"
                ],
                "evidence_count": len(
                    candidate[
                        "evidence"
                    ]
                ),
                "source_count": len(
                    sources
                ),
                "sources": "|".join(
                    sorted(
                        sources
                    )
                ),
            }

            rows.append(
                row
            )

            if verbose:
                print(
                    f"  "
                    f"{candidate['type']:<10} "
                    f"{candidate['value'][:55]:<55} "
                    f"e={row['evidence_count']} "
                    f"s={row['source_count']}"
                )

    return rows


def save_rows(
    rows: list[dict[str, Any]],
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "lead",
        "type",
        "value",
        "evidence_count",
        "source_count",
        "sources",
    ]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        if rows:
            writer.writerows(
                rows
            )


def generate_candidates(
    city: str,
    niche_name: str,
    limit: int | None = None,
    verbose: bool = True,
) -> tuple[
    list[dict[str, Any]],
    Path,
]:
    niche = resolve_niche(
        niche_name
    )

    input_file = build_input_file(
        city=city,
        niche=niche,
    )

    output_file = build_output_file(
        city=city,
        niche=niche,
    )

    leads = load_leads(
        input_file=input_file,
        limit=limit,
    )

    if verbose:
        print()
        print("=" * 88)
        print(
            "LEADFLOW ZERO — CANDIDATE POOL"
        )
        print("=" * 88)

        print(
            f"Cidade : {city}"
        )

        print(
            f"Nicho  : {niche.key}"
        )

        print(
            f"Leads  : {len(leads)}"
        )

    rows = candidate_rows(
        leads=leads,
        verbose=verbose,
    )

    save_rows(
        rows=rows,
        output_file=output_file,
    )

    return (
        rows,
        output_file,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="candidates",
        description=(
            "LeadFlow Zero — geração "
            "do candidate pool."
        ),
    )

    parser.add_argument(
        "--city",
        default="Manaus",
        help="Cidade.",
    )

    parser.add_argument(
        "--niche",
        default="dentistas",
        help="Nicho comercial.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Número máximo de leads.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "Não imprime candidatos "
            "individualmente."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        rows, output_file = (
            generate_candidates(
                city=args.city,
                niche_name=args.niche,
                limit=args.limit,
                verbose=not args.quiet,
            )
        )

        print()
        print(
            f"Total de candidatos: "
            f"{len(rows)}"
        )

        print(
            f"Arquivo salvo: "
            f"{output_file}"
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
