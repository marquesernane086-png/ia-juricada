"""Future Metadata Schemas — Estruturas para indexação futura.

NÃO executar. Apenas definição de schemas.
Preparação para quando legislação e jurisprudência forem indexadas.
"""

from typing import Optional, List
from pydantic import BaseModel


# ============================================================
# LEGISLAÇÃO
# ============================================================

class LegislationMetadata(BaseModel):
    """Metadados esperados para artigos de lei."""
    tipo_documento: str = "lei"
    law_name: str = ""              # "Código Civil"
    law_number: str = ""            # "Lei 10.406/2002"
    article: str = ""               # "927"
    paragraph: str = ""             # "§ único"
    inciso: str = ""                # "I"
    alinea: str = ""                # "a"
    hierarchy_weight: float = 0.95  # CF=1.0, Lei=0.95, Decreto=0.90
    norm_type: str = "federal"      # federal, estadual, municipal
    vigencia: str = "ativa"         # ativa, revogada, parcialmente_revogada
    area: str = ""                  # Direito Civil, Penal, etc.
    artigos_relacionados: List[str] = []
    fonte: str = ""


# ============================================================
# JURISPRUDÊNCIA
# ============================================================

class JurisprudenceMetadata(BaseModel):
    """Metadados esperados para decisões judiciais."""
    tipo_documento: str = "jurisprudencia"
    court: str = ""                 # STF, STJ, TJSP
    judge: str = ""                 # nome do juiz/desembargador
    rapporteur: str = ""            # relator
    decision_date: str = ""         # "15/03/2024"
    process_number: str = ""        # "REsp 1234567/SP"
    classe_processual: str = ""     # REsp, HC, MS, ADI
    orgao_julgador: str = ""        # "3ª Turma"
    tipo_decisao: str = ""          # acordao, monocratica, despacho
    binding_level: str = "none"     # binding, persuasive, none
    precedent_type: str = ""        # sumula_vinculante, tema_repetitivo, IRDR
    ementa: str = ""
    tese: str = ""
    area: str = ""
    is_ementa: bool = False
    secao: str = ""                 # ementa, voto, dispositivo


# ============================================================
# SOURCE TYPE ENUM
# ============================================================

SOURCE_TYPES = {
    "doctrine": {
        "label": "Doutrina",
        "weight": 0.75,
        "description": "Livros e artigos acadêmicos",
    },
    "legislation": {
        "label": "Legislação",
        "weight": 0.95,
        "description": "Leis, códigos, decretos",
    },
    "jurisprudence": {
        "label": "Jurisprudência",
        "weight": 0.90,
        "description": "Decisões judiciais",
    },
    "constitution": {
        "label": "Constituição",
        "weight": 1.00,
        "description": "Constituição Federal",
    },
    "sumula": {
        "label": "Súmula",
        "weight": 0.95,
        "description": "Súmulas vinculantes e não vinculantes",
    },
}
