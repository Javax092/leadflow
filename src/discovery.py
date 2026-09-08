from __future__ import annotations

import argparse
import csv
import re
import unicodedata
import time
from pathlib import Path
from typing import Any

import requests

from src.niches import NicheConfig, resolve_niche


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
)
OUTPUT_DIR = Path("data/raw")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)

    return value.strip("_")


def build_output_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return OUTPUT_DIR / (
        f"{slugify(city)}_{niche.key}.csv"
    )


def escape_overpass(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )


def build_query(
    city: str,
    niche: NicheConfig,
) -> str:
    safe_city = escape_overpass(city)

    selectors = "\n".join(
        (
            f'  nwr["{escape_overpass(key)}"='
            f'"{escape_overpass(value)}"]'
            f"(area.searchArea);"
        )
        for key, value in niche.osm_tags
    )

    return f"""
[out:json][timeout:60];

area["name"="{safe_city}"]["boundary"="administrative"]->.searchArea;

(
{selectors}
);

out center tags;
"""


def fetch_overpass(
    city: str,
    niche: NicheConfig,
) -> dict[str, Any]:
    query = build_query(
        city=city,
        niche=niche,
    )

    print(
        f"Consultando OpenStreetMap/Overpass: "
        f"{city} • {niche.key}"
    )

    errors: list[str] = []

    for endpoint_index, endpoint in enumerate(
        OVERPASS_URLS,
        start=1,
    ):
        for attempt in range(1, 3):
            try:
                print(
                    f"  Endpoint {endpoint_index}/"
                    f"{len(OVERPASS_URLS)} "
                    f"• tentativa {attempt}/2"
                )

                response = requests.get(
                    endpoint,
                    params={
                        "data": query,
                    },
                    timeout=120,
                    headers={
                        "User-Agent": (
                            "LeadFlow-Zero/0.2 "
                            "(OSM discovery)"
                        )
                    },
                )

                response.raise_for_status()

                data = response.json()

                if "elements" not in data:
                    raise ValueError(
                        "Resposta Overpass sem "
                        "campo 'elements'."
                    )

                print(
                    f"  ✓ Overpass respondeu "
                    f"com {len(data['elements'])} "
                    f"elementos."
                )

                return data

            except (
                requests.RequestException,
                ValueError,
            ) as error:
                message = (
                    f"{endpoint} "
                    f"tentativa={attempt}: "
                    f"{error}"
                )

                errors.append(message)

                print(
                    f"  Falhou: {error}"
                )

                if attempt < 2:
                    wait_seconds = 3 * attempt

                    print(
                        f"  Aguardando "
                        f"{wait_seconds}s..."
                    )

                    time.sleep(
                        wait_seconds
                    )

        print(
            "  Tentando próximo "
            "endpoint Overpass..."
        )

    details = "\n".join(
        f"- {error}"
        for error in errors
    )

    raise requests.RequestException(
        "Todos os endpoints Overpass "
        "falharam.\n"
        f"{details}"
    )


def get_coordinates(
    element: dict[str, Any],
) -> tuple[Any, Any]:
    if element.get("type") == "node":
        return (
            element.get("lat"),
            element.get("lon"),
        )

    center = element.get(
        "center",
        {},
    )

    return (
        center.get("lat"),
        center.get("lon"),
    )


def normalize(
    element: dict[str, Any],
) -> dict[str, Any]:
    tags = element.get(
        "tags",
        {},
    )

    lat, lon = get_coordinates(
        element
    )

    street = tags.get(
        "addr:street",
        "",
    )

    number = tags.get(
        "addr:housenumber",
        "",
    )

    address = " ".join(
        value
        for value in (
            street,
            number,
        )
        if value
    )

    return {
        "osm_type": element.get(
            "type",
            "",
        ),
        "osm_id": element.get(
            "id",
            "",
        ),
        "name": tags.get(
            "name",
            "",
        ),
        "phone": (
            tags.get("contact:phone")
            or tags.get("phone", "")
        ),
        "website": (
            tags.get("contact:website")
            or tags.get("website", "")
        ),
        "instagram": tags.get(
            "contact:instagram",
            "",
        ),
        "facebook": tags.get(
            "contact:facebook",
            "",
        ),
        "email": (
            tags.get("contact:email")
            or tags.get("email", "")
        ),
        "address": address,
        "neighbourhood": tags.get(
            "addr:suburb",
            "",
        ),
        "postcode": tags.get(
            "addr:postcode",
            "",
        ),
        "lat": lat,
        "lon": lon,
    }


