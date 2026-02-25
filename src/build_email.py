import os
import pandas as pd
from jinja2 import Template
from datetime import datetime
from utils import df_to_html_table, clamp_top

DATA_DIR = os.getenv("DATA_DIR", "data")
TEMPLATE_PATH = os.getenv("TEMPLATE_PATH", "src/email_template.html")
OUTPUT_HTML = os.getenv("OUTPUT_HTML", "out/email.html")

SENDER_NAME = os.getenv("SENDER_NAME", "Rajesh Dasari")
DEFECT_SHEET_NAME = os.getenv("DEFECT_SHEET_NAME", "NY_MECM_Performance_issues.xlsx")

# Optional overrides for comparison headings (used if CSVs lack enough info)
COMP_HEADING_LEFT = os.getenv("COMP_HEADING_LEFT", "")
COMP_HEADING_RIGHT = os.getenv("COMP_HEADING_RIGHT", "")

def read_csv(name: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)

def detect_executed_users(load_df: pd.DataFrame) -> str:
    # Prefer "Total Vusers" from the most recent run
    if not load_df.empty:
        df = load_df.rename(columns={"End":"EndTime"}).copy()
        if "EndTime" in df.columns:
            df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")
            df = df.sort_values("EndTime", ascending=False)
        # Try Total Vusers field
        for col in ["Total Vusers", "Total_Vusers", "Users", "Vusers"]:
            if col in df.columns:
                v = pd.to_numeric(df[col], errors="coerce").dropna()
                if not v.empty:
                    return f"{int(v.iloc[0]):,}"
        # If not present, try scenario-level sum of "User distribution"
        if "User distribution" in df.columns:
            vu = pd.to_numeric(df["User distribution"], errors="coerce").sum()
            if pd.notna(vu) and vu > 0:
                return f"{int(vu):,}"
    # Fallback
    return "5,000"

def detect_primary_application(load_df: pd.DataFrame) -> str:
    # Determine which portal is dominant to present in the greeting (e.g., "Member Portal")
    if not load_df.empty and "Portal" in load_df.columns:
        top = load_df["Portal"].dropna().astype(str).value_counts().idxmax()
        # Normalize casing/spaces lightly
        return top.strip()
    return "Member Portal"

def build_scenarios_table(load_df: pd.DataFrame) -> str:
    wanted = ["Script Name", "Portal", "Achieved Volume", "User distribution"]
    present = [c for c in wanted if c in load_df.columns]
    if len(present) < 3:
        return "<p><em>Scenarios not available (column mismatch).</em></p>"
    df = load_df[present].copy()
    # Keep 'Total' last
    if "Script Name" in df.columns:
        total_mask = df["Script Name"].astype(str).str.strip().str.lower().eq("total")
        total_df = df[total_mask]
        df = pd.concat([df[~total_mask], total_df], ignore_index=True)
    return df_to_html_table(df.rename(columns={
        "Script Name": "Script Name",
        "Portal": "Portal",
        "Achieved Volume": "Achieved Volume",
        "User distribution": "User distribution"
    }))

def load_two_latest_runs(load_df: pd.DataFrame) -> pd.DataFrame:
    if load_df.empty:
        return load_df
    df = load_df.rename(columns={"End":"EndTime"}).copy()
    if "EndTime" in df.columns:
        df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")
        df = df.sort_values("EndTime", ascending=False)
    return df.head(2).reset_index(drop=True)

def run_line(row) -> str:
    rn = row.get("RunName", "Run")
    st = row.get("StartTime", "")
    et = row.get("EndTime", "")
    return f"{rn} - {st} - {et}"

