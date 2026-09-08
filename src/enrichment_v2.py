from __future__ import annotations

import argparse
import csv
import random
import time
from pathlib import Path
from typing import Any

from ddgs import DDGS

from src.discovery import slugify
from src.niches import NicheConfig, resolve_niche


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


SEARCH_TYPES = {
    "identity": '"{name}" {city}',
    "contact": '"{name}" {city} telefone WhatsApp',
    "digital": '"{name}" {city} Instagram site',
}


def build_input_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return RAW_DIR / (
        f"{slugify(city)}_{niche.key}.csv"
    )


def build_output_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return PROCESSED_DIR / (
        f"{slugify(city)}_{niche.key}_enriched_v2.csv"
    )


def load_leads(
    input_file: Path,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not input_file.exists():
        raise FileNotFoundError(
            f"Arquivo de discovery não encontrado: "
            f"{input_file}"
        )

    with input_file.open(
        encoding="utf-8",
    ) as file:
        leads = list(
            csv.DictReader(file)
        )

    if (
        limit is not None
        and limit > 0
    ):
        leads = leads[:limit]

    return leads


def search_web(
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    try:
        return list(
            DDGS().text(
                query,
                max_results=max_results,
            )
        )

    except Exception as error:
        print(
            f"    ERRO: {error}"
        )

        return []


def enrich_lead(
    lead: dict[str, Any],
    city: str,
) -> dict[str, Any]:
    name = (
        lead.get("name", "")
        or ""
    ).strip()

    print()
    print("=" * 72)
    print(
        f"LEAD: {name}"
    )
    print("=" * 72)

    enriched = lead.copy()

    for (
        search_type,
        template,
    ) in SEARCH_TYPES.items():

        query = template.format(
            name=name,
            city=city,
        )

        print(
            f"\n[{search_type.upper()}]"
        )

        print(query)

        results = search_web(
            query,
            max_results=5,
        )

        enriched[
            f"{search_type}_query"
        ] = query

        enriched[
            f"{search_type}_results_count"
        ] = len(results)

        # Mantemos os 3 primeiros resultados no dataset
        # para preservar o contrato do pipeline atual.
        for index in range(3):
            position = index + 1

            prefix = (
                f"{search_type}_result_"
                f"{position}"
            )

            if index < len(results):
                result = results[index]

                enriched[
                    f"{prefix}_title"
                ] = (
                    result.get(
                        "title",
                        "",
                    )
                    or ""
                )

                enriched[
                    f"{prefix}_url"
                ] = (
                    result.get(
                        "href",
                        "",
                    )
                    or ""
                )

                enriched[
                    f"{prefix}_snippet"
                ] = (
                    result.get(
                        "body",
                        "",
                    )
                    or ""
                )

                print(
                    f"  {position}. "
                    f"{result.get('title', '')[:80]}"
                )

                print(
                    f"     "
                    f"{result.get('href', '')}"
                )

            else:
                enriched[
                    f"{prefix}_title"
                ] = ""

                enriched[
                    f"{prefix}_url"
                ] = ""

                enriched[
                    f"{prefix}_snippet"
                ] = ""

        # Mantemos o comportamento já validado:
        # nada de rajadas de consultas consecutivas.
        time.sleep(
            random.uniform(
                1.5,
                3.0,
            )
        )

    return enriched


def save_csv(
    rows: list[dict[str, Any]],
    output_file: Path,
) -> None:
    if not rows:
        print(
            "Nenhum lead enriquecido para salvar."
        )
        return

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    print()
    print("=" * 72)
    print(
        f"Arquivo salvo: {output_file}"
    )
    print("=" * 72)


def enrich(
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

    print(
        "LeadFlow Zero — Enrichment v2"
    )

    print(
        f"Cidade : {city}"
    )

    print(
        f"Nicho  : {niche.key}"
    )

    print(
        f"Entrada: {input_file}"
    )

    print(
        f"{len(leads)} leads carregados."
    )

    enriched: list[
        dict[str, Any]
    ] = []

    for index, lead in enumerate(
        leads,
        start=1,
    ):
        print(
            f"\nPROCESSANDO "
            f"{index}/{len(leads)}"
        )

        enriched.append(
            enrich_lead(
                lead=lead,
                city=city,
            )
        )

    return (
        enriched,
        output_file,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="enrichment_v2",
        description=(
            "LeadFlow Zero — enriquecimento "
            "de evidências públicas."
        ),
    )

    parser.add_argument(
        "--city",
        default="Manaus",
        help="Cidade dos estabelecimentos.",
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
            "Número máximo de leads "
            "a enriquecer."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        enriched, output_file = enrich(
            city=args.city,
            niche_name=args.niche,
            limit=args.limit,
        )

        save_csv(
            rows=enriched,
            output_file=output_file,
        )

    except (
        ValueError,
        FileNotFoundError,
    ) as error:
        raise SystemExit(
            f"Erro: {error}"
        )

    except KeyboardInterrupt:
        raise SystemExit(
            "\nEnrichment interrompido."
        )


if __name__ == "__main__":
    main()
