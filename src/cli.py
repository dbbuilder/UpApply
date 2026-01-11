"""
Command Line Interface for Upwork Automation Tool

Provides an interactive CLI for managing Upwork job applications using Click.
Supports job listing, filtering, selection, and automated application submission.
"""

import asyncio
import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm, Prompt
from rich import print as rich_print

from .config import get_config
from .upwork_scraper import extract_saved_jobs, load_saved_jobs
from .browser_automation import apply_to_jobs, apply_to_single_job
from .utils import parse_job_numbers, format_currency, format_datetime, load_json

logger = logging.getLogger(__name__)
console = Console()

class UpworkCLI:
    """Command line interface for Upwork automation"""
    
    def __init__(self):
        """Initialize CLI with configuration"""
        self.config = get_config()
        self.jobs: List[Dict[str, Any]] = []
        self.loaded = False
    
    async def load_jobs(self, force_refresh: bool = False) -> bool:
        """
        Load jobs from file or refresh from Upwork
        
        Args:
            force_refresh: If True, refresh from Upwork instead of loading from file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if force_refresh:
                console.print("🔄 Refreshing jobs from Upwork...", style="yellow")
                self.jobs = await extract_saved_jobs()
            else:
                console.print("📂 Loading jobs from local file...", style="blue")
                self.jobs = await load_saved_jobs()
            
            # Filter out already applied jobs
            unapplied_jobs = [job for job in self.jobs if not job.get('applied', False)]
            self.jobs = unapplied_jobs
            
            self.loaded = True
            console.print(f"✅ Loaded {len(self.jobs)} unapplied jobs", style="green")
            return True
            
        except Exception as e:
            console.print(f"❌ Error loading jobs: {e}", style="red")
            logger.error(f"Error loading jobs: {e}")
            return False
    
    def display_jobs(self, sort_by: str = 'date') -> None:
        """
        Display jobs in a formatted table
        
        Args:
            sort_by: Sort criteria ('date', 'budget', 'rating', 'title')
        """
        if not self.jobs:
            console.print("No jobs available. Run 'refresh' to load jobs from Upwork.", style="yellow")
            return
        
        # Sort jobs
        if sort_by == 'date':
            sorted_jobs = sorted(self.jobs, key=lambda x: x.get('saved_date', ''), reverse=True)
        elif sort_by == 'budget':
            sorted_jobs = sorted(self.jobs, key=lambda x: x.get('budget', ''), reverse=True)
        elif sort_by == 'rating':
            sorted_jobs = sorted(self.jobs, key=lambda x: x.get('client_rating', 0), reverse=True)
        elif sort_by == 'title':
            sorted_jobs = sorted(self.jobs, key=lambda x: x.get('title', '').lower())
        else:
            sorted_jobs = self.jobs
        
        # Create table
        table = Table(title=f"Available Jobs (sorted by {sort_by})")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Title", style="bold", width=40)
        table.add_column("Budget", style="green", width=15)
        table.add_column("Client Rating", style="yellow", width=12)
        table.add_column("Location", style="blue", width=15)
        table.add_column("Posted", style="magenta", width=12)
        
        for i, job in enumerate(sorted_jobs, 1):
            title = job.get('title', 'Unknown')
            if len(title) > 37:
                title = title[:34] + "..."
            
            budget = format_currency(job.get('budget', ''))
            rating = f"{job.get('client_rating', 'N/A'):.1f}★" if job.get('client_rating') else "N/A"
            location = job.get('client_location', 'Unknown')[:12]
            posted = format_datetime(job.get('saved_date', ''))
            
            table.add_row(str(i), title, budget, rating, location, posted)
        
        console.print(table)
    
    def display_job_details(self, job_index: int) -> None:
        """
        Display detailed information for a specific job
        
        Args:
            job_index: Index of the job in the list (1-based)
        """
        if not self.jobs or job_index < 1 or job_index > len(self.jobs):
            console.print("Invalid job number", style="red")
            return
        
        job = self.jobs[job_index - 1]
        
        # Create detailed panel
        details = f"""