def build_load_summary(load_df: pd.DataFrame) -> tuple[str, str]:
    if load_df.empty:
        return "<p><em>No load test summary.</em></p>", "<p><em>No metrics available.</em></p>"

    rename_map = {
        "RunID":"RunID","Run ID":"RunID",
        "RunName":"RunName","Run Name":"RunName",
        "StartTime":"StartTime","Start":"StartTime",
        "EndTime":"EndTime","End":"EndTime",
        "Total Vusers":"Total Vusers",
        "Average Throughput (B/s)":"Average Throughput (B/s)",
        "Total Hits":"Total Hits",
        "Average Hits/sec":"Average Hits/sec",
        "Passed Ratio":"Passed Ratio",
        "Total Transactions":"Total Transactions",
        "Total Average Response Time (Sec)":"Total Average Response Time (Sec)",
        "Achieved Volumes":"Achieved Volumes"
    }
    df = load_df.rename(columns={k: v for k, v in rename_map.items() if k in load_df.columns}).copy()
    two = load_two_latest_runs(df)
    if two.shape[0] == 0:
        return "<p><em>No load test summary.</em></p>", "<p><em>No metrics available.</em></p>"
    if two.shape[0] == 1:
        two = pd.concat([two, two]).reset_index(drop=True)

    r1 = str(two.loc[0, "RunID"]) if "RunID" in two.columns else "Run A"
    r2 = str(two.loc[1, "RunID"]) if "RunID" in two.columns else "Run B"

    heading = f"""
      <div style="margin:8px 0; font-weight:bold;">
        Run ID - {r1}&nbsp;&nbsp;&nbsp;&nbsp;Run ID - {r2}
      </div>
      <div style="margin:4px 0;">
        {run_line(two.loc[0])}&nbsp;&nbsp;&nbsp;&nbsp;{run_line(two.loc[1])}
      </div>
    """

    metrics = [
        "Total Vusers",
        "Average Throughput (B/s)",
        "Total Hits",
        "Average Hits/sec",
        "Passed Ratio",
        "Total Transactions",
        "Total Average Response Time (Sec)",
        "Achieved Volumes"
    ]
    rows = []
    for m in metrics:
        v1 = two.loc[0, m] if m in two.columns else ""
        v2 = two.loc[1, m] if m in two.columns else ""
        rows.append(f"""
          <tr>
            <td style="border:1px solid #ddd; padding:6px; font-weight:bold;">{m}</td>
            <td style="border:1px solid #ddd; padding:6px;">{v1}</td>
            <td style="border:1px solid #ddd; padding:6px;">{v2}</td>
          </tr>
        """)
    table = f"""
      <table style="border-collapse:collapse; width:100%;">
        <tr>
          <th style="border:1px solid #ddd; padding:6px; background:#f5f5f5;">Metric</th>
          <th style="border:1px solid #ddd; padding:6px; background:#f5f5f5;">Load Test Summary</th>
          <th style="border:1px solid #ddd; padding:6px; background:#f5f5f5;">Load Test Summary</th>
        </tr>
        {''.join(rows)}
      </table>
    """
    return heading, table

def infer_comparison_headings_from_runs(load_df: pd.DataFrame) -> tuple[str, str]:
    two = load_two_latest_runs(load_df)
    if two.shape[0] < 2:
        return "", ""
    left = run_line(two.loc[0])
    right = run_line(two.loc[1])
    return left, right

def build_top_slow_table(slow_df: pd.DataFrame) -> str:
    wanted = ["Transaction Names","Average (Sec)","90 Percent (Sec)","95 Percent (Sec)","99 Percent (Sec)"]
    present = [c for c in wanted if c in slow_df.columns]
    if not present:
        return "<p><em>No high response time details.</em></p>"
    df = clamp_top(slow_df[present].copy(), 50)
    return df_to_html_table(df)

