"""Procedural Deadline Agent — Contador de Prazo

⏱️ PREPARATION MODE — NOT CONNECTED TO RUNTIME

Calculates procedural deadlines under Brazilian procedural rules.
Uses business-day counting, considers weekends, allows regional holiday input,
and applies CPC deadline logic.
"""

ENABLED = False

from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import date, timedelta


# ============================================================
# SCHEMAS
# ============================================================

class DeadlineInput(BaseModel):
    """Input for deadline calculation."""
    deadline_type: str  # apelação, agravo, embargos, contestação, etc.
    publication_date: date  # data da publicação/intimação
    custom_days: Optional[int] = None  # prazo personalizado em dias úteis
    regional_holidays: List[date] = []  # feriados regionais
    is_fazenda_publica: bool = False  # dobra prazo (art. 183, CPC)
    is_defensoria: bool = False  # dobra prazo (art. 186, CPC)
    is_litisconsorcio_advogados_diferentes: bool = False  # não se aplica no PJe


class DeadlineOutput(BaseModel):
    """Output: calculated deadline."""
    deadline_type: str
    start_date: date  # primeiro dia útil após publicação
    final_date: date
    counted_days: int  # dias úteis contados
    total_calendar_days: int
    legal_basis: str
    observations: List[str] = []
    is_doubled: bool = False
    doubled_reason: str = ""


# ============================================================
# DEADLINE DATABASE (CPC)
# ============================================================

DEADLINES_CPC = {
    "apelação": {"days": 15, "basis": "Art. 1.003, §5º, CPC"},
    "agravo de instrumento": {"days": 15, "basis": "Art. 1.003, §5º, CPC"},
    "agravo interno": {"days": 15, "basis": "Art. 1.021, CPC"},
    "embargos de declaração": {"days": 5, "basis": "Art. 1.023, CPC"},
    "contestação": {"days": 15, "basis": "Art. 335, CPC"},
    "contestação (procedimento comum)": {"days": 15, "basis": "Art. 335, CPC"},
    "contestação (JEC)": {"days": 0, "basis": "Art. 30, Lei 9.099/95 (audiência)"},
    "recurso especial": {"days": 15, "basis": "Art. 1.003, §5º, CPC"},
    "recurso extraordinário": {"days": 15, "basis": "Art. 1.003, §5º, CPC"},
    "recurso ordinário": {"days": 15, "basis": "Art. 1.003, §5º, CPC"},
    "réplica": {"days": 15, "basis": "Art. 351, CPC"},
    "impugnação ao cumprimento": {"days": 15, "basis": "Art. 525, CPC"},
    "embargos à execução": {"days": 15, "basis": "Art. 915, CPC"},
    "mandado de segurança": {"days": 120, "basis": "Art. 23, Lei 12.016/09"},
    "habeas corpus": {"days": 0, "basis": "Sem prazo (pode ser impetrado a qualquer tempo)"},
    "ação rescisória": {"days": 730, "basis": "Art. 975, CPC (2 anos - dias corridos)"},
}


# ============================================================
# NATIONAL HOLIDAYS (Brazil)
# ============================================================

def get_national_holidays(year: int) -> List[date]:
    """Return national holidays for a given year."""
    holidays = [
        date(year, 1, 1),   # Confraternização Universal
        date(year, 4, 21),  # Tiradentes
        date(year, 5, 1),   # Dia do Trabalho
        date(year, 9, 7),   # Independência
        date(year, 10, 12), # Nossa Sra Aparecida
        date(year, 11, 2),  # Finados
        date(year, 11, 15), # Proclamação da República
        date(year, 12, 25), # Natal
    ]
    # TODO: Add Easter-based holidays (Carnaval, Sexta-Feira Santa, Corpus Christi)
    # These require Easter date calculation
    return holidays


# ============================================================
# CORE LOGIC
# ============================================================

def is_business_day(d: date, holidays: List[date]) -> bool:
    """Check if a date is a business day (not weekend, not holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if d in holidays:
        return False
    return True


def next_business_day(d: date, holidays: List[date]) -> date:
    """Get the next business day from a given date."""
    d = d + timedelta(days=1)
    while not is_business_day(d, holidays):
        d = d + timedelta(days=1)
    return d


def count_business_days(start: date, num_days: int, holidays: List[date]) -> date:
    """Count N business days from start date."""
    current = start
    counted = 0
    while counted < num_days:
        current = current + timedelta(days=1)
        if is_business_day(current, holidays):
            counted += 1
    return current


def calculate_deadline(deadline_input: DeadlineInput) -> DeadlineOutput:
    """Main entry point: calculate procedural deadline."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    # Get deadline info
    deadline_info = DEADLINES_CPC.get(deadline_input.deadline_type, {})
    base_days = deadline_input.custom_days or deadline_info.get("days", 15)
    legal_basis = deadline_info.get("basis", "")
    
    # Double for Fazenda Pública or Defensoria
    is_doubled = False
    doubled_reason = ""
    if deadline_input.is_fazenda_publica:
        base_days *= 2
        is_doubled = True
        doubled_reason = "Fazenda Pública (art. 183, CPC)"
    elif deadline_input.is_defensoria:
        base_days *= 2
        is_doubled = True
        doubled_reason = "Defensoria Pública (art. 186, CPC)"
    
    # Build holidays list
    year = deadline_input.publication_date.year
    all_holidays = get_national_holidays(year) + get_national_holidays(year + 1)
    all_holidays.extend(deadline_input.regional_holidays)
    
    # Start date: first business day after publication
    start = next_business_day(deadline_input.publication_date, all_holidays)
    
    # Count business days
    final = count_business_days(start, base_days, all_holidays)
    
    total_calendar = (final - deadline_input.publication_date).days
    
    observations = []
    if is_doubled:
        observations.append(f"Prazo dobrado: {doubled_reason}")
    
    return DeadlineOutput(
        deadline_type=deadline_input.deadline_type,
        start_date=start,
        final_date=final,
        counted_days=base_days,
        total_calendar_days=total_calendar,
        legal_basis=legal_basis,
        observations=observations,
        is_doubled=is_doubled,
        doubled_reason=doubled_reason,
    )
