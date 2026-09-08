import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from src.niches import resolve_niche
from src.opportunity import score_site_express
from src.whatsapp import br_phone_digits, br_phone_international, resolve_row


PHONE = "92991234567"
WA_PHONE = "5592991234567"
OTHER_WA_PHONE = "5592987654321"


def base_row(
    **overrides,
):
    row = {
        "name": "Criare Móveis",
        "phone_candidate_v2": PHONE,
        "phone_verification_score_v2": "93",
        "phone_verification_status_v2": "VERIFIED",
        "website_candidate_v2": "",
        "website_verification_score_v2": "0",
        "website_verification_status_v2": "NONE",
        "instagram_candidate_v2": "",
        "instagram_verification_score_v2": "0",
        "instagram_verification_status_v2": "NONE",
        "email_candidate_v2": "",
        "email_verification_score_v2": "0",
        "email_verification_status_v2": "NONE",
    }
    row.update(
        overrides
    )
    return row


def with_result(
    row,
    label,
    url,
    title,
    snippet,
):
    search_type, position = label.split(
        ":"
    )
    prefix = f"{search_type}_result_{position}"
    return {
        **row,
        f"{prefix}_url": url,
        f"{prefix}_title": title,
        f"{prefix}_snippet": snippet,
    }


def resolve(
    row,
    niche_name="lojas de móveis",
):
    return resolve_row(
        row,
        "Manaus",
        resolve_niche(niche_name),
    )


def test_phone_normalization():
    assert br_phone_digits("(92) 99123-4567") == PHONE
    assert br_phone_international("(92) 99123-4567") == WA_PHONE


def test_a_phone_verified_without_whatsapp_evidence_is_not_verified():
    result = resolve(
        base_row()
    )

    assert result["whatsapp_status"] == "NOT_FOUND"
    assert result["commercial_contact_status"] == "NOT_FOUND"


def test_b_mobile_phone_without_whatsapp_evidence_is_not_verified():
    result = resolve(
        base_row(
            phone_candidate_v2="92998765432",
        )
    )

    assert result["whatsapp_status"] != "VERIFIED"


def test_c_query_whatsapp_is_not_evidence():
    row = with_result(
        base_row(
            contact_query='"Criare Móveis" Manaus telefone WhatsApp',
        ),
        "contact:1",
        "https://example.com/criare",
        "Criare Móveis Manaus",
        "Telefone (92) 99123-4567.",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] != "VERIFIED"


