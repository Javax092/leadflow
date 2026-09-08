from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from rapidfuzz.fuzz import partial_ratio, ratio, token_set_ratio

from src.candidates import extract_candidates
from src.discovery import slugify
from src.niches import NicheConfig, resolve_niche


PROCESSED_DIR = Path("data/processed")


BAD_DOMAINS = {
    "wanderlog.com",
    "acnur.org",
    "pmc.ncbi.nlm.nih.gov",
    "arquivosdeneuropsiquiatria.org",
    "fliphtml5.com",
    "science.gov",
    "stretto.com",
    "idcrawl.com",
    "starngage.com",
    "rentechdigital.com",
    "helpmecovid.com",
    "ortosena.com.br",
    "manausprevidencia.manaus.am.gov.br",
    "one-line.com",
    "openaccesspublications.org",
    "books.scielo.org",
    "atacadaosports.com",
}


GENERIC_INSTAGRAMS = {
    "prefeiturademanaus",
    "banzeiromanaus.oficial",
    "trinitaclinica",
}


BASE_STOPWORDS = {
    "clinica",
    "consultorio",
    "instituto",
    "unidade",
    "dra",
    "dr",
    "de",
    "da",
    "do",
    "dos",
    "das",
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


def compact(text: str) -> str:
    return normalize(text).replace(
        " ",
        "",
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


def is_bad_domain(domain: str) -> bool:
    return any(
        domain == bad
        or domain.endswith("." + bad)
        for bad in BAD_DOMAINS
    )


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
        f"{niche.key}_verified_v2.csv"
    )


def stopwords_for(
    niche: NicheConfig,
) -> set[str]:
    """
    Termos genéricos do nicho não devem dominar
    a identidade da empresa.

    Mantemos o comportamento odontológico anterior
    adicionando os termos que já eram stopwords.
    """
    words = set(
        BASE_STOPWORDS
    )

    if niche.key == "dentistas":
        words.update(
            {
                "odontologica",
                "odontologico",
                "odontologia",
                "preventiva",
                "protese",
                "estetica",
            }
        )

    elif niche.key == "lojas_de_moveis":
        words.update(
            {
                "moveis",
                "movel",
                "loja",
                "planejados",
                "planejado",
            }
        )

    return words


def business_tokens(
    name: str,
    niche: NicheConfig,
) -> set[str]:
    stopwords = stopwords_for(
        niche
    )

    return {
        token
        for token in normalize(name).split()
        if len(token) >= 3
        and token not in stopwords
    }


def evidence_text(
    candidate: dict,
) -> str:
    pieces = []

    for evidence in candidate["evidence"]:
        pieces.append(
            evidence.get(
                "title",
                "",
            )
        )

        pieces.append(
            evidence.get(
                "snippet",
                "",
            )
        )

    return " ".join(
        pieces
    )


def identity_score(
    lead: dict[str, str],
    candidate: dict,
    niche: NicheConfig,
    city: str,
) -> tuple[int, list[str]]:
    name = normalize(
        lead["name"]
    )

    text = normalize(
        evidence_text(candidate)
    )

    reasons: list[str] = []
    score = 0

    if not text:
        return 0, reasons

    full_ratio = ratio(
        name,
        text,
    )

    partial = partial_ratio(
        name,
        text,
    )

    token_ratio = token_set_ratio(
        name,
        text,
    )

    if (
        full_ratio >= 85
        or partial >= 92
        or token_ratio >= 92
    ):
        score += 35
        reasons.append(
            "nome_forte"
        )

    elif (
        full_ratio >= 60
        or partial >= 75
        or token_ratio >= 75
    ):
        score += 20
        reasons.append(
            "nome_parcial"
        )

    lead_tokens = business_tokens(
        lead["name"],
        niche,
    )

    text_tokens = set(
        text.split()
    )

    common = (
        lead_tokens
        & text_tokens
    )

    if len(common) >= 2:
        score += 20
        reasons.append(
            "tokens_fortes"
        )

    elif len(common) == 1:
        score += 8
        reasons.append(
            "token_parcial"
        )

    city_normalized = normalize(
        city
    )

    if (
        city_normalized
        and city_normalized in text
    ):
        score += 15
        reasons.append(
            "cidade"
        )

    neighbourhood = normalize(
        lead.get(
            "neighbourhood",
            "",
        )
    )

    if (
        neighbourhood
        and neighbourhood in text
    ):
        score += 10
        reasons.append(
            "bairro"
        )

    return min(
        score,
        80,
    ), reasons


def source_stats(
    candidate: dict,
) -> tuple[int, int, set[str]]:
    sources = {
        evidence.get(
            "source",
            "",
        )
        for evidence in candidate["evidence"]
        if evidence.get(
            "source",
            "",
        )
    }

    return (
        len(candidate["evidence"]),
        len(sources),
        sources,
    )


def verify_candidate(
    lead: dict[str, str],
    candidate: dict,
    niche: NicheConfig,
    city: str,
) -> dict:
    kind = candidate["type"]
    value = candidate["value"]

    identity, reasons = identity_score(
        lead,
        candidate,
        niche,
        city,
    )

    (
        evidence_count,
        source_count,
        _sources,
    ) = source_stats(
        candidate
    )

    score = identity

    # ========================================================
    # OSM AGREEMENT
    # ========================================================

    has_osm = any(
        evidence.get("source") == "osm"
        for evidence in candidate["evidence"]
    )

    if has_osm:
        score += 45
        reasons.append(
            "osm"
        )

    # ========================================================
    # INDEPENDENT CORROBORATION
    # ========================================================

    if source_count >= 2:
        score += 25
        reasons.append(
            "fontes_independentes"
        )

    elif evidence_count >= 2:
        score += 10
        reasons.append(
            "evidencia_repetida"
        )

    # ========================================================
    # WEBSITE
    # ========================================================

    if kind == "website":
        domain = host(
            value
        )

        if is_bad_domain(
            domain
        ):
            return {
                **candidate,
                "score": 0,
                "status": "REJECTED",
                "reasons": [
                    "dominio_invalido"
                ],
            }

        domain_base = compact(
            domain.split(".")[0]
        )

        matches = sum(
            compact(token) in domain_base
            for token in business_tokens(
                lead["name"],
                niche,
            )
        )

        if matches >= 2:
            score += 35
            reasons.append(
                "dominio_forte"
            )

        elif matches == 1:
            score += 20
            reasons.append(
                "dominio_parcial"
            )

    # ========================================================
    # INSTAGRAM
    # ========================================================

    elif kind == "instagram":
        handle = (
            value.lower()
            .replace("@", "")
            .strip()
        )

        if handle in GENERIC_INSTAGRAMS:
            return {
                **candidate,
                "score": 0,
                "status": "REJECTED",
                "reasons": [
                    "instagram_invalido"
                ],
            }

        handle_compact = compact(
            handle
        )

        lead_tokens = business_tokens(
            lead["name"],
            niche,
        )

        matches = sum(
            compact(token) in handle_compact
            for token in lead_tokens
        )

        if matches >= 2:
            score += 30
            reasons.append(
                "handle_forte"
            )

        elif matches == 1:
            score += 15
            reasons.append(
                "handle_parcial"
            )

        evidence_normalized = normalize(
            evidence_text(candidate)
        )

        city_normalized = normalize(
            city
        )

        has_location = (
            city_normalized
            and city_normalized
            in evidence_normalized
        )

        has_business_context = any(
            normalize(term)
            in evidence_normalized
            for term in niche.context_terms
        )

        has_independent_source = (
            source_count >= 2
        )

        has_identity_anchor = (
            (
                has_location
                and has_business_context
            )
            or has_independent_source
            or has_osm
        )

        # Regra anti-homônimo.
        if not has_identity_anchor:
            score = min(
                score,
                60,
            )

            reasons.append(
                "sem_ancora_identidade"
            )

    # ========================================================
    # PHONE
    # ========================================================

    elif kind == "phone":
        digits = re.sub(
            r"\D",
            "",
            value,
        )

        # Geografia ainda está validada apenas para Manaus.
        if normalize(city) == "manaus":
            if digits.startswith("92"):
                score += 10
                reasons.append(
                    "ddd_92"
                )

            elif len(digits) >= 10:
                score -= 25
                reasons.append(
                    "ddd_conflitante"
                )

    # ========================================================
    # EMAIL
    # ========================================================

    elif kind == "email":
        email_domain = (
            value.split("@")[-1]
            if "@" in value
            else ""
        )

        if email_domain:
            domain_base = compact(
                email_domain.split(".")[0]
            )

            if any(
                compact(token) in domain_base
                for token in business_tokens(
                    lead["name"],
                    niche,
                )
            ):
                score += 20
                reasons.append(
                    "email_domain_match"
                )

    # ========================================================
    # FINAL SCORE
    # ========================================================

    score = max(
        0,
        min(score, 100),
    )

    if score >= 75:
        status = "VERIFIED"

    elif score >= 45:
        status = "REVIEW"

    else:
        status = "REJECTED"

    return {
        **candidate,
        "score": score,
        "status": status,
        "reasons": reasons,
    }


def candidate_rank(
    candidate: dict,
):
    status_rank = {
        "VERIFIED": 3,
        "REVIEW": 2,
        "REJECTED": 1,
    }

    return (
        status_rank.get(
            candidate["status"],
            0,
        ),
        candidate["score"],
    )


def best_by_type(
    verified_candidates: list[dict],
) -> dict[str, dict]:
    best = {}

    for candidate in verified_candidates:
        kind = candidate["type"]

        current = best.get(
            kind
        )

        if (
            current is None
            or candidate_rank(candidate)
            > candidate_rank(current)
        ):
            best[kind] = candidate

    return best


def verify_leads(
    city: str,
    niche_name: str,
    verbose: bool = True,
) -> tuple[list[dict], Path]:
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
            f"Enrichment não encontrado: "
            f"{input_file}"
        )

    with input_file.open(
        encoding="utf-8",
    ) as file:
        leads = list(
            csv.DictReader(file)
        )

    rows = []

    if verbose:
        print()
        print("=" * 96)
        print(
            "LEADFLOW ZERO — "
            "CANDIDATE VERIFIER v2.2"
        )
        print("=" * 96)
        print(
            f"Cidade : {city}"
        )
        print(
            f"Nicho  : {niche.key}"
        )

    for lead in leads:
        candidates = extract_candidates(
            lead
        )

        verified_candidates = [
            verify_candidate(
                lead,
                candidate,
                niche,
                city,
            )
            for candidate in candidates
        ]

        best = best_by_type(
            verified_candidates
        )

        output = lead.copy()

        if verbose:
            print()
            print(
                lead["name"]
            )

        for kind in (
            "phone",
            "website",
            "instagram",
            "email",
        ):
            candidate = best.get(
                kind
            )

            if not candidate:
                output[
                    f"{kind}_candidate_v2"
                ] = ""

                output[
                    f"{kind}_verification_score_v2"
                ] = "0"

                output[
                    f"{kind}_verification_status_v2"
                ] = "NONE"

                if verbose:
                    print(
                        f"  {kind.upper():<10} "
                        f"N/D → NONE 0"
                    )

                continue

            output[
                f"{kind}_candidate_v2"
            ] = candidate["value"]

            output[
                f"{kind}_verification_score_v2"
            ] = str(
                candidate["score"]
            )

            output[
                f"{kind}_verification_status_v2"
            ] = candidate["status"]

            if verbose:
                print(
                    f"  {kind.upper():<10} "
                    f"{candidate['value'][:55]} "
                    f"→ {candidate['status']} "
                    f"{candidate['score']} "
                    f"[{','.join(candidate['reasons'])}]"
                )

        rows.append(
            output
        )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if rows:
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
            writer.writerows(
                rows
            )

    return rows, output_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verifier_v2",
        description=(
            "LeadFlow Zero — "
            "verificação de entidades."
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
        rows, output_file = verify_leads(
            city=args.city,
            niche_name=args.niche,
            verbose=not args.quiet,
        )

        print()
        print(
            f"Leads verificados: "
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