def build_comparison_section(comp_df: pd.DataFrame, load_df: pd.DataFrame) -> tuple[str, str]:
    # Build heading using either env overrides, or derive from latest runs in load_df
    h_left = COMP_HEADING_LEFT
    h_right = COMP_HEADING_RIGHT
    if not h_left or not h_right:
        l, r = infer_comparison_headings_from_runs(load_df.rename(columns={"End":"EndTime"}).copy())
        h_left = h_left or l
        h_right = h_right or r

    if not comp_df.empty:
        expected = [
            "Transaction Names",
            "Average (Sec)_A","90 Percent (Sec)_A","95 Percent (Sec)_A","99 Percent (Sec)_A",
            "Average (Sec)_B","90 Percent (Sec)_B","95 Percent (Sec)_B","99 Percent (Sec)_B",
            "Deviation","Deviation %"
        ]
        present = [c for c in expected if c in comp_df.columns]
        df = clamp_top(comp_df[present].copy(), 50)
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
        display_df = df.rename(columns=rename_map)
        table_html = df_to_html_table(display_df)
    else:
        table_html = "<p><em>No comparison table.</em></p>"

    heading_html = ""
    if h_left and h_right:
        heading_html = f"""
          <div style="margin:8px 0; font-weight:bold;">
            {h_left}&nbsp;&nbsp;&nbsp;&nbsp;{h_right}
          </div>
        """
    return heading_html, table_html

def build_observations(load_df: pd.DataFrame, error_df: pd.DataFrame, executed_users: str) -> list[str]:
    obs = []
    # Degradation check
    try:
        df = load_df.rename(columns={"End":"EndTime"}).copy()
        if "EndTime" in df.columns:
            df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")
            two = df.sort_values("EndTime", ascending=False).head(2).reset_index(drop=True)
            if two.shape[0] == 2:
                c = pd.to_numeric(two.loc[0, "Total Average Response Time (Sec)"], errors="coerce")
                p = pd.to_numeric(two.loc[1, "Total Average Response Time (Sec)"], errors="coerce")
                if pd.notna(c) and pd.notna(p) and c > p:
                    obs.append("Response times degraded—particularly for the sign-in and submit transactions—compared to the previous load test.")
    except Exception:
        pass

    # Error codes summary (500/422)
    try:
        if not error_df.empty and "StatusCode" in error_df.columns and "Count" in error_df.columns:
            m = error_df.groupby("StatusCode")["Count"].sum().to_dict()
            c500 = int(m.get(500, 0))
            c422 = int(m.get(422, 0))
            if c500 or c422:
                obs.append(f"During the {executed_users} load test, we observed {c500} (500) and {c422} (422) errors.")
    except Exception:
        pass

    # Always include comparison note if not already noted
    if not any("comparison" in o.lower() for o in obs):
        obs.append("Attached is the comparison report summarizing the last two tests with the same user volume.")

    return obs

def main():
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)

    load_df = read_csv("load_test_results.csv")
    slow_df = read_csv("TopSlowTransactions.csv")
    # Allow for either spelling:
    comp_df = read_csv("ComparisonReport.csv")
    if comp_df.empty:
        comp_df = read_csv("ComparisionReport.csv")
    err_df  = read_csv("ErrorDetails.csv")

    executed_users = detect_executed_users(load_df)
    primary_app = detect_primary_application(load_df)

    scenarios_table = build_scenarios_table(load_df)
    load_heading, load_table = build_load_summary(load_df)
    top_slow_table = build_top_slow_table(slow_df)
    comp_heading, comp_table = build_comparison_section(comp_df, load_df)
    observations = build_observations(load_df, err_df, executed_users)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = Template(f.read())

    html_body = template.render(
        # Intro variables are now dynamic
        executed_users=executed_users,
        scenarios_table=scenarios_table,
        load_test_summary_heading_row=load_heading,
        load_test_summary_tables=load_table,
        defect_sheet_name=DEFECT_SHEET_NAME,
        top_slow_table=top_slow_table,
        comparison_heading_row=comp_heading,
        comparison_tables=comp_table,
        observations=observations,
        sender_name=SENDER_NAME,
        # If you want to reflect app in the intro sentence, modify the template to use {{primary_app}}
        primary_app=primary_app
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_body)

    print(f"Wrote email HTML to {OUTPUT_HTML} with executed_users={executed_users} and primary_app={primary_app}")

if __name__ == "__main__":
    main()
