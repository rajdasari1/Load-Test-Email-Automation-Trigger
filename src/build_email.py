import os
import pandas as pd
from jinja2 import Template
from datetime import datetime
from utils import df_to_html_table, clamp_top

# Adjust these paths or set via env
DATA_DIR = os.getenv("DATA_DIR", "data")
TEMPLATE_PATH = os.getenv("TEMPLATE_PATH", "src/email_template.html")
OUTPUT_HTML = os.getenv("OUTPUT_HTML", "out/email.html")

SENDER_NAME = os.getenv("SENDER_NAME", "Rajesh Dasari")
EXECUTED_USERS = os.getenv("EXECUTED_USERS", "5,000")
DEFECT_SHEET_NAME = os.getenv("DEFECT_SHEET_NAME", "NY_MECM_Performance_issues.xlsx")

# Email sending settings (if sending within this script via SMTP)
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME or "")
EMAIL_TO = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]
EMAIL_CC = [e.strip() for e in os.getenv("EMAIL_CC", "").split(",") if e.strip()]
EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", f"Member Portal Load Test Summary - {datetime.utcnow().strftime('%Y-%m-%d')}")

def read_csv_safe(path: str) -> pd.DataFrame:
    p = os.path.join(DATA_DIR, path)
    if not os.path.exists(p):
        return pd.DataFrame()
    return pd.read_csv(p)

def build_scenarios_table(load_df: pd.DataFrame) -> str:
    # Expected columns (adjust to your schema if different)
    # "Script Name","Portal","Achieved Volume","User distribution"
    colmap = {
        "Script Name": ["Script Name", "Script_Name", "script", "Scenario"],
        "Portal": ["Portal"],
        "Achieved Volume": ["Achieved Volume", "Achieved_Volume", "achieved"],
        "User distribution": ["User distribution", "User_distribution", "users"]
    }
    # Try to align columns
    def pick(cols):
        for c in cols:
            if c in load_df.columns:
                return c
        return None
    cols = {k: pick(v) for k, v in colmap.items()}

    # If there is a "Total" row, keep it at bottom by ordering later
    df = load_df.copy()
    # If your CSV has exact 4 columns with these names, this will just work.
    keep_cols = [cols["Script Name"], cols["Portal"], cols["Achieved Volume"], cols["User distribution"]]
    keep_cols = [c for c in keep_cols if c]
    if not keep_cols:
        return "<p><em>Scenarios not available (column mismatch).</em></p>"
    df = df[keep_cols]
    # Preserve total row (if labeled "Total" in script name)
    if cols["Script Name"] and cols["Script Name"] in df.columns:
        total_mask = df[cols["Script Name"]].astype(str).str.lower() == "total"
        total_df = df[total_mask]
        df = pd.concat([df[~total_mask], total_df], ignore_index=True)
    # Add header row matching your format
    df = df.rename(columns={
        cols["Script Name"]: "Script Name",
        cols["Portal"]: "Portal",
        cols["Achieved Volume"]: "Achieved Volume",
        cols["User distribution"]: "User distribution"
    })
    return df_to_html_table(df)

