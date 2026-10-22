import argparse
from pathlib import Path
import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from src.schema import InputTicket, OutputRow
from src.agent.graph import process_ticket
from src.evaluation.validator import CSVValidator
from src.config import Config

console = Console()

def run_benchmark(input_csv: Path, output_csv: Path):
    console.print(f"[bold cyan]Running Benchmark Pipeline on:[/bold cyan] {input_csv}")
    
    if not input_csv.exists():
        console.print(f"[bold red]Error: Input file {input_csv} does not exist.[/bold red]")
        return

    df = pd.read_csv(input_csv)
    console.print(f"[green]Loaded {len(df)} test tickets successfully.[/green]")

    output_rows = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[yellow]Processing tickets...", total=len(df))

        for _, row in df.iterrows():
            ticket = InputTicket(
                ticket_id=str(row["ticket_id"]),
                customer_id=str(row.get("customer_id", "UNKNOWN")),
                subject=str(row.get("subject", "")),
                description=str(row.get("description", "")),
                channel=str(row.get("channel", "email"))
            )
            decision = process_ticket(ticket)
            
            citation_id = decision.citations[0].document_id if decision.citations else "NONE"
            output_rows.append({
                "ticket_id": decision.ticket_id,
                "action": decision.action.value,
                "priority": decision.priority.value,
                "category": decision.category,
                "citation_id": citation_id,
                "response_summary": decision.justification
            })
            progress.advance(task)

    # Save to CSV
    output_df = pd.DataFrame(output_rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False)
    console.print(f"\n[bold green]Saved output predictions to:[/bold green] [cyan]{output_csv}[/cyan]")

    # Run strict schema validator
    console.print("\n[bold yellow]Validating Output Schema for HackerRank Compliance...[/bold yellow]")
    val_result = CSVValidator.validate_file(output_csv)
    
    if val_result["valid"]:
        console.print("[bold green]SUCCESS: Output CSV passed all schema and integrity checks![/bold green]")
        
        # Display Stats Table
        table = Table(title="Submission Metrics Summary", border_style="green")
        table.add_column("Metric", style="bold white")
        table.add_column("Count / Distribution", style="cyan")
        
        stats = val_result["stats"]
        table.add_row("Total Processed Rows", str(stats["total_rows"]))
        table.add_row("Actions Breakdown", str(stats["action_distribution"]))
        table.add_row("Priorities Breakdown", str(stats["priority_distribution"]))
        console.print(table)
    else:
        console.print("[bold red]FAILED: Schema validation issues detected:[/bold red]")
        for err in val_result["errors"]:
            console.print(f"  [red]- {err}[/red]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run HackerRank Orchestrate Agent Benchmark")
    parser.add_argument("--input", type=str, default="data/raw/sample_tickets.csv", help="Input CSV path")
    parser.add_argument("--output", type=str, default="outputs/output.csv", help="Output CSV path")
    args = parser.parse_args()

    run_benchmark(Path(args.input), Path(args.output))