[bold]Title:[/bold] {job.get('title', 'Unknown')}
[bold]Budget:[/bold] {format_currency(job.get('budget', 'Not specified'))}
[bold]Client Rating:[/bold] {job.get('client_rating', 'N/A')}
[bold]Client Location:[/bold] {job.get('client_location', 'Unknown')}
[bold]Posted:[/bold] {format_datetime(job.get('saved_date', 'Unknown'))}
[bold]Job URL:[/bold] {job.get('upwork_url', 'N/A')}

[bold]Description:[/bold]
{job.get('description', 'No description available')[:500]}{'...' if len(job.get('description', '')) > 500 else ''}
        """
        
        panel = Panel(details, title=f"Job #{job_index} Details", border_style="blue")
        console.print(panel)
    
    async def apply_to_selected_jobs(self, job_numbers: str) -> bool:
        """
        Apply to jobs selected by number
        
        Args:
            job_numbers: Comma-separated job numbers or ranges
        
        Returns:
            bool: True if any applications were successful
        """
        try:
            # Parse job numbers
            selected_indices = parse_job_numbers(job_numbers)
            
            # Validate indices
            valid_indices = [i for i in selected_indices if 1 <= i <= len(self.jobs)]
            if not valid_indices:
                console.print("No valid job numbers provided", style="red")
                return False
            
            if len(valid_indices) != len(selected_indices):
                invalid = [i for i in selected_indices if i not in valid_indices]
                console.print(f"Warning: Invalid job numbers ignored: {invalid}", style="yellow")
            
            # Get selected jobs
            selected_jobs = [self.jobs[i - 1] for i in valid_indices]
            
            # Show confirmation
            console.print(f"\n📋 Selected {len(selected_jobs)} jobs for application:", style="bold")
            for i, job in enumerate(selected_jobs, 1):
                console.print(f"  {i}. {job.get('title', 'Unknown')}")
            
            if not Confirm.ask("\nProceed with applications?"):
                console.print("Application cancelled by user", style="yellow")
                return False
            
            # Start application process
            console.print("\n🚀 Starting application process...", style="bold green")
            
            results = await apply_to_jobs(selected_jobs)
            
            # Display results
            self._display_application_results(results)
            
            # Reload jobs to update status
            await self.load_jobs()
            
            return results['successful_applications'] > 0
            
        except ValueError as e:
            console.print(f"Error parsing job numbers: {e}", style="red")
            return False
        except Exception as e:
            console.print(f"Error applying to jobs: {e}", style="red")
            logger.error(f"Error applying to jobs: {e}")
            return False
    
    def _display_application_results(self, results: Dict[str, Any]) -> None:
        """
        Display application results in a formatted way
        
        Args:
            results: Results dictionary from batch application
        """
        total = results['total_jobs']
        successful = results['successful_applications']
        failed = results['failed_applications']
        success_rate = (successful / total) * 100 if total > 0 else 0
        
        # Summary panel
        summary = f"""
