import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.schema import InputTicket, AgentDecision
from src.agent.graph import process_ticket
from src.config import Config

console = Console()

def display_banner():
    console.print(Panel.fit(
        "[bold cyan]HACKERANK ORCHESTRATE AI AGENT[/bold cyan]\n"
        "[dim]Autonomous State-Machine Triage & Defense Engine[/dim]\n"
        f"[green]Active Model Backend:[/green] [yellow]{Config.get_active_model()}[/yellow]",
        border_style="cyan"
    ))

def display_decision(decision: AgentDecision):
    table = Table(title=f"Agent Decision: {decision.ticket_id}", border_style="bright_blue")
    table.add_column("Field", style="bold white", width=18)
    table.add_column("Value", style="cyan")

    # Colored action tag
    action_color = "green" if decision.action.value == "replied" else ("red" if decision.action.value == "blocked" else "yellow")
    table.add_row("Action", f"[{action_color}]{decision.action.value.upper()}[/{action_color}]")
    table.add_row("Priority", decision.priority.value.upper())
    table.add_row("Category", decision.category)
    table.add_row("Requires Human", str(decision.requires_human))
    table.add_row("Injection Flagged", f"[bold red]{decision.injection_detected}[/bold red]" if decision.injection_detected else "False")
    table.add_row("Justification", decision.justification)
    
    citations_str = ", ".join([f"{c.document_id} ({c.title})" for c in decision.citations]) or "None"
    table.add_row("Citations Grounding", citations_str)
    
    console.print(table)
    console.print(Panel(decision.response_draft, title="Response / Triage Notes", border_style="magenta"))

def run_interactive():
    display_banner()
    console.print("[bold yellow]Interactive Ticket Mode[/bold yellow] (Type 'exit' to quit)\n")
    
    while True:
        try:
            subject = console.input("[bold green]Enter Subject:[/bold green] ").strip()
            if subject.lower() in ["exit", "quit", "q"]:
                break
            if not subject:
                continue

            description = console.input("[bold green]Enter Description:[/bold green] ").strip()
            ticket = InputTicket(
                ticket_id=f"INTERACTIVE-{sys.platform[:3].upper()}",
                subject=subject,
                description=description
            )
            with console.status("[bold blue]Agent reasoning through LangGraph nodes...[/bold blue]"):
                decision = process_ticket(ticket)
            display_decision(decision)
            console.print("\n" + "-"*60 + "\n")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    run_interactive()

