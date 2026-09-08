from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PipelineError(RuntimeError):
    pass


def run_module(
    module: str,
    label: str,
) -> None:
    print()
    print("=" * 84)
    print(f"ETAPA — {label}")
    print("=" * 84)

    command = [
        sys.executable,
        "-m",
        module,
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
    )

    if result.returncode != 0:
        raise PipelineError(
            f"Falha na etapa {label} "
            f"({module})."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="leadflow",
        description=(
            "LeadFlow Zero — descoberta e "
            "priorização comercial de leads."
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
        "--refresh",
        action="store_true",
        help=(
            "Executa novamente discovery e "
            "enrichment antes da análise."
        ),
    )

    return parser.parse_args()


def validate_scope(
    city: str,
    niche: str,
) -> None:
    normalized_city = (
        city.strip()
        .lower()
    )

    normalized_niche = (
        niche.strip()
        .lower()
    )

    supported_niches = {
        "dentista",
        "dentistas",
        "odontologia",
        "clinicas odontologicas",
        "clínicas odontológicas",
    }

    if (
        normalized_city != "manaus"
        or normalized_niche
        not in supported_niches
    ):
        raise PipelineError(
            "\nEsta versão do MVP está validada "
            "somente para dentistas em Manaus.\n"
            "\n"
            "Não vou executar outro nicho como se "
            "o pipeline já fosse genérico.\n"
            "\n"
            "Próxima evolução: parametrizar "
            "discovery + enrichment + contexto "
            "do verifier."
        )


def required_file(
    path: str,
) -> Path:
    file_path = ROOT / path

    if not file_path.exists():
        raise PipelineError(
            f"Arquivo necessário não encontrado: "
            f"{path}\n"
            f"Execute com --refresh."
        )

    return file_path


def main() -> None:
    args = parse_args()

    validate_scope(
        args.city,
        args.niche,
    )

    started_at = time.time()

    print()
    print("=" * 84)
    print("LEADFLOW ZERO")
    print("=" * 84)

    print(
        f"Cidade : {args.city}"
    )

    print(
        f"Nicho  : {args.niche}"
    )

    print(
        f"Modo   : "
        f"{'BUSCA COMPLETA' if args.refresh else 'DADOS EXISTENTES'}"
    )

    # ========================================================
    # DISCOVERY + ENRICHMENT
    # ========================================================

    if args.refresh:
        run_module(
            "src.discovery",
            "DISCOVERY",
        )

        run_module(
            "src.enrichment_v2",
            "ENRICHMENT",
        )

    else:
        required_file(
            "data/processed/"
            "manaus_dentistas_enriched_v2.csv"
        )

    # ========================================================
    # VERIFICATION
    # ========================================================

    run_module(
        "src.verifier_v2",
        "ENTITY VERIFICATION",
    )

    required_file(
        "data/processed/"
        "manaus_dentistas_verified_v2.csv"
    )

    # ========================================================
    # OPPORTUNITY
    # ========================================================

    run_module(
        "src.opportunity",
        "OPPORTUNITY ENGINE",
    )

    required_file(
        "data/processed/"
        "manaus_dentistas_opportunities.csv"
    )

    elapsed = (
        time.time()
        - started_at
    )

    print()
    print("=" * 84)
    print("PIPELINE CONCLUÍDO")
    print("=" * 84)

    print(
        f"Tempo total: "
        f"{elapsed:.1f}s"
    )

    print(
        "Resultado: "
        "data/processed/"
        "manaus_dentistas_opportunities.csv"
    )

    print()
    print(
        "Use somente os leads marcados "
        "como ABORDAR para prospecção."
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\nLeadFlow interrompido."
        )

        raise SystemExit(130)

    except PipelineError as error:
        print(
            f"\nERRO: {error}"
        )

        raise SystemExit(1)