def deduplicate(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []

    for row in rows:
        key = (
            str(row.get("osm_type", "")),
            str(row.get("osm_id", "")),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(row)

    return unique


def save_csv(
    rows: list[dict[str, Any]],
    output_file: Path,
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        print(
            "Nenhum estabelecimento encontrado."
        )
        return

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Arquivo salvo em: {output_file}"
    )


def print_summary(
    rows: list[dict[str, Any]],
    city: str,
    niche: NicheConfig,
) -> None:
    total = len(rows)

    with_phone = sum(
        bool(row["phone"])
        for row in rows
    )

    with_website = sum(
        bool(row["website"])
        for row in rows
    )

    with_instagram = sum(
        bool(row["instagram"])
        for row in rows
    )

    with_email = sum(
        bool(row["email"])
        for row in rows
    )

    print()
    print("=" * 68)
    print(
        "LEADFLOW ZERO — DISCOVERY REPORT"
    )
    print("=" * 68)

    print(
        f"Cidade               : {city}"
    )

    print(
        f"Nicho                : {niche.key}"
    )

    print(
        f"Registros encontrados: {total}"
    )

    print(
        f"Com telefone         : {with_phone}"
    )

    print(
        f"Com website          : {with_website}"
    )

    print(
        f"Com Instagram        : {with_instagram}"
    )

    print(
        f"Com email            : {with_email}"
    )

    print()
    print("PRIMEIROS RESULTADOS")
    print("-" * 68)

    for index, row in enumerate(
        rows[:10],
        start=1,
    ):
        print(f"\n#{index}")

        print(
            f"Nome      : "
            f"{row['name'] or 'N/D'}"
        )

        print(
            f"Telefone  : "
            f"{row['phone'] or 'N/D'}"
        )

        print(
            f"Website   : "
            f"{row['website'] or 'N/D'}"
        )

        print(
            f"Instagram : "
            f"{row['instagram'] or 'N/D'}"
        )

        print(
            f"Bairro    : "
            f"{row['neighbourhood'] or 'N/D'}"
        )

        print(
            f"Endereço  : "
            f"{row['address'] or 'N/D'}"
        )


def discover(
    city: str,
    niche_name: str,
    limit: int | None = None,
) -> tuple[
    list[dict[str, Any]],
    Path,
]:
    niche = resolve_niche(
        niche_name
    )

    data = fetch_overpass(
        city=city,
        niche=niche,
    )

    elements = data.get(
        "elements",
        [],
    )

    rows = [
        normalize(element)
        for element in elements
    ]

    # Registros sem nome não são comercialmente úteis
    # nesta fase do LeadFlow.
    rows = [
        row
        for row in rows
        if row["name"]
    ]

    rows = deduplicate(
        rows
    )

    # Ordem determinística antes do limit.
    rows.sort(
        key=lambda row: (
            str(row["name"]).lower(),
            str(row["osm_id"]),
        )
    )

    if (
        limit is not None
        and limit > 0
    ):
        rows = rows[:limit]

    output_file = build_output_file(
        city=city,
        niche=niche,
    )

    return (
        rows,
        output_file,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="discovery",
        description=(
            "LeadFlow Zero — descoberta "
            "de empresas via OpenStreetMap."
        ),
    )

    parser.add_argument(
        "--city",
        default="Manaus",
        help="Cidade da busca.",
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
        help=(
            "Máximo de estabelecimentos "
            "salvos após a descoberta."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        niche = resolve_niche(
            args.niche
        )

        rows, output_file = discover(
            city=args.city,
            niche_name=args.niche,
            limit=args.limit,
        )

        print_summary(
            rows=rows,
            city=args.city,
            niche=niche,
        )

        save_csv(
            rows=rows,
            output_file=output_file,
        )

    except ValueError as error:
        raise SystemExit(
            f"Erro de configuração: {error}"
        )

    except requests.RequestException as error:
        raise SystemExit(
            f"Erro ao consultar Overpass: {error}"
        )

    except Exception as error:
        raise SystemExit(
            f"Erro inesperado: {error}"
        )


if __name__ == "__main__":
    main()