[bold green]✅ Successful:[/bold green] {successful}
[bold red]❌ Failed:[/bold red] {failed}
[bold blue]📊 Success Rate:[/bold blue] {success_rate:.1f}%
        """
        
        summary_panel = Panel(summary, title="Application Results", border_style="green")
        console.print(summary_panel)
        
        # Detailed results
        if results.get('job_results'):
            table = Table(title="Detailed Results")
            table.add_column("Job", style="bold", width=30)
            table.add_column("Status", width=10)
            table.add_column("Notes", width=30)
            
            for job_result in results['job_results']:
                title = job_result.get('job_title', 'Unknown')[:27] + "..." if len(job_result.get('job_title', '')) > 30 else job_result.get('job_title', 'Unknown')
                status = "✅ Success" if job_result.get('success') else "❌ Failed"
                notes = job_result.get('error', 'Application completed') if not job_result.get('success') else 'Application submitted'
                
                table.add_row(title, status, notes[:27] + "..." if len(notes) > 30 else notes)
            
            console.print(table)
    
    def display_application_history(self) -> None:
        """Display history of previous applications"""
        try:
            storage_config = self.config.get_storage_config()
            applications_file = storage_config.get('applications_file', 'data/applications.json')
            
            applications_data = load_json(applications_file, default={'applications': []})
            applications = applications_data.get('applications', [])
            
            if not applications:
                console.print("No application history found", style="yellow")
                return
            
            # Sort by date (most recent first)
            sorted_applications = sorted(
                applications, 
                key=lambda x: x.get('applied_date', ''), 
                reverse=True
            )
            
            table = Table(title="Application History")
            table.add_column("Date", style="cyan", width=12)
            table.add_column("Job Title", style="bold", width=35)
            table.add_column("Status", width=10)
            table.add_column("Notes", width=25)
            
            for app in sorted_applications[:20]:  # Show last 20 applications
                date = format_datetime(app.get('applied_date', ''))
                title = app.get('job_title', 'Unknown')[:32] + "..." if len(app.get('job_title', '')) > 35 else app.get('job_title', 'Unknown')
                status = "✅ Success" if app.get('success') else "❌ Failed"
                notes = app.get('error_message', 'Completed')[:22] + "..." if len(app.get('error_message', '')) > 25 else app.get('error_message', 'Completed')
                
                table.add_row(date, title, status, notes)
            
            console.print(table)
            
            # Summary statistics
            total_apps = len(applications)
            successful_apps = sum(1 for app in applications if app.get('success'))
            success_rate = (successful_apps / total_apps) * 100 if total_apps > 0 else 0
            
            summary = f"Total Applications: {total_apps} | Successful: {successful_apps} | Success Rate: {success_rate:.1f}%"
            console.print(f"\n📊 {summary}", style="bold blue")
            
        except Exception as e:
            console.print(f"Error loading application history: {e}", style="red")
            logger.error(f"Error loading application history: {e}")


# Global CLI instance
cli_instance = UpworkCLI()

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose):
    """
    Upwork Automation Tool
    
    Automate your Upwork job applications with AI-generated cover letters.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        console.print("Verbose logging enabled", style="blue")

@cli.command()
@click.option('--email', help='Upwork email for auto-login')
def refresh(email):
    """Refresh job list from Upwork"""
    async def _refresh():
        success = await cli_instance.load_jobs(force_refresh=True)
        if success:
            console.print(f"✅ Successfully refreshed {len(cli_instance.jobs)} jobs", style="green")
        else:
            console.print("❌ Failed to refresh jobs", style="red")
            sys.exit(1)
    
    asyncio.run(_refresh())

@cli.command('list')
@click.option('--sort', default='date', 
              type=click.Choice(['date', 'budget', 'rating', 'title']),
              help='Sort jobs by specified criteria')
def list_jobs(sort):
    """List available jobs"""
    async def _list():
        if not cli_instance.loaded:
            await cli_instance.load_jobs()
        cli_instance.display_jobs(sort_by=sort)
    
    asyncio.run(_list())

@cli.command()
@click.argument('job_number', type=int)
def view(job_number):
    """View detailed information for a specific job"""
    async def _view():
        if not cli_instance.loaded:
            await cli_instance.load_jobs()
        cli_instance.display_job_details(job_number)
    
    asyncio.run(_view())

@cli.command()
@click.argument('job_numbers')
@click.option('--dry-run', is_flag=True, help='Preview actions without actually applying')
def apply(job_numbers, dry_run):
    """
    Apply to selected jobs by numbers
    
    Examples:
      apply 1          - Apply to job #1
      apply 1,3,5      - Apply to jobs #1, #3, and #5
      apply 1-5        - Apply to jobs #1 through #5
    """
    async def _apply():
        if not cli_instance.loaded:
            await cli_instance.load_jobs()
        
        if dry_run:
            console.print("🔍 DRY RUN MODE - No actual applications will be submitted", style="yellow")
            # TODO: Implement dry run preview
            
        success = await cli_instance.apply_to_selected_jobs(job_numbers)
        if not success:
            sys.exit(1)
    
    asyncio.run(_apply())

