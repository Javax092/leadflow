from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from src.discovery import slugify
from src.niches import resolve_niche


ROOT = Path(__file__).resolve().parent.parent


class PipelineError(RuntimeError):
    pass


def run_module(
    module: str,
    label: str,
    args: list[str] | None = None,
    verbose: bool = False,
    silent: bool = False,
) -> None:
    if verbose:
        print()
        print("=" * 84)
        print(f"ETAPA — {label}")
        print("=" * 84)

    command = [
        sys.executable,
        "-m",
        module,
        *(args or []),
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        stdout=(
            subprocess.DEVNULL
            if silent
            else None
        ),
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

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite de leads nas etapas que suportam corte.",
    )

    parser.add_argument(
        "--min-score",
        type=int,
        default=70,
        help="Score mínimo para listar oportunidade acionável.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostra diagnóstico das etapas intermediárias.",
    )

    return parser.parse_args()


def validate_scope(
    city: str,
    niche: str,
) -> str:
    normalized_city = (
        city.strip()
        .lower()
    )

    if normalized_city != "manaus":
        raise PipelineError(
            "\nEsta versão do MVP está validada "
            "somente para Manaus.\n"
        )

    return resolve_niche(
        niche
    ).key


def required_file(
    path: Path,
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

    niche_key = validate_scope(
        args.city,
        args.niche,
    )

    started_at = time.time()

    if args.verbose:
        print()
        print("=" * 84)
        print("LEADFLOW ZERO")
        print("=" * 84)
        print(
            f"Cidade : {args.city}"
        )
        print(
            f"Nicho  : {niche_key}"
        )
        print(
            f"Modo   : "
            f"{'BUSCA COMPLETA' if args.refresh else 'DADOS EXISTENTES'}"
        )

    # ========================================================
    # DISCOVERY + ENRICHMENT
    # ========================================================

    city_slug = slugify(
        args.city
    )

    base_args = [
        "--city",
        args.city,
        "--niche",
        args.niche,
    ]

    limited_args = base_args.copy()

    if args.limit:
        limited_args.extend(
            [
                "--limit",
                str(args.limit),
            ]
        )

    if args.refresh:
        run_module(
            "src.discovery",
            "DISCOVERY",
            limited_args,
            verbose=args.verbose,
            silent=not args.verbose,
        )

        run_module(
            "src.enrichment_v2",
            "ENRICHMENT",
            limited_args,
            verbose=args.verbose,
            silent=not args.verbose,
        )

    else:
        required_file(
            Path(
                "data/processed"
            )
            / f"{city_slug}_{niche_key}_enriched_v2.csv"
        )

    run_module(
        "src.candidates",
        "CANDIDATES",
        [
            *limited_args,
            "--quiet",
        ],
        verbose=args.verbose,
        silent=not args.verbose,
    )

    # ========================================================
    # VERIFICATION
    # ========================================================

    quiet = [] if args.verbose else ["--quiet"]

    run_module(
        "src.verifier_v2",
        "ENTITY VERIFICATION",
        [
            *base_args,
            *(
                [
                    "--limit",
                    str(args.limit),
                ]
                if args.limit
                else []
            ),
            *quiet,
        ],
        verbose=args.verbose,
        silent=not args.verbose,
    )

    required_file(
        Path(
            "data/processed"
        )
        / f"{city_slug}_{niche_key}_verified_v2.csv"
    )

    # ========================================================
    # WHATSAPP
    # ========================================================

    run_module(
        "src.whatsapp",
        "WHATSAPP RESOLVER",
        [
            *base_args,
            *quiet,
        ],
        verbose=args.verbose,
        silent=not args.verbose,
    )

    required_file(
        Path(
            "data/processed"
        )
        / f"{city_slug}_{niche_key}_whatsapp.csv"
    )

    # ========================================================
    # OPPORTUNITY
    # ========================================================

    run_module(
        "src.opportunity",
        "OPPORTUNITY ENGINE",
        [
            *base_args,
            "--min-score",
            str(args.min_score),
        ],
        verbose=args.verbose,
    )

    output_file = required_file(
        Path(
            "data/processed"
        )
        / f"{city_slug}_{niche_key}_opportunities.csv"
    )

    elapsed = (
        time.time()
        - started_at
    )

    if args.verbose:
        print()
        print("=" * 84)
        print("PIPELINE CONCLUÍDO")
        print("=" * 84)
        print(
            f"Tempo total: "
            f"{elapsed:.1f}s"
        )
        print(
            f"Resultado: {output_file}"
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
