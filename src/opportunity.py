from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

from src.discovery import slugify
from src.niches import NicheConfig, normalize, resolve_niche


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
    whatsapp: str
    whatsapp_status: str
    whatsapp_confidence: int
    commercial_contact_status: str
    commercial_contact_confidence: int

    website: str
    website_status: str

    instagram: str
    instagram_status: str

    reasons: list[str]


def build_input_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return Path("data/processed") / (
        f"{slugify(city)}_{niche.key}_whatsapp.csv"
    )


def build_output_file(
    city: str,
    niche: NicheConfig,
) -> Path:
    return Path("data/processed") / (
        f"{slugify(city)}_{niche.key}_opportunities.csv"
    )


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
    niche: NicheConfig,
) -> bool:
    normalized = normalize(
        name
    )

    return any(
        term in normalized
        for term in (
            *INSTITUTIONAL_TERMS,
            *niche.institutional_terms,
        )
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


def int_field(
    row: dict[str, str],
    key: str,
) -> int:
    try:
        return int(
            float(
                row.get(key, "0")
                or "0"
            )
        )
    except ValueError:
        return 0


def is_verified_whatsapp_commercial_contact(
    row: dict[str, str],
) -> bool:
    return (
        (
            row.get(
                "whatsapp_status",
                "",
            )
            or ""
        ).strip().upper()
        == "VERIFIED"
        and (
            row.get(
                "commercial_contact_status",
                "",
            )
            or ""
        ).strip().upper()
        == "VERIFIED"
    )


def score_site_express(
    row: dict[str, str],
    niche: NicheConfig,
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

    whatsapp = (
        row.get(
            "whatsapp_candidate",
            "",
        )
        or ""
    ).strip()

    whatsapp_status = (
        row.get(
            "whatsapp_status",
            "NONE",
        )
        or "NONE"
    ).strip().upper()

    whatsapp_confidence = int_field(
        row,
        "whatsapp_confidence",
    )

    commercial_contact_status = (
        row.get(
            "commercial_contact_status",
            "NONE",
        )
        or "NONE"
    ).strip().upper()

    commercial_contact_confidence = int_field(
        row,
        "commercial_contact_confidence",
    )

    has_commercial_whatsapp = (
        is_verified_whatsapp_commercial_contact(
            row
        )
    )

    website_verified = is_verified(
        website_status
    )

    instagram_verified = is_verified(
        instagram_status
    )

    institutional = is_institutional(
        name,
        niche,
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

    # Pesos de contactabilidade:
    # telefone verificado = +8 potencial de contato;
    # WhatsApp verificado = +12 evidência de canal;
    # WhatsApp comercial verificado = +28 elegível para ABORDAR.
    if phone_verified:
        score += 8
        reasons.append(
            "telefone_verificado_entidade"
        )

        if phone_confidence >= 90:
            score += 2
            reasons.append(
                "telefone_alta_confianca"
            )

    elif phone_status == "REVIEW":
        score += 3
        reasons.append(
            "telefone_em_revisao"
        )

    if whatsapp_status == "VERIFIED":
        score += 12
        reasons.append(
            "whatsapp_verificado"
        )

    elif whatsapp_status == "REVIEW":
        score += 4
        reasons.append(
            "whatsapp_em_revisao"
        )

    if has_commercial_whatsapp:
        score += 28
        reasons.append(
            "whatsapp_comercial_verificado"
        )

    elif (
        whatsapp_status == "VERIFIED"
        and commercial_contact_status != "VERIFIED"
    ):
        score += 4
        reasons.append(
            "whatsapp_sem_confirmacao_comercial"
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

    if (
        not has_commercial_whatsapp
        and not instagram_verified
    ):
        score -= 20
        reasons.append(
            "sem_contato_comercial_confirmado"
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
        and not website_verified
        and has_commercial_whatsapp
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

    elif has_commercial_whatsapp and not website_verified:
        problem = (
            "WhatsApp comercial confirmado, mas "
            "site próprio não foi encontrado."
        )

        offer = "SITE_EXPRESS"

    elif (
        phone_verified
        and not website_verified
        and not has_commercial_whatsapp
    ):
        problem = (
            "Telefone da entidade confirmado, mas "
            "WhatsApp comercial ainda precisa ser validado."
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
        whatsapp=whatsapp,
        whatsapp_status=whatsapp_status,
        whatsapp_confidence=whatsapp_confidence,
        commercial_contact_status=commercial_contact_status,
        commercial_contact_confidence=commercial_contact_confidence,
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
    niche: NicheConfig,
) -> list[Opportunity]:
    opportunities = [
        score_site_express(
            row,
            niche,
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
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
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
        "whatsapp",
        "whatsapp_status",
        "whatsapp_confidence",
        "commercial_contact_status",
        "commercial_contact_confidence",
        "website",
        "website_status",
        "instagram",
        "instagram_status",
        "reasons",
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
                    "whatsapp": item.whatsapp,
                    "whatsapp_status": (
                        item.whatsapp_status
                    ),
                    "whatsapp_confidence": (
                        item.whatsapp_confidence
                    ),
                    "commercial_contact_status": (
                        item.commercial_contact_status
                    ),
                    "commercial_contact_confidence": (
                        item.commercial_contact_confidence
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
    city: str,
    niche: NicheConfig,
    output_file: Path,
    min_score: int = 70,
) -> None:
    approach = [
        item
        for item in opportunities
        if item.action == "ABORDAR"
        and item.score >= min_score
    ]

    print(
        "LEADFLOW ZERO — OPORTUNIDADES"
    )
    print(
        f"{city} • {niche.key.replace('_', ' ').title()}"
    )
    print()
    print(
        f"{len(approach)} oportunidades acionáveis"
    )

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

        if (
            item.whatsapp_status == "VERIFIED"
            and item.commercial_contact_status == "VERIFIED"
        ):
            print(
                f"WhatsApp   : "
                f"{format_phone(item.phone)} ✓"
            )

        print(
            f"Comercial  : "
            f"{item.commercial_contact_status} "
            f"({item.commercial_contact_confidence})"
        )

        print(
            f"Site       : "
            f"{'próprio confirmado' if is_verified(item.website_status) else 'próprio não confirmado'}"
        )

        print(
            f"Problema   : "
            f"{item.problem}"
        )

        print(
            f"Oferta     : "
            f"{item.offer}"
        )

        print(
            f"Ação       : "
            f"{item.action}"
        )

    print()
    print(
        f"Arquivo salvo: "
        f"{output_file}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="opportunity",
        description=(
            "LeadFlow Zero — priorização "
            "comercial."
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
        "--min-score",
        type=int,
        default=70,
    )

    return parser.parse_args()


def run(
    city: str,
    niche_name: str,
    min_score: int = 70,
) -> tuple[list[Opportunity], Path]:
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

    rows = load_rows(
        input_file
    )

    opportunities = evaluate_rows(
        rows,
        niche,
    )

    save_results(
        opportunities,
        output_file,
    )

    print_report(
        opportunities,
        city,
        niche,
        output_file,
        min_score,
    )

    return opportunities, output_file


def main() -> None:
    args = parse_args()

    run(
        city=args.city,
        niche_name=args.niche,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
