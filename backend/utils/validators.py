"""Validadores reutilizáveis: CPF, CNPJ, datas, valores."""
import re
from typing import Optional

def validar_cpf(cpf: str) -> bool:
    n = re.sub(r'\D', '', cpf)
    if len(n) != 11 or len(set(n)) == 1:
        return False
    for i in range(9, 11):
        s = sum(int(n[j]) * (i + 1 - j) for j in range(i))
        if int(n[i]) != (s * 10 % 11) % 10:
            return False
    return True

def validar_cnpj(cnpj: str) -> bool:
    n = re.sub(r'\D', '', cnpj)
    if len(n) != 14 or len(set(n)) == 1:
        return False
    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pesos2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    for pesos, pos in [(pesos1, 12), (pesos2, 13)]:
        s = sum(int(n[i]) * pesos[i] for i in range(len(pesos)))
        d = 11 - (s % 11)
        if int(n[pos]) != (0 if d > 9 else d):
            return False
    return True

def normalizar_valor(v: str) -> Optional[float]:
    """'R$ 1.500,75' → 1500.75"""
    v = re.sub(r'[R$\s]', '', v)
    v = v.replace('.', '').replace(',', '.')
    try:
        return float(v)
    except Exception:
        return None

def normalizar_data(d: str) -> Optional[str]:
    """DD/MM/YYYY ou YYYY-MM-DD → YYYY-MM-DD"""
    m = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', d)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r'(\d{4})[/\-](\d{2})[/\-](\d{2})', d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None
