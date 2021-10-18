from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.html import escape

import datetime
import argparse
import decimal
import markdown2

from termsandconditions.models import TermsAndConditions


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def valid_version(s):
    try:
        return decimal.Decimal(s)
    except Exception:
        msg = "Not a valid decimal number: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    help = """Imports or updates terms and conditions to the database.
    """

    def add_arguments(self, parser):
        parser.add_argument('slug', type=str,
                            help='Slug used for these terms in URLs, e.g. "site-terms".')
        parser.add_argument('terms_version', type=valid_version,
                            help="Version number of these terms.")
        parser.add_argument('terms_file', type=open,
                            help="Path of input file containing the terms in markdown format.")

        parser.add_argument(
            '-a',
            '--date-active',
            type=valid_date,
            dest='date_active',
            help='Date from which onwards these terms should be active.',
        )

        parser.add_argument(
            '-n',
            '--name',
            type=str,
            dest='name',
            help='Name of these terms and conditions. If not given, will be extracted from first line.',
        )

        parser.add_argument(
            '--summary',
            type=str,
            dest='summary',
            help='Short optional text with summary of changes.',
        )

    def handle(self, *args, **options):

        #
        # Read terms and convert to markdown
        #
        terms_file = options['terms_file']
        terms_markdown = terms_file.read()

        #
        # Handle optional arguments
        #
        if options['name']:
            name = options['name'].strip()
        else:
            terms_markdown_lines = terms_markdown.splitlines()
            name = terms_markdown_lines[0].replace('#', ' ').strip()
            terms_markdown = "\n".join(terms_markdown_lines[1:])  # remove first line, will be inserted by terms pkg
            self.stdout.write(self.style.NOTICE("Using first line of terms as name."))

        name = escape(name)  # e.g. convert & to &amp;

        terms_html = markdown2.markdown(terms_markdown)

        now = timezone.now()

        if options['date_active']:
            date_active = options['date_active']
        else:
            date_active = now

        if options['summary']:
            info = options['summary']
        else:
            info = ""  # no longer allowed to be None with migration 0004 in official repo of django-termsandconditons

        #
        # Finally create terms and conditions in database
        #
        TermsAndConditions.objects.create(
            slug=options['slug'].strip(),
            version_number=options['terms_version'],
            name=name,
            date_created=timezone.now(),
            date_active=date_active,
            text=terms_html,
            info=info
        )

        self.stdout.write(self.style.SUCCESS(f"Successfully created terms and conditions '{name}' in database."))


