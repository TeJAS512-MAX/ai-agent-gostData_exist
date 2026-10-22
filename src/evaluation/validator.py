from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
from src.schema import TriageAction, PriorityLevel

REQUIRED_COLUMNS = [
    "ticket_id",
    "action",
    "priority",
    "category",
    "citation_id",
    "response_summary"
]

class CSVValidator:
    """Automated schema and integrity checker for HackerRank output.csv submissions."""

    @staticmethod
    def validate_file(csv_path: Path) -> Dict[str, Any]:
        if not csv_path.exists():
            return {"valid": False, "errors": [f"File {csv_path} does not exist."]}

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            return {"valid": False, "errors": [f"CSV parse error: {e}"]}

        errors: List[str] = []

        # 1. Check columns
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")

        # 2. Check null values
        null_counts = df[REQUIRED_COLUMNS].isnull().sum().to_dict()
        for col, count in null_counts.items():
            if count > 0:
                errors.append(f"Column '{col}' contains {count} null or NaN values.")

        # 3. Check actions
        valid_actions = {a.value for a in TriageAction}
        invalid_actions = set(df["action"].str.lower().unique()) - valid_actions
        if invalid_actions:
            errors.append(f"Invalid actions found: {invalid_actions}. Allowed: {valid_actions}")

        # 4. Check priorities
        valid_priorities = {p.value for p in PriorityLevel}
        invalid_priorities = set(df["priority"].str.lower().unique()) - valid_priorities
        if invalid_priorities:
            errors.append(f"Invalid priorities found: {invalid_priorities}. Allowed: {valid_priorities}")

        stats = {
            "total_rows": len(df),
            "action_distribution": df["action"].value_counts().to_dict() if "action" in df.columns else {},
            "priority_distribution": df["priority"].value_counts().to_dict() if "priority" in df.columns else {},
        }

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "stats": stats
        }

