from typing import List
import pandas as pd
import html

def df_to_html_table(df: pd.DataFrame, header=True) -> str:
    if df is None or df.empty:
        return "<p><em>No data available.</em></p>"
    styles = "border-collapse: collapse; width:100%;"
    thtd = "border:1px solid #ddd; padding:6px; text-align:left; font-size:13px;"
    head_html = ""
    if header:
        head_html = "<tr>" + "".join([f"<th style='{thtd}; background:#f5f5f5'>{html.escape(str(c))}</th>" for c in df.columns]) + "</tr>"
    body_rows = []
    for _, row in df.iterrows():
        body_cells = "".join([f"<td style='{thtd}'>{html.escape('' if pd.isna(v) else str(v))}</td>" for v in row])
        body_rows.append(f"<tr>{body_cells}</tr>")
    return f"<table style='{styles}'>{head_html}{''.join(body_rows)}</table>"

def clamp_top(df: pd.DataFrame, n=50) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.head(n)
