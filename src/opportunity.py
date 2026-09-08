from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


INPUT_FILE = Path(
    "data/processed/manaus_dentistas_verified_v2.csv"
)

OUTPUT_FILE = Path(
    "data/processed/manaus_dentistas_opportunities.csv"
)


VERIFIED_STATUSES = {
    "VERIFIED",
    "OSM_MATCH",
}


INSTITUTIONAL_TERMS = {
    "aeronautica",
    "aeronautica",
    "fametro",
    "universidade",
    "faculdade",
    "hospital",
    "governo",
    "prefeitura",
    "municipal",
    "estadual",
    "federal",
    "militar",
}


@dataclass
class Opportunity:
    name: str
    score: int
    action: str
    offer: str
    problem: str

    phone: str
    phone_status: str

    website: str
    website_status: str

    instagram: str
    instagram_status: str

    reasons: list[str]


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


def is_verified(
    status: str,
) -> bool:
    return (
        status or ""
    ).strip().upper() in VERIFIED_STATUSES


def get_asset(
    row: dict[str, str],
    kind: str,
) -> tuple[str, str, int]:
    value = (
        row.get(
            f"{kind}_candidate_v2",
            "",
        )
        or ""
    ).strip()

    status = (
        row.get(
            f"{kind}_verification_status_v2",
            "NONE",
        )
        or "NONE"
    ).strip().upper()

    raw_score = (
        row.get(
            f"{kind}_verification_score_v2",
            "0",
        )
        or "0"
    )

    try:
        score = int(
            float(raw_score)
        )
    except ValueError:
        score = 0

    return (
        value,
        status,
        score,
    )


def is_institutional(
    name: str,
) -> bool:
    normalized = normalize(
        name
    )

    return any(
        term in normalized
        for term in INSTITUTIONAL_TERMS
    )


def format_phone(
    value: str,
) -> str:
    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if (
        len(digits) == 11
        and digits.startswith("92")
    ):
        return (
            f"({digits[:2]}) "
            f"{digits[2:7]}-"
            f"{digits[7:]}"
        )

    if (
        len(digits) == 10
        and digits.startswith("92")
    ):
        return (
            f"({digits[:2]}) "
            f"{digits[2:6]}-"
            f"{digits[6:]}"
        )

    return value


def score_site_express(
    row: dict[str, str],
) -> Opportunity:
    name = (
        row.get(
            "name",
            "",
        )
        or ""
    ).strip()

    (
        phone,
        phone_status,
        phone_confidence,
    ) = get_asset(
        row,
        "phone",
    )

    (
        website,
        website_status,
        website_confidence,
    ) = get_asset(
        row,
        "website",
    )

    (
        instagram,
        instagram_status,
        instagram_confidence,
    ) = get_asset(
        row,
        "instagram",
    )

    phone_verified = is_verified(
        phone_status
    )

    website_verified = is_verified(
        website_status
    )

    instagram_verified = is_verified(
        instagram_status
    )

    institutional = is_institutional(
        name
    )

    score = 0
    reasons: list[str] = []

    # ========================================================
    # 1. COMMERCIAL FIT
    # ========================================================

    if institutional:
        score -= 60
        reasons.append(
            "perfil_institucional"
        )

    else:
        score += 20
        reasons.append(
            "negocio_comercial"
        )

    # ========================================================
    # 2. CONTACTABILITY
    # ========================================================

    if phone_verified:
        score += 25
        reasons.append(
            "telefone_verificado"
        )

        if phone_confidence >= 90:
            score += 5
            reasons.append(
                "telefone_alta_confianca"
            )

    elif phone_status == "REVIEW":
        # REVIEW ajuda pouco no ranking, mas NÃO será
        # apresentado como contato confirmado.
        score += 5
        reasons.append(
            "telefone_em_revisao"
        )

    if instagram_verified:
        score += 8
        reasons.append(
            "instagram_verificado"
        )

    # ========================================================
    # 3. DIGITAL GAP
    # ========================================================

    if not website_verified:
        score += 35
        reasons.append(
            "site_proprio_nao_confirmado"
        )

    else:
        # Para Site Express, um site próprio verificado reduz
        # fortemente a oportunidade.
        score -= 35
        reasons.append(
            "site_proprio_verificado"
        )

        if website_confidence >= 90:
            score -= 5
            reasons.append(
                "site_alta_confianca"
            )

    if (
        not website_verified
        and not instagram_verified
    ):
        score += 12
        reasons.append(
            "presenca_digital_fraca"
        )

    elif (
        not website_verified
        and instagram_verified
    ):
        score += 5
        reasons.append(
            "instagram_sem_site_confirmado"
        )

    # ========================================================
    # 4. MINIMUM COMMERCIAL REACHABILITY
    # ========================================================

    has_verified_contact = (
        phone_verified
        or instagram_verified
    )

    if not has_verified_contact:
        score -= 20
        reasons.append(
            "sem_contato_verificado"
        )

    # ========================================================
    # NORMALIZE
    # ========================================================

    score = max(
        0,
        min(score, 100),
    )

    # ========================================================
    # ACTION
    # ========================================================

    if institutional:
        action = "DESCARTAR"

    elif (
        score >= 70
        and has_verified_contact
        and not website_verified
    ):
        action = "ABORDAR"

    elif score >= 45:
        action = "REVISAR"

    else:
        action = "DESCARTAR"

    # ========================================================
    # PROBLEM / OFFER
    # ========================================================

    if institutional:
        problem = (
            "Perfil institucional fora do ICP "
            "da oferta atual."
        )

        offer = "NENHUMA"

    elif website_verified:
        problem = (
            "Site próprio já confirmado; "
            "baixa prioridade para Site Express."
        )

        offer = "OUTRA_OFERTA"

    elif (
        phone_verified
        and not website_verified
        and not instagram_verified
    ):
        problem = (
            "Empresa contatável, mas sem site próprio "
            "ou Instagram confirmados."
        )

        offer = "SITE_EXPRESS"

    elif (
        instagram_verified
        and not website_verified
    ):
        problem = (
            "Possui presença social confirmada, "
            "mas site próprio não foi encontrado."
        )

        offer = "SITE_EXPRESS"

    elif not website_verified:
        problem = (
            "Site próprio não confirmado, mas o contato "
            "comercial ainda precisa ser validado."
        )

        offer = "SITE_EXPRESS"

    else:
        problem = (
            "Nenhuma lacuna comercial prioritária "
            "detectada para a oferta atual."
        )

        offer = "NENHUMA"

    return Opportunity(
        name=name,
        score=score,
        action=action,
        offer=offer,
        problem=problem,
        phone=phone,
        phone_status=phone_status,
        website=website,
        website_status=website_status,
        instagram=instagram,
        instagram_status=instagram_status,
        reasons=reasons,
    )