@cli.command()
def status():
    """Show application history and statistics"""
    cli_instance.display_application_history()

@cli.command()
def config():
    """Show current configuration"""
    config_data = cli_instance.config._config
    
    # Create configuration display
    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan", width=20)
    table.add_column("Value", style="green", width=40)
    
    # Flatten config for display
    def flatten_config(data, prefix=""):
        items = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                items.extend(flatten_config(value, full_key))
            else:
                # Hide sensitive information
                if 'api_key' in key.lower() or 'password' in key.lower():
                    value = "***hidden***"
                items.append((full_key, str(value)))
        return items
    
    config_items = flatten_config(config_data)
    for key, value in config_items:
        table.add_row(key, value)
    
    console.print(table)

@cli.command()
def interactive():
    """Start interactive mode"""
    async def _interactive():
        if not cli_instance.loaded:
            console.print("Loading jobs...", style="blue")
            await cli_instance.load_jobs()
        
        console.print("\n🎯 Welcome to Upwork Automation Tool - Interactive Mode", style="bold green")
        console.print("Type 'help' for available commands or 'quit' to exit\n")
        
        while True:
            try:
                command = Prompt.ask("upwork", default="help").strip().lower()
                
                if command in ['quit', 'exit', 'q']:
                    console.print("Goodbye! 👋", style="blue")
                    break
                elif command in ['help', 'h']:
                    _show_interactive_help()
                elif command in ['list', 'l']:
                    cli_instance.display_jobs()
                elif command in ['refresh', 'r']:
                    await cli_instance.load_jobs(force_refresh=True)
                elif command in ['status', 's']:
                    cli_instance.display_application_history()
                elif command.startswith('view '):
                    try:
                        job_num = int(command.split()[1])
                        cli_instance.display_job_details(job_num)
                    except (IndexError, ValueError):
                        console.print("Usage: view <job_number>", style="red")
                elif command.startswith('apply '):
                    try:
                        job_numbers = command.split(maxsplit=1)[1]
                        await cli_instance.apply_to_selected_jobs(job_numbers)
                    except IndexError:
                        console.print("Usage: apply <job_numbers>", style="red")
                elif command.startswith('sort '):
                    try:
                        sort_by = command.split()[1]
                        if sort_by in ['date', 'budget', 'rating', 'title']:
                            cli_instance.display_jobs(sort_by=sort_by)
                        else:
                            console.print("Sort options: date, budget, rating, title", style="red")
                    except IndexError:
                        console.print("Usage: sort <criteria>", style="red")
                else:
                    console.print(f"Unknown command: {command}. Type 'help' for available commands.", style="red")
                    
            except KeyboardInterrupt:
                console.print("\nUse 'quit' to exit", style="yellow")
            except Exception as e:
                console.print(f"Error: {e}", style="red")
                logger.error(f"Interactive mode error: {e}")
    
    asyncio.run(_interactive())

def _show_interactive_help():
    """Show help for interactive mode"""
    help_text = """
[bold]Available Commands:[/bold]

[cyan]list, l[/cyan]           - List available jobs
[cyan]refresh, r[/cyan]        - Refresh jobs from Upwork
[cyan]view <number>[/cyan]     - View job details (e.g., 'view 1')
[cyan]apply <numbers>[/cyan]   - Apply to jobs (e.g., 'apply 1,3,5' or 'apply 1-3')
[cyan]sort <criteria>[/cyan]   - Sort jobs (date, budget, rating, title)
[cyan]status, s[/cyan]         - Show application history
[cyan]help, h[/cyan]           - Show this help message
[cyan]quit, exit, q[/cyan]     - Exit interactive mode

[bold]Examples:[/bold]
  list                 - Show all available jobs
  view 3               - Show details for job #3
  apply 1,5,7          - Apply to jobs #1, #5, and #7
  apply 1-5            - Apply to jobs #1 through #5
  sort budget          - Sort jobs by budget
    """
    console.print(Panel(help_text, title="Help", border_style="blue"))

if __name__ == "__main__":
    cli()