def build_load_summary(load_df: pd.DataFrame) -> tuple[str, str]:
    # Build two-run comparison for summary metrics
    # Expect two runs with run identifiers and date ranges
    # Example assumed columns:
    # RunID, RunName, StartTime, EndTime, Total Vusers, Average Throughput (B/s),
    # Total Hits, Average Hits/sec, Passed Ratio, Total Transactions,
    # Total Average Response Time (Sec), Achieved Volumes
    if load_df.empty:
        return "<p><em>No load test summary.</em></p>", ""

    # Try standardize headers
    rename_map = {
        "Run ID": "RunID",
        "RunID": "RunID",
        "Run Name": "RunName",
        "RunName": "RunName",
        "Start": "StartTime",
        "StartTime": "StartTime",
        "End": "EndTime",
        "EndTime": "EndTime",
        "Total Vusers": "Total Vusers",
        "Average Throughput (B/s)": "Average Throughput (B/s)",
        "Total Hits": "Total Hits",
        "Average Hits/sec": "Average Hits/sec",
        "Passed Ratio": "Passed Ratio",
        "Total Transactions": "Total Transactions",
        "Total Average Response Time (Sec)": "Total Average Response Time (Sec)",
        "Achieved Volumes": "Achieved Volumes",
    }
    df = load_df.rename(columns={k: v for k, v in rename_map.items() if k in load_df.columns})

    # Assume the latest two runs are the two most recent by EndTime (or by order)
    time_col = "EndTime" if "EndTime" in df.columns else None
    if time_col:
        df_sorted = df.copy()
        df_sorted[time_col] = pd.to_datetime(df_sorted[time_col], errors="coerce")
        df_sorted = df_sorted.sort_values(time_col, ascending=False)
    else:
        df_sorted = df.copy()

    two = df_sorted.head(2).reset_index(drop=True)
    if two.shape[0] < 2:
        # If only one row available, duplicate for formatting
        two = pd.concat([two, two]).head(2).reset_index(drop=True)

    # Header line like:
    # Run ID - 984   Run ID - 1051
    r1 = str(two.loc[0, "RunID"]) if "RunID" in two.columns else "Run A"
    r2 = str(two.loc[1, "RunID"]) if "RunID" in two.columns else "Run B"
    # Run name + times line:
    def name_and_time(row):
        rn = row.get("RunName", "Run")
        st = row.get("StartTime", "")
        et = row.get("EndTime", "")
        return f"{rn} - {st} - {et}"

    heading_row = f"""
      <table style="border-collapse:collapse;width:100%;margin-bottom:8px">
        <tr>
          <td style="padding:4px 0;"><strong>Run ID - {r1}</strong></td>
          <td style="padding:4px 0;"><strong>Run ID - {r2}</strong></td>
        </tr>
        <tr>
          <td style="padding:4px 0;">{name_and_time(two.loc[0])}</td>
          <td style="padding:4px 0;">{name_and_time(two.loc[1])}</td>
        </tr>
      </table>
    """

    # Metric comparison table
    metric_order = [
        "Total Vusers",
        "Average Throughput (B/s)",
        "Total Hits",
        "Average Hits/sec",
        "Passed Ratio",
        "Total Transactions",
        "Total Average Response Time (Sec)",
        "Achieved Volumes",
    ]
    rows_html = []
    for m in metric_order:
        v1 = two.loc[0, m] if m in two.columns else ""
        v2 = two.loc[1, m] if m in two.columns else ""
        rows_html.append(f"""
          <tr>
            <td style="border:1px solid #ddd; padding:6px; font-weight:bold;">{m}</td>
            <td style="border:1px solid #ddd; padding:6px;">{v1}</td>
            <td style="border:1px solid #ddd; padding:6px;">{v2}</td>
          </tr>
        """)
    table_html = f"""
      <table style="border-collapse:collapse;width:100%;">
        <tr>
          <th style="border:1px solid #ddd;padding:6px;background:#f5f5f5;">Metric</th>
          <th style="border:1px solid #ddd;padding:6px;background:#f5f5f5;">Load Test Summary</th>
          <th style="border:1px solid #ddd;padding:6px;background:#f5f5f5;">Load Test Summary</th>
        </tr>
        {''.join(rows_html)}
      </table>
    """
    return heading_row, table_html

def build_top_slow_table(slow_df: pd.DataFrame) -> str:
    # Expected columns:
    # "Transaction Names","Average (Sec)","90 Percent (Sec)","95 Percent (Sec)","99 Percent (Sec)"
    wanted = ["Transaction Names","Average (Sec)","90 Percent (Sec)","95 Percent (Sec)","99 Percent (Sec)"]
    df = slow_df.copy()
    present = [c for c in wanted if c in df.columns]
    if not present:
        return "<p><em>No high response time details.</em></p>"
    df = df[present]
    df = clamp_top(df, n=50)
    return df_to_html_table(df)

