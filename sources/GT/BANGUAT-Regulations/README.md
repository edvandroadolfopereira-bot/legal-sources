# GT/BANGUAT-Regulations — Banco de Guatemala, Marco Legal del Sistema Financiero

Full text of the banking and financial-system legal framework published by the
**Banco de Guatemala (BANGUAT)**, the central bank of Guatemala. These are the
monetary, banking, and financial-sector statutes that constitute the legal basis
for the bank's operation and for the supervision of the Guatemalan financial
system.

## What this captures

The 16 laws on BANGUAT's [*Leyes Bancarias y Financieras*](https://banguat.gob.gt/page/leyes-bancarias-y-financieras)
page, including:

- Ley Orgánica del Banco de Guatemala (Decreto 16-2002)
- Ley Monetaria (Decreto 17-2002)
- Ley de Supervisión Financiera (Decreto 18-2002)
- Ley de Bancos y Grupos Financieros (Decreto 19-2002)
- Ley de Sociedades Financieras Privadas
- Ley de Almacenes Generales de Depósito
- Ley de Libre Negociación de Divisas
- Ley Contra el Lavado de Dinero u Otros Activos (Decreto 67-2001)
- Ley para Prevenir y Reprimir el Financiamiento del Terrorismo (Decreto 58-2005)
- Ley de la Actividad Aseguradora (Decreto 25-2010)
- Ley de Garantías Mobiliarias (Decreto 51-2007)
- and related decrees/acuerdos.

Each law is a text-based PDF; full text is extracted with `pdfplumber`
(2.7k–150k characters per law).

## What is excluded (and why)

BANGUAT's own **resoluciones** — the Junta Monetaria archive
(`/page/ano-YYYY`) and the Gerencia General archive
(`/page/resoluciones-de-gerencia-general-*`) — are published **only as
scanned-image PDFs with no embedded text layer**. `pdfplumber` extracts 0–6
characters from them, so they cannot satisfy the full-text requirement and are
intentionally excluded. Should BANGUAT publish OCR'd or text versions in the
future, those archives could be added.

## Usage

```bash
python bootstrap.py test               # connectivity + first-law extraction
python bootstrap.py bootstrap --sample # 15 sample records
python bootstrap.py bootstrap --full   # all 16 laws
```

## License

Guatemalan statutes are official legal texts in the public domain. They are
published here by a public institution (the Banco de Guatemala) on its
institutional website for public use.

[Open Government Data — Banco de Guatemala](https://banguat.gob.gt/) — official
financial-sector legislation; attribution to the Banco de Guatemala is
appropriate. Commercial use permitted.
