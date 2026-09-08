from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class NicheConfig:
    key: str
    aliases: tuple[str, ...]
    osm_tags: tuple[tuple[str, str], ...]
    context_terms: tuple[str, ...]
    institutional_terms: tuple[str, ...] = ()


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


NICHES: dict[str, NicheConfig] = {
    "dentistas": NicheConfig(
        key="dentistas",
        aliases=(
            "dentista",
            "dentistas",
            "odontologia",
            "clinica odontologica",
            "clinicas odontologicas",
        ),
        osm_tags=(
            ("amenity", "dentist"),
            ("healthcare", "dentist"),
        ),
        context_terms=(
            "odontologia",
            "odontologico",
            "odontologica",
            "dentista",
            "dental",
            "odonto",
            "clinica",
            "consultorio",
        ),
        institutional_terms=(
            "universidade",
            "faculdade",
            "governo",
            "prefeitura",
            "municipal",
            "estadual",
            "federal",
            "militar",
            "aeronautica",
        ),
    ),

    "lojas_de_moveis": NicheConfig(
        key="lojas_de_moveis",
        aliases=(
            "loja de moveis",
            "lojas de moveis",
            "moveis",
            "moveis planejados",
        ),
        osm_tags=(
            ("shop", "furniture"),
        ),
        context_terms=(
            "moveis",
            "movel",
            "furniture",
            "decoracao",
            "planejados",
            "casa",
            "interiores",
        ),
    ),

    "restaurantes": NicheConfig(
        key="restaurantes",
        aliases=(
            "restaurante",
            "restaurantes",
        ),
        osm_tags=(
            ("amenity", "restaurant"),
        ),
        context_terms=(
            "restaurante",
            "gastronomia",
            "comida",
            "delivery",
            "cardapio",
            "almoco",
            "jantar",
        ),
    ),

    "academias": NicheConfig(
        key="academias",
        aliases=(
            "academia",
            "academias",
            "gym",
        ),
        osm_tags=(
            ("leisure", "fitness_centre"),
        ),
        context_terms=(
            "academia",
            "fitness",
            "musculacao",
            "treino",
            "personal",
            "gym",
        ),
    ),

    "oficinas": NicheConfig(
        key="oficinas",
        aliases=(
            "oficina",
            "oficinas",
            "oficina mecanica",
            "oficinas mecanicas",
        ),
        osm_tags=(
            ("shop", "car_repair"),
        ),
        context_terms=(
            "oficina",
            "mecanica",
            "mecanico",
            "automotivo",
            "automotiva",
            "carro",
            "veiculo",
        ),
    ),
}


def resolve_niche(
    value: str,
) -> NicheConfig:
    wanted = normalize(
        value
    )

    for config in NICHES.values():
        candidates = {
            normalize(config.key),
            *(
                normalize(alias)
                for alias in config.aliases
            ),
        }

        if wanted in candidates:
            return config

    supported = ", ".join(
        sorted(NICHES)
    )

    raise ValueError(
        f"Nicho não suportado: {value}. "
        f"Disponíveis: {supported}"
    )


def supported_niches() -> list[str]:
    return sorted(
        NICHES.keys()
    )
