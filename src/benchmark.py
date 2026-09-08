from __future__ import annotations

import csv
from pathlib import Path


# ============================================================
# FILES
# ============================================================

GROUND_TRUTH_FILE = Path(
    "data/ground_truth/verification.csv"
)

VERIFIED_FILE = Path(
    "data/processed/manaus_dentistas_verified_v2.csv"
)


# ============================================================
# VERIFIER v2.1 FIELD MAPPING
# ============================================================

FIELD_MAP = {
    "phone": {
        "candidate": "phone_candidate_v2",
        "status": "phone_verification_status_v2",
    },
    "website": {
        "candidate": "website_candidate_v2",
        "status": "website_verification_status_v2",
    },
    "instagram": {
        "candidate": "instagram_candidate_v2",
        "status": "instagram_verification_status_v2",
    },
    "email": {
        "candidate": "email_candidate_v2",
        "status": "email_verification_status_v2",
    },
}


# Somente estes estados contam como uma previsão positiva.
#
# REVIEW continua sendo negativo para o benchmark.
# Isso é proposital: não queremos considerar um candidato
# "correto" enquanto o verifier ainda pede revisão.
POSITIVE_STATUSES = {
    "VERIFIED",
    "OSM_MATCH",
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_value(
    value: str,
    kind: str,
) -> str:
    value = (
        value or ""
    ).strip().lower()

    if kind == "phone":
        return "".join(
            char
            for char in value
            if char.isdigit()
        )

    if kind == "website":
        return value.rstrip("/")

    if kind == "instagram":
        return (
            value
            .replace("@", "")
            .strip("/")
        )

    return value


# ============================================================
# CSV
# ============================================================

def load_csv(
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


# ============================================================
# SAFE DIVISION
# ============================================================

def safe_divide(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return numerator / denominator


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    truth = load_csv(
        GROUND_TRUTH_FILE
    )

    verified = load_csv(
        VERIFIED_FILE
    )

    by_name = {
        row["name"]: row
        for row in verified
    }

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    ignored = 0
    missing_leads = 0

    errors: list[dict[str, str]] = []

    print()
    print("=" * 76)
    print(
        "LEADFLOW ZERO — "
        "VERIFICATION BENCHMARK v2.1"
    )
    print("=" * 76)

    print()
    print(
        f"Ground truth : {GROUND_TRUTH_FILE}"
    )
    print(
        f"Verifier     : {VERIFIED_FILE}"
    )

    # ========================================================
    # EVALUATION
    # ========================================================

    for expected_row in truth:
        expected = (
            expected_row["expected"]
            .strip()
            .upper()
        )

        # UNKNOWN não entra nas métricas.
        if expected == "UNKNOWN":
            ignored += 1
            continue

        lead_name = expected_row[
            "lead"
        ]

        kind = (
            expected_row["type"]
            .strip()
            .lower()
        )

        if kind not in FIELD_MAP:
            raise ValueError(
                f"Tipo desconhecido no ground truth: "
                f"{kind}"
            )

        lead = by_name.get(
            lead_name
        )

        if not lead:
            missing_leads += 1

            print(
                f"LEAD NÃO ENCONTRADO: "
                f"{lead_name}"
            )

            continue

        config = FIELD_MAP[
            kind
        ]

        candidate = normalize_value(
            lead.get(
                config["candidate"],
                "",
            ),
            kind,
        )

        expected_value = normalize_value(
            expected_row["value"],
            kind,
        )

        status = (
            lead.get(
                config["status"],
                "NONE",
            )
            .strip()
            .upper()
        )

        same_value = (
            candidate
            == expected_value
        )

        # Só conta como previsão positiva se:
        #
        # 1. o valor selecionado pelo verifier é exatamente
        #    o valor presente no ground truth;
        #
        # 2. o verifier realmente o marcou como positivo.
        predicted_positive = (
            same_value
            and status
            in POSITIVE_STATUSES
        )

        actual_positive = (
            expected == "TRUE"
        )

        # ====================================================
        # CONFUSION MATRIX
        # ====================================================

        if (
            actual_positive
            and predicted_positive
        ):
            tp += 1
            result = "TP"

        elif (
            not actual_positive
            and predicted_positive
        ):
            fp += 1
            result = "FP"

        elif (
            actual_positive
            and not predicted_positive
        ):
            fn += 1
            result = "FN"

        else:
            tn += 1
            result = "TN"

        # ====================================================
        # SAVE ERRORS
        # ====================================================

        if result in {
            "FP",
            "FN",
        }:
            errors.append(
                {
                    "result": result,
                    "lead": lead_name,
                    "type": kind,
                    "expected_value": (
                        expected_value
                    ),
                    "candidate": candidate,
                    "status": status,
                }
            )

    # ========================================================
    # METRICS
    # ========================================================

    precision = safe_divide(
        tp,
        tp + fp,
    )

    recall = safe_divide(
        tp,
        tp + fn,
    )

    specificity = safe_divide(
        tn,
        tn + fp,
    )

    f1 = (
        2
        * precision
        * recall
        / (precision + recall)
        if precision + recall
        else 0.0
    )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("-" * 76)
    print("CONFUSION MATRIX")
    print("-" * 76)

    print(
        f"TP: {tp}"
    )

    print(
        f"FP: {fp}"
    )

    print(
        f"TN: {tn}"
    )

    print(
        f"FN: {fn}"
    )

    print(
        f"Ignorados (UNKNOWN): "
        f"{ignored}"
    )

    print(
        f"Leads ausentes: "
        f"{missing_leads}"
    )

    print()
    print("-" * 76)
    print("MÉTRICAS")
    print("-" * 76)

    print(
        f"Precision   : "
        f"{precision:.1%}"
    )

    print(
        f"Recall      : "
        f"{recall:.1%}"
    )

    print(
        f"Specificity : "
        f"{specificity:.1%}"
    )

    print(
        f"F1          : "
        f"{f1:.1%}"
    )

    # ========================================================
    # ERRORS
    # ========================================================

    if errors:
        print()
        print("-" * 76)
        print("ERROS")
        print("-" * 76)

        for error in errors:
            print(
                f"{error['result']} | "
                f"{error['lead']} | "
                f"{error['type']} | "
                f"esperado={error['expected_value']} | "
                f"candidato={error['candidate'] or 'N/D'} | "
                f"status={error['status']}"
            )

    else:
        print()
        print("-" * 76)
        print(
            "Nenhum FP/FN encontrado."
        )

    # ========================================================
    # MVP TARGET
    # ========================================================

    print()
    print("-" * 76)
    print("META DO MVP")
    print("-" * 76)

    precision_ok = (
        precision >= 0.95
    )

    recall_ok = (
        recall >= 0.80
    )

    fp_ok = (
        fp == 0
    )

    print(
        f"Precision >= 95% : "
        f"{'PASS' if precision_ok else 'FAIL'}"
    )

    print(
        f"Recall >= 80%    : "
        f"{'PASS' if recall_ok else 'FAIL'}"
    )

    print(
        f"FP == 0          : "
        f"{'PASS' if fp_ok else 'FAIL'}"
    )

    mvp_pass = (
        precision_ok
        and recall_ok
        and fp_ok
    )

    print()
    print(
        "RESULTADO: "
        + (
            "VERIFIER MVP APROVADO"
            if mvp_pass
            else "VERIFIER MVP AINDA NÃO APROVADO"
        )
    )

    print()
    print("=" * 76)


if __name__ == "__main__":
    main()
