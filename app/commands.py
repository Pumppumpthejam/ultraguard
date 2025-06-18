import click
from flask.cli import with_appcontext
from . import db
from .models import Client, Device, Site, Route, Shift, User, UploadedPatrolReport

@click.command('test-db-connection')
@with_appcontext
def test_db_connection_command():
    """Tests the database connection and performs basic queries on all models."""
    try:
        # Test connection and basic queries for each model
        results = {
            'Client': db.session.query(Client.id).count(),
            'Device': db.session.query(Device.id).count(),
            'Site': db.session.query(Site.id).count(),
            'Route': db.session.query(Route.id).count(),
            'Shift': db.session.query(Shift.id).count(),
            'User': db.session.query(User.id).count(),
            'UploadedPatrolReport': db.session.query(UploadedPatrolReport.id).count()
        }
        
        click.echo("✅ Successfully connected to the database!")
        click.echo("\nRecord counts by model:")
        for model, count in results.items():
            click.echo(f"  - {model}: {count} records")
        
        click.echo(f"\nDatabase URI: {db.engine.url}")
        click.echo(f"Database driver: {db.engine.driver}")
        click.echo(f"Database name: {db.engine.url.database}")
        
    except Exception as e:
        click.echo(f"❌ Error connecting to the database or querying: {str(e)}")
        click.echo(f"Database URI attempted: {db.engine.url}")
        raise click.Abort() 