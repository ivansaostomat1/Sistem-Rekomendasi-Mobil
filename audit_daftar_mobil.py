# file: audit_daftar_mobil.py
import json
import pandas as pd
from loaders import load_specs
from bot_carinfo import _collect_data_issues  # pakai ulang logic yang sama

specs = load_specs()
rows = []
for i, row in specs.iterrows():
    issues = _collect_data_issues(row.to_dict())
    if issues:
        rows.append({
            "brand": row.get("brand"),
            "type_model": row.get("type model") or row.get("type_model") or row.get("model"),
            "issues": " | ".join(issues),
        })

df_report = pd.DataFrame(rows)
df_report.to_csv("report_cacat_data.csv", index=False)
print("Selesai. Lihat report_cacat_data.csv untuk list mobil yang perlu dicek.")
