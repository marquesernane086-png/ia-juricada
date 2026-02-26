"""Case Memory — Memória de caso/processo jurídico.

Mantém contexto contínuo de um processo/caso jurídico:
- partes, tema, histórico de perguntas, fundamentos utilizados.

Salvo em MongoDB separado do vetor doutrinário.
Permite acompanhamento contínuo de um processo.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Will be set from server.py
_db = None


def set_db(database):
    global _db
    _db = database


class CaseMemory:
    """Memória persistente de caso jurídico."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self._data = None

    async def load(self) -> Dict:
        """Carrega caso do MongoDB."""
        if _db is None:
            return {}
        if self._data is None:
            self._data = await _db.cases.find_one({"case_id": self.case_id}, {"_id": 0})
            if not self._data:
                self._data = {
                    "case_id": self.case_id,
                    "titulo": "",
                    "partes": {"autor": "", "reu": "", "outros": []},
                    "tema_juridico": "",
                    "area_direito": "",
                    "historico_perguntas": [],
                    "fundamentos_utilizados": [],
                    "normas_citadas": [],
                    "autores_citados": [],
                    "status": "ativo",
                    "criado_em": datetime.now(timezone.utc).isoformat(),
                    "atualizado_em": datetime.now(timezone.utc).isoformat(),
                }
                await _db.cases.insert_one(self._data)
        return self._data

    async def add_question(self, question: str, answer_summary: str = "", sources: List[str] = None):
        """Registra pergunta e resposta no histórico do caso."""
        data = await self.load()
        entry = {
            "pergunta": question,
            "resumo_resposta": answer_summary[:500],
            "fontes": sources or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        data["historico_perguntas"].append(entry)
        data["atualizado_em"] = datetime.now(timezone.utc).isoformat()

        # Limitar histórico a 50 últimas perguntas
        if len(data["historico_perguntas"]) > 50:
            data["historico_perguntas"] = data["historico_perguntas"][-50:]

        await _db.cases.update_one(
            {"case_id": self.case_id},
            {"$set": data},
            upsert=True
        )

    async def add_fundamento(self, autor: str, obra: str, ano: int = 0, artigo: str = ""):
        """Registra fundamento utilizado no caso."""
        data = await self.load()
        fundamento = {"autor": autor, "obra": obra, "ano": ano, "artigo": artigo}
        if fundamento not in data["fundamentos_utilizados"]:
            data["fundamentos_utilizados"].append(fundamento)
            await _db.cases.update_one(
                {"case_id": self.case_id},
                {"$set": {"fundamentos_utilizados": data["fundamentos_utilizados"]}}
            )

    async def set_partes(self, autor: str = "", reu: str = "", outros: List[str] = None):
        """Define as partes do processo."""
        await _db.cases.update_one(
            {"case_id": self.case_id},
            {"$set": {"partes": {"autor": autor, "reu": reu, "outros": outros or []}}},
            upsert=True
        )

    async def set_tema(self, tema: str, area: str = ""):
        """Define tema jurídico do caso."""
        await _db.cases.update_one(
            {"case_id": self.case_id},
            {"$set": {"tema_juridico": tema, "area_direito": area}},
            upsert=True
        )

    async def get_context(self) -> str:
        """Gera contexto do caso para enviar ao LLM."""
        data = await self.load()
        parts = []
        parts.append(f"CASO: {data.get('titulo', self.case_id)}")
        partes = data.get("partes", {})
        if partes.get("autor"):
            parts.append(f"Autor: {partes['autor']}")
        if partes.get("reu"):
            parts.append(f"Réu: {partes['reu']}")
        if data.get("tema_juridico"):
            parts.append(f"Tema: {data['tema_juridico']}")

        hist = data.get("historico_perguntas", [])[-5:]  # últimas 5
        if hist:
            parts.append("\nPerguntas anteriores:")
            for h in hist:
                parts.append(f"  Q: {h['pergunta'][:100]}")
                if h.get("resumo_resposta"):
                    parts.append(f"  R: {h['resumo_resposta'][:150]}")

        return "\n".join(parts)


async def get_case(case_id: str) -> CaseMemory:
    """Factory para obter memória de caso."""
    case = CaseMemory(case_id)
    await case.load()
    return case


async def list_cases(limit: int = 20) -> List[Dict]:
    """Lista casos ativos."""
    if _db is None:
        return []
    cursor = _db.cases.find({}, {"_id": 0}).sort("atualizado_em", -1).limit(limit)
    return await cursor.to_list(limit)
