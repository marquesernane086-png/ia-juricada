"""Cadastro de Magistrados — Base inteligente de julgadores

Cria e mantem base estruturada de magistrados para enriquecer
a IA com perfil decisorio, tendencia e estatisticas.

Uso:
    from cadastro_magistrados import MagistradoRegistry
    
    registry = MagistradoRegistry()
    registry.registrar_magistrado("Min. Fulano", "STJ", "Ministro")
    registry.atualizar_estatisticas("Min. Fulano", "procedente", "Direito Civil")
    print(registry.get_perfil("Min. Fulano"))
"""

import json
import os
import hashlib
import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

DATABASE_FILE = "magistrados.json"


def _id_magistrado(nome: str) -> str:
    return hashlib.sha256(nome.lower().strip().encode()).hexdigest()[:16]


class MagistradoRegistry:
    """Base de dados de magistrados com perfil decisorio."""

    def __init__(self, db_path: str = DATABASE_FILE):
        self.db_path = db_path
        self.magistrados: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                self.magistrados = json.load(f)

    def _save(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.magistrados, f, ensure_ascii=False, indent=2)

    def registrar_magistrado(
        self, nome: str, tribunal: str, cargo: str,
        area_predominante: str = ""
    ) -> str:
        """Registra um novo magistrado ou atualiza existente."""
        mid = _id_magistrado(nome)

        if mid not in self.magistrados:
            self.magistrados[mid] = {
                "id_magistrado": mid,
                "nome": nome.strip(),
                "tribunal": tribunal,
                "cargo": cargo,
                "area_predominante": area_predominante,
                "tendencia_jurisprudencial": "indefinida",
                "decisoes_indexadas": 0,
                "estatisticas": {
                    "total": 0,
                    "procedente": 0,
                    "improcedente": 0,
                    "parcialmente_procedente": 0,
                    "extinto": 0,
                },
                "areas": {},
                "criado_em": datetime.now().isoformat(),
                "atualizado_em": datetime.now().isoformat(),
            }
            logger.info(f"Magistrado registrado: {nome} ({tribunal})")
        else:
            self.magistrados[mid]["tribunal"] = tribunal
            self.magistrados[mid]["cargo"] = cargo
            if area_predominante:
                self.magistrados[mid]["area_predominante"] = area_predominante

        self._save()
        return mid

    def atualizar_estatisticas(
        self, nome: str, resultado: str, area: str = ""
    ):
        """Atualiza estatisticas apos indexar uma decisao.
        
        resultado: procedente, improcedente, parcialmente_procedente, extinto
        """
        mid = _id_magistrado(nome)

        if mid not in self.magistrados:
            self.registrar_magistrado(nome, "desconhecido", "desconhecido")

        mag = self.magistrados[mid]
        mag["decisoes_indexadas"] += 1
        mag["estatisticas"]["total"] += 1

        resultado_lower = resultado.lower().strip()
        if "procedente" in resultado_lower and "improcedente" not in resultado_lower:
            if "parcial" in resultado_lower:
                mag["estatisticas"]["parcialmente_procedente"] += 1
            else:
                mag["estatisticas"]["procedente"] += 1
        elif "improcedente" in resultado_lower:
            mag["estatisticas"]["improcedente"] += 1
        elif "extinto" in resultado_lower:
            mag["estatisticas"]["extinto"] += 1

        # Area tracking
        if area:
            if area not in mag["areas"]:
                mag["areas"][area] = 0
            mag["areas"][area] += 1

            # Update predominant area
            if mag["areas"]:
                mag["area_predominante"] = max(mag["areas"], key=mag["areas"].get)

        # Update tendency
        stats = mag["estatisticas"]
        total = stats["total"]
        if total >= 5:
            proc_rate = (stats["procedente"] + stats["parcialmente_procedente"]) / total
            if proc_rate > 0.65:
                mag["tendencia_jurisprudencial"] = "favoravel_autor"
            elif proc_rate < 0.35:
                mag["tendencia_jurisprudencial"] = "favoravel_reu"
            else:
                mag["tendencia_jurisprudencial"] = "equilibrada"

        mag["atualizado_em"] = datetime.now().isoformat()
        self._save()

    def get_perfil(self, nome: str) -> Optional[Dict]:
        """Retorna perfil completo do magistrado."""
        mid = _id_magistrado(nome)
        return self.magistrados.get(mid)

    def get_por_tribunal(self, tribunal: str) -> List[Dict]:
        """Lista magistrados de um tribunal."""
        return [
            m for m in self.magistrados.values()
            if m["tribunal"].upper() == tribunal.upper()
        ]

    def get_tendencia(self, nome: str) -> str:
        """Retorna tendencia do magistrado."""
        perfil = self.get_perfil(nome)
        if not perfil:
            return "desconhecido"
        return perfil.get("tendencia_jurisprudencial", "indefinida")

    def listar_todos(self) -> List[Dict]:
        """Lista todos os magistrados."""
        return sorted(
            self.magistrados.values(),
            key=lambda m: m.get("decisoes_indexadas", 0),
            reverse=True
        )

    def stats(self) -> Dict:
        """Estatisticas gerais."""
        total = len(self.magistrados)
        tribunais = defaultdict(int)
        for m in self.magistrados.values():
            tribunais[m["tribunal"]] += 1
        return {
            "total_magistrados": total,
            "por_tribunal": dict(tribunais),
            "com_decisoes": sum(1 for m in self.magistrados.values() if m["decisoes_indexadas"] > 0),
        }


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    registry = MagistradoRegistry()

    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(registry.stats(), indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "listar":
        for m in registry.listar_todos():
            print(f"  {m['nome']} ({m['tribunal']}) - {m['decisoes_indexadas']} decisoes - {m['tendencia_jurisprudencial']}")
    else:
        print("Uso:")
        print("  python cadastro_magistrados.py stats")
        print("  python cadastro_magistrados.py listar")
        print(f"\nMagistrados cadastrados: {len(registry.magistrados)}")
