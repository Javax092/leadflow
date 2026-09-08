from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from ddgs import DDGS


INPUT_FILE = Path("data/raw/manaus_dentistas.csv")
OUTPUT_FILE = Path("data/processed/manaus_dentistas_enriched.csv")


def load_leads() -> list[dict[str, Any]]:
    with INPUT_FILE.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def search_web(query: str, max_results: int = 5) -> list[dict]:
    try:
        return list(
            DDGS().text(
                query,
                max_results=max_results,
            )
        )
    except Exception as error:
        print(f"Erro na busca: {error}")
        return []


def enrich_lead(lead: dict[str, Any]) -> dict[str, Any]:
    name = lead["name"]

    query = f'"{name}" Manaus Amazonas'

    print()
    print("=" * 70)
    print(f"Pesquisando: {name}")
    print(f"Query: {query}")
    print("-" * 70)

    results = search_web(query)

    enriched = lead.copy()

    enriched["search_query"] = query
    enriched["search_results_count"] = len(results)

    # Por enquanto NÃO decidimos automaticamente
    # qual resultado pertence à empresa.
    # Apenas armazenamos evidências.
    for index in range(3):
        position = index + 1

        if index < len(results):
            result = results[index]

            enriched[f"result_{position}_title"] = result.get("title", "")
            enriched[f"result_{position}_url"] = result.get("href", "")
            enriched[f"result_{position}_snippet"] = result.get("body", "")

        else:
            enriched[f"result_{position}_title"] = ""
            enriched[f"result_{position}_url"] = ""
            enriched[f"result_{position}_snippet"] = ""

    for index, result in enumerate(results[:3], start=1):
        print(f"\n[{index}] {result.get('title', '')}")
        print(result.get("href", ""))
        print(result.get("body", "")[:250])

    # Pequeno intervalo para não bombardear o serviço.
    time.sleep(2)

    return enriched


def save_csv(rows: list[dict[str, Any]]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
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
    print(f"Arquivo salvo em: {OUTPUT_FILE}")


def main() -> None:
    leads = load_leads()

    print(f"{len(leads)} leads carregados.")

    # Experimento controlado:
    # somente os primeiros 5.
    leads = leads[:5]

    enriched = []

    for lead in leads:
        enriched.append(enrich_lead(lead))

    if enriched:
        save_csv(enriched)


if __name__ == "__main__":
    main()