def build_comparison_tables(comp_df: pd.DataFrame) -> tuple[str, str]:
    # We expect a dataset that has two runs’ columns side-by-side with deviation.
    # Example columns:
    # "Transaction Names","Average (Sec)_A","90 Percent (Sec)_A","95 Percent (Sec)_A","99 Percent (Sec)_A",
    # "Average (Sec)_B","90 Percent (Sec)_B","95 Percent (Sec)_B","99 Percent (Sec)_B","Deviation","Deviation %"
    if comp_df.empty:
        return "<p><em>No comparison data.</em></p>", ""

    # Attempt to infer the two run captions from the file (optional).
    # For exact headings line like your example, set these via env or detect from the CSV if present.
    h1 = os.getenv("COMP_HEADING_LEFT", "MP_1.1_5K_Users_LoadTest_05022026 - 05/02/2026 02:05:27 - 05/02/2026 11:39:26 EST")
    h2 = os.getenv("COMP_HEADING_RIGHT", "MP_1.1_5K_LoadTest_18022026 - 18/02/2026 03:08:02 AM - 18/02/2026 01:58:24 PM EST")
    heading_row = f"""
      <table style="border-collapse:collapse;width:100%;margin-bottom:8px">
        <tr>
          <td style="padding:4px 0;"><strong>{h1}</strong></td>
          <td style="padding:4px 0;"><strong>{h2}</strong></td>
        </tr>
        <tr>
          <td style="padding:4px 0;"><strong>Load Test Summary</strong></td>
          <td style="padding:4px 0;"><strong>Load Test Summary</strong></td>
        </tr>
      </table>
    """

    # Build table with both runs & deviation
    expected_cols = [
        "Transaction Names",
        "Average (Sec)_A","90 Percent (Sec)_A","95 Percent (Sec)_A","99 Percent (Sec)_A",
        "Average (Sec)_B","90 Percent (Sec)_B","95 Percent (Sec)_B","99 Percent (Sec)_B",
        "Deviation","Deviation %"
    ]
    present = [c for c in expected_cols if c in comp_df.columns]
    df = comp_df[present].copy()
    df = clamp_top(df, n=50)
    # Rename columns to match your visual (remove suffixes A/B in header)
    rename_map = {
        "Transaction Names": "Transaction Names",
        "Average (Sec)_A": "Average (Sec)",
        "90 Percent (Sec)_A": "90 Percent (Sec)",
        "95 Percent (Sec)_A": "95 Percent (Sec)",
        "99 Percent (Sec)_A": "99 Percent (Sec)",
        "Average (Sec)_B": "Average (Sec)",
        "90 Percent (Sec)_B": "90 Percent (Sec)",
        "95 Percent (Sec)_B": "95 Percent (Sec)",
        "99 Percent (Sec)_B": "99 Percent (Sec)",
        "Deviation": "Deviation",
        "Deviation %": "Deviation %"
    }
    df_display = df.rename(columns=rename_map)
    return heading_row, df_to_html_table(df_display)

def build_observations(load_df: pd.DataFrame, error_df: pd.DataFrame, slow_df: pd.DataFrame) -> list[str]:
    obs = []
    # Example generated observations based on data patterns
    # 1) Response times degraded? Check if average response time increased vs prior run
    try:
        # Need at least two rows; compare last two rows by EndTime
        df = load_df.rename(columns={"End": "EndTime", "EndTime": "EndTime"})
        df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")
        df = df.sort_values("EndTime", ascending=False).head(2)
        if df.shape[0] == 2:
            cur = pd.to_numeric(df.iloc[0].get("Total Average Response Time (Sec)"), errors="coerce")
            prev = pd.to_numeric(df.iloc[1].get("Total Average Response Time (Sec)"), errors="coerce")
            if pd.notna(cur) and pd.notna(prev) and cur > prev:
                obs.append("Response times degraded compared to the previous 5,000-user load test.")
    except Exception:
        pass

    # 2) List HTTP 500/422 occurrence summary from ErrorDetails.csv if available
    try:
        if not error_df.empty:
            # Expect columns like: "StatusCode","Count" (adjust if different)
            code_col = "StatusCode" if "StatusCode" in error_df.columns else None
            cnt_col = "Count" if "Count" in error_df.columns else None
            if code_col and cnt_col:
                err_map = error_df.groupby(code_col)[cnt_col].sum().to_dict()
                http_500 = err_map.get(500, 0)
                http_422 = err_map.get(422, 0)
                if http_500 or http_422:
                    obs.append(f"During the {EXECUTED_USERS} load test, we observed {http_500} (500) and {http_422} (422) errors.")
    except Exception:
        pass

    # Fallback examples if nothing detected
    if not obs:
        obs.append("Attached is the comparison report summarizing the last two tests with 5k users each.")
    return obs

def main():
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)

    load_df = read_csv_safe("load_test_results.csv")
    comp_df = read_csv_safe("ComparisonReport.csv")
    slow_df = read_csv_safe("TopSlowTransactions.csv")
    err_df  = read_csv_safe("ErrorDetails.csv")

    scenarios_table = build_scenarios_table(load_df)
    load_heading, load_table = build_load_summary(load_df)
    top_slow_table = build_top_slow_table(slow_df)
    comp_heading, comp_table = build_comparison_tables(comp_df)
    observations = build_observations(load_df, err_df, slow_df)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        tmpl = Template(f.read())

    html_body = tmpl.render(
        executed_users=EXECUTED_USERS,
        scenarios_table=scenarios_table,
        load_test_summary_heading_row=load_heading,
        load_test_summary_tables=load_table,
        defect_sheet_name=DEFECT_SHEET_NAME,
        top_slow_table=top_slow_table,
        comparison_heading_row=comp_heading,
        comparison_tables=comp_table,
        observations=observations,
        sender_name=SENDER_NAME
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_body)

    print(f"Email HTML written to {OUTPUT_HTML}")

    # If you want to send email directly here via SMTP, uncomment and set secrets
    # send_via_smtp(html_body)

if __name__ == "__main__":
    main()