def test_d_divergent_wa_me_does_not_verify():
    row = with_result(
        base_row(),
        "contact:1",
        "https://example.com/criare",
        "Criare Móveis Manaus",
        f"Contato https://wa.me/{OTHER_WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] != "VERIFIED"


def test_e_first_party_wa_me_exact_phone_can_verify_commercial():
    row = with_result(
        base_row(
            website_candidate_v2="https://criare.example",
            website_verification_status_v2="VERIFIED",
        ),
        "contact:1",
        "https://criare.example/contato",
        "Criare Móveis Manaus",
        f"Fale conosco pelo WhatsApp https://wa.me/{WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "VERIFIED"
    assert result["commercial_contact_status"] == "VERIFIED"


def test_f_first_party_exact_phone_with_commercial_whatsapp_text_verifies():
    row = with_result(
        base_row(
            website_candidate_v2="https://criare.example",
            website_verification_status_v2="VERIFIED",
        ),
        "contact:1",
        "https://criare.example/contato",
        "Criare Móveis Manaus",
        "Contato WhatsApp: (92) 99123-4567",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "VERIFIED"
    assert result["commercial_contact_status"] == "VERIFIED"


def test_g_whatsapp_verified_without_commercial_context_is_not_commercial():
    row = with_result(
        base_row(
            website_candidate_v2="https://criare.example",
            website_verification_status_v2="VERIFIED",
        ),
        "contact:1",
        "https://criare.example/sobre",
        "Criare Móveis Manaus",
        f"WhatsApp https://wa.me/{WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "VERIFIED"
    assert result["commercial_contact_status"] != "VERIFIED"


def test_h_different_company_or_city_does_not_verify():
    row = with_result(
        base_row(),
        "contact:1",
        "https://directory.example/outro",
        "Outra Empresa Belém",
        "WhatsApp (92) 99123-4567",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] != "VERIFIED"
    assert result["commercial_contact_status"] != "VERIFIED"


def test_i_single_directory_is_not_commercial_verified():
    row = with_result(
        base_row(),
        "contact:1",
        "https://directory.example/criare",
        "Criare Móveis Manaus",
        "Criare Móveis - WhatsApp (92) 99123-4567",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "REVIEW"
    assert result["commercial_contact_status"] == "REVIEW"


def test_j_two_independent_directories_can_verify_with_commercial_context():
    row = with_result(
        base_row(),
        "contact:1",
        "https://directory-one.example/criare",
        "Criare Móveis Manaus",
        "Contato WhatsApp (92) 99123-4567",
    )
    row = with_result(
        row,
        "contact:2",
        "https://directory-two.example/criare",
        "Criare Móveis Manaus",
        "Vendas WhatsApp (92) 99123-4567",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "VERIFIED"
    assert result["commercial_contact_status"] == "VERIFIED"


def test_k_first_party_wa_me_other_phone_does_not_validate_candidate():
    row = with_result(
        base_row(
            website_candidate_v2="https://criare.example",
            website_verification_status_v2="VERIFIED",
        ),
        "contact:1",
        "https://criare.example/contato",
        "Criare Móveis Manaus",
        f"Fale pelo WhatsApp https://wa.me/{OTHER_WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] != "VERIFIED"


def test_l_unverified_instagram_is_not_first_party():
    row = with_result(
        base_row(
            instagram_candidate_v2="criare.manaus",
            instagram_verification_status_v2="REVIEW",
        ),
        "digital:1",
        "https://www.instagram.com/criare.manaus/",
        "Criare Móveis Manaus",
        f"Contato WhatsApp https://wa.me/{WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "REVIEW"
    assert result["commercial_contact_status"] == "REVIEW"


def test_m_verified_instagram_can_be_first_party():
    row = with_result(
        base_row(
            instagram_candidate_v2="criare.manaus",
            instagram_verification_status_v2="VERIFIED",
        ),
        "digital:1",
        "https://www.instagram.com/criare.manaus/",
        "Criare Móveis Manaus",
        f"Atendimento WhatsApp https://wa.me/{WA_PHONE}",
    )

    result = resolve(
        row
    )

    assert result["whatsapp_status"] == "VERIFIED"
    assert result["commercial_contact_status"] == "VERIFIED"


def test_fametro_single_secondary_directory_regression():
    row = with_result(
        base_row(
            name="Clínica Odontológica Fametro",
            phone_candidate_v2="92992438217",
        ),
        "contact:1",
        "https://saudecidade.com/manaus/dentista/clinica-odontologica-fametro",
        "Clínica Odontológica Fametro — Dentista em Manaus, AM",
        "Informações de contato Manaus, AM Telefone +5592992438217 Ligar agora WhatsApp Ver no mapa",
    )

    result = resolve(
        row,
        "dentistas",
    )

    assert result["whatsapp_status"] != "VERIFIED"
    assert result["commercial_contact_status"] != "VERIFIED"


def test_verified_phone_is_not_commercial_whatsapp():
    niche = resolve_niche("lojas de móveis")
    row = {
        "name": "Criare Móveis",
        "phone_candidate_v2": "9236315343",
        "phone_verification_score_v2": "93",
        "phone_verification_status_v2": "VERIFIED",
        "website_candidate_v2": "",
        "website_verification_score_v2": "0",
        "website_verification_status_v2": "NONE",
        "instagram_candidate_v2": "criare.manaus",
        "instagram_verification_score_v2": "73",
        "instagram_verification_status_v2": "REVIEW",
        "contact_result_1_title": "Criare Móveis Manaus",
        "contact_result_1_url": "https://example.com/criare",
        "contact_result_1_snippet": (
            "Telefone (92) 3631-5343. WhatsApp (92) 98246-0304."
        ),
    }

    resolved = {
        **row,
        **resolve_row(
            row,
            "Manaus",
            niche,
        ),
    }
    opportunity = score_site_express(
        resolved,
        niche,
    )

    assert resolved["whatsapp_status"] == "REJECTED"
    assert resolved["commercial_contact_status"] == "REJECTED"
    assert opportunity.action == "REVISAR"


if __name__ == "__main__":
    test_phone_normalization()
    test_a_phone_verified_without_whatsapp_evidence_is_not_verified()
    test_b_mobile_phone_without_whatsapp_evidence_is_not_verified()
    test_c_query_whatsapp_is_not_evidence()
    test_d_divergent_wa_me_does_not_verify()
    test_e_first_party_wa_me_exact_phone_can_verify_commercial()
    test_f_first_party_exact_phone_with_commercial_whatsapp_text_verifies()
    test_g_whatsapp_verified_without_commercial_context_is_not_commercial()
    test_h_different_company_or_city_does_not_verify()
    test_i_single_directory_is_not_commercial_verified()
    test_j_two_independent_directories_can_verify_with_commercial_context()
    test_k_first_party_wa_me_other_phone_does_not_validate_candidate()
    test_l_unverified_instagram_is_not_first_party()
    test_m_verified_instagram_can_be_first_party()
    test_fametro_single_secondary_directory_regression()
    test_verified_phone_is_not_commercial_whatsapp()