def opportunity_rank(
    opportunity: Opportunity,
) -> tuple[int, int]:
    action_rank = {
        "ABORDAR": 3,
        "REVISAR": 2,
        "DESCARTAR": 1,
    }

    return (
        action_rank.get(
            opportunity.action,
            0,
        ),
        opportunity.score,
    )


def evaluate_rows(
    rows: list[dict[str, str]],
) -> list[Opportunity]:
    opportunities = [
        score_site_express(
            row
        )
        for row in rows
    ]

    return sorted(
        opportunities,
        key=opportunity_rank,
        reverse=True,
    )


def load_rows(
    path: Path,
) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    with path.open(
        encoding="utf-8",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def save_results(
    opportunities: list[Opportunity],
) -> None:
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "name",
        "opportunity_score",
        "action",
        "offer",
        "problem",
        "phone",
        "phone_status",
        "website",
        "website_status",
        "instagram",
        "instagram_status",
        "reasons",
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for item in opportunities:
            writer.writerow(
                {
                    "name": item.name,
                    "opportunity_score": (
                        item.score
                    ),
                    "action": item.action,
                    "offer": item.offer,
                    "problem": item.problem,
                    "phone": item.phone,
                    "phone_status": (
                        item.phone_status
                    ),
                    "website": item.website,
                    "website_status": (
                        item.website_status
                    ),
                    "instagram": (
                        item.instagram
                    ),
                    "instagram_status": (
                        item.instagram_status
                    ),
                    "reasons": ",".join(
                        item.reasons
                    ),
                }
            )


def print_report(
    opportunities: list[Opportunity],
) -> None:
    approach = [
        item
        for item in opportunities
        if item.action == "ABORDAR"
    ]

    review = [
        item
        for item in opportunities
        if item.action == "REVISAR"
    ]

    discarded = [
        item
        for item in opportunities
        if item.action == "DESCARTAR"
    ]

    print()
    print("=" * 84)
    print(
        "LEADFLOW ZERO — "
        "OPPORTUNITY ENGINE v1"
    )
    print("=" * 84)

    print()
    print(
        f"Empresas analisadas : "
        f"{len(opportunities)}"
    )

    print(
        f"ABORDAR             : "
        f"{len(approach)}"
    )

    print(
        f"REVISAR             : "
        f"{len(review)}"
    )

    print(
        f"DESCARTAR           : "
        f"{len(discarded)}"
    )

    print()
    print("-" * 84)
    print(
        "OPORTUNIDADES RECOMENDADAS"
    )
    print("-" * 84)

    if not approach:
        print()
        print(
            "Nenhuma oportunidade atingiu "
            "o critério de abordagem."
        )

    for index, item in enumerate(
        approach,
        start=1,
    ):
        print()
        print(
            f"#{index} "
            f"{item.name}"
        )

        print(
            f"Score      : "
            f"{item.score}/100"
        )

        print(
            f"Ação       : "
            f"{item.action}"
        )

        print(
            f"Oferta     : "
            f"{item.offer}"
        )

        if is_verified(
            item.phone_status
        ):
            print(
                f"Telefone   : "
                f"{format_phone(item.phone)} ✓"
            )

        elif is_verified(
            item.instagram_status
        ):
            print(
                f"Instagram  : "
                f"@{item.instagram} ✓"
            )

        print(
            f"Problema   : "
            f"{item.problem}"
        )

        print(
            f"Sinais     : "
            f"{', '.join(item.reasons)}"
        )

    print()
    print("=" * 84)

    print(
        f"Arquivo salvo: "
        f"{OUTPUT_FILE}"
    )


def main() -> None:
    rows = load_rows(
        INPUT_FILE
    )

    opportunities = evaluate_rows(
        rows
    )

    save_results(
        opportunities
    )

    print_report(
        opportunities
    )


if __name__ == "__main__":
    main()
