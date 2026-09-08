"""
Glossary Labels seed (v3.14).

Seeds a profile's Glossary Labels + multilingual member terms, so the matcher can
stamp a single canonical label (e.g. "SGK") regardless of which language/spelling of a
term appears in the source. Idempotent: labels and terms use INSERT-OR-IGNORE semantics.

The TR/HCM seed below was supplied by the LPM. Run:
    python3 -m agents.glossary_labels_seed <profile_id>       # defaults to TR/HCM seed
"""

import sys

from configurations.db import (
    get_connection, create_schema_if_needed, add_label, add_glossary_term,
)

# Canonical label (English) → member terms (multilingual). Any term hit stamps the label.
TR_HCM_SEED: dict[str, list[str]] = {
    "SGK": ["SGK", "SSK", "SSI", "Social Security", "Sosyal Güvenlik",
            "Sosyal Güvenlik Kurumu", "Health Insurance", "sağlık sigortası",
            "Retirement", "emeklilik", "Premium Support", "prim desteği"],
    "Tax": ["Income Tax", "gelir vergisi", "Gelir Vergisi Oranları", "Tax Base",
            "vergi matrahı", "Tax Exemption", "vergi istisnası", "Tax Withholding",
            "vergi kesintisi", "Tax Payer", "VERGİ", "Vergi Dilimleri", "Damga Vergisi"],
    "Wage": ["Payroll", "bordro", "Salary", "maaş", "Wage", "ücret", "Gross Salary",
             "brüt maaş", "Minimum Wage", "Asgari Ücret"],
    "Employment": ["Employment", "istihdam", "Employee", "çalışan", "Worker", "işçi",
                   "Employer", "işveren", "Labor Law", "İş kanunu", "Employment Contract",
                   "İş sözleşmesi", "Labor Contract", "Collective Agreement", "toplu sözleşme",
                   "İŞKUR", "Termination", "İşten çıkarma", "Severance Pay", "kıdem tazminatı",
                   "ihbar tazminatı", "Overtime", "fazla mesai"],
    "Leave": ["Annual Leave", "yıllık izin", "Maternity Leave", "doğum izni",
              "Paternity Leave", "babalık izni"],
    "Benefits": ["Meal Allowance", "Yemek yardımı", "Social Aid", "Social Aids", "sosyal yardım"],
    "R&D": ["R&D", "ARGE", "ARAŞTIRMA GELİŞTİRME"],
}

_TR_CHARS = set("çğıİöşüÇĞİÖŞÜ")


def _guess_lang(term: str) -> str:
    """Best-effort language tag for display only (not used for matching)."""
    return "tr" if any(c in _TR_CHARS for c in term) else "en"


def seed_labels(conn, profile_id: int, seed: dict[str, list[str]]) -> tuple[int, int]:
    """Create labels and their member terms. Returns (labels_written, terms_written)."""
    n_labels = n_terms = 0
    for label_name, terms in seed.items():
        label_id = add_label(conn, profile_id, label_name)
        n_labels += 1
        for term in terms:
            add_glossary_term(conn, profile_id, term.strip(),
                              lang=_guess_lang(term), label_id=label_id)
            # Unify any pre-existing same-text rows (other langs, unlabeled) under this label
            # so leftover flat glossary terms don't leak as their own labels.
            conn.execute(
                "UPDATE glossary_terms SET label_id=? "
                "WHERE profile_id=? AND lower(term)=lower(?) AND label_id IS NULL",
                (label_id, profile_id, term.strip()),
            )
            n_terms += 1
    conn.commit()
    return n_labels, n_terms


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m agents.glossary_labels_seed <profile_id>", file=sys.stderr)
        return 2
    profile_id = int(argv[1])
    conn = get_connection()
    create_schema_if_needed(conn)
    n_labels, n_terms = seed_labels(conn, profile_id, TR_HCM_SEED)
    print(f"✅ Seeded {n_labels} labels / {n_terms} terms for profile {profile_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
