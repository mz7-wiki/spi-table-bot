import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Prevent module-level side effects before importing run_bot:
# - pywikibot.Site() would attempt to connect to Wikipedia
# - RotatingFileHandler would fail if /data/project/... doesn't exist
sys.modules['pywikibot'] = MagicMock()
sys.modules['pywikibot.pagegenerators'] = MagicMock()
sys.modules['pywikibot.textlib'] = MagicMock()
with patch('logging.handlers.RotatingFileHandler'):
    import run_bot

# The mock RotatingFileHandler was added to run_bot's logger at import time.
# Remove it so that logging calls inside run_bot don't raise TypeErrors when
# the logging machinery tries to compare record.levelno >= mock_handler.level.
run_bot.logger.handlers.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_category(name):
    cat = MagicMock()
    cat.title.return_value = name
    return cat


def make_revision(user, timestamp, comment=''):
    rev = MagicMock()
    rev.user = user
    rev.timestamp = timestamp
    rev.comment = comment
    return rev


# ---------------------------------------------------------------------------
# get_status_from_categories
# ---------------------------------------------------------------------------

class TestGetStatusFromCategories(unittest.TestCase):

    def test_single_priority_status(self):
        cats = [make_category('SPI cases needing a Clerk')]
        self.assertEqual(run_bot.get_status_from_categories(cats), ['clerk'])

    def test_new_status_returned(self):
        cats = [make_category('New SPI cases')]
        self.assertEqual(run_bot.get_status_from_categories(cats), ['new'])

    def test_multiple_priority_statuses_all_returned(self):
        cats = [
            make_category('SPI cases needing a Clerk'),
            make_category('SPI cases awaiting archive'),
        ]
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('clerk', result)
        self.assertIn('close', result)

    def test_curequest_group_picks_highest_priority(self):
        # inprogress (rank 0) should beat endorsed (rank 2)
        cats = [
            make_category('SPI cases currently being checked'),  # inprogress
            make_category('SPI cases awaiting a CheckUser'),     # endorsed
        ]
        result = run_bot.get_status_from_categories(cats)
        self.assertEqual(result, ['inprogress'])

    def test_misc_shown_when_no_other_status(self):
        cats = [make_category('SPI cases awaiting review')]  # open
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('open', result)

    def test_misc_shown_when_only_close_present(self):
        cats = [
            make_category('SPI cases awaiting archive'),  # close
            make_category('SPI cases awaiting review'),   # open
        ]
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('close', result)
        self.assertIn('open', result)

    def test_misc_not_shown_when_priority_status_present(self):
        cats = [
            make_category('SPI cases needing a Clerk'),  # clerk (priority)
            make_category('SPI cases awaiting review'),  # open (misc)
        ]
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('clerk', result)
        self.assertNotIn('open', result)

    def test_moreinfo_becomes_cumoreinfo_with_pre_cu_review(self):
        cats = [
            make_category('SPI cases requesting more information'),
            make_category('SPI cases for pre-CheckUser review'),
        ]
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('cumoreinfo', result)
        self.assertNotIn('moreinfo', result)

    def test_moreinfo_without_pre_cu_review_stays_moreinfo(self):
        cats = [make_category('SPI cases requesting more information')]
        result = run_bot.get_status_from_categories(cats)
        self.assertIn('moreinfo', result)
        self.assertNotIn('cumoreinfo', result)

    def test_empty_categories_returns_empty(self):
        self.assertEqual(run_bot.get_status_from_categories([]), [])

    def test_unknown_category_ignored(self):
        cats = [make_category('Some unrelated category')]
        self.assertEqual(run_bot.get_status_from_categories(cats), [])


# ---------------------------------------------------------------------------
# format_table_row
# ---------------------------------------------------------------------------

class TestFormatTableRow(unittest.TestCase):

    def test_produces_correct_wikitext(self):
        case = {
            'name': 'Sockpuppet investigations/Example',
            'status': 'clerk',
            'file_time': '2026-03-22 10:00',
            'last_user': 'SomeUser',
            'last_user_time': '2026-03-22 09:00',
            'last_clerk': 'SomeClerk',
            'last_clerk_time': '2026-03-22 08:00',
        }
        result = run_bot.format_table_row(case)
        self.assertEqual(
            result,
            '{{SPIstatusentry|Sockpuppet investigations/Example|clerk'
            '|2026-03-22 10:00|SomeUser|2026-03-22 09:00|SomeClerk|2026-03-22 08:00}}\n'
        )

    def test_empty_clerk_fields_produce_empty_parameters(self):
        case = {
            'name': 'Example',
            'status': 'open',
            'file_time': '2026-03-22 10:00',
            'last_user': 'User1',
            'last_user_time': '2026-03-22 09:00',
            'last_clerk': '',
            'last_clerk_time': '',
        }
        result = run_bot.format_table_row(case)
        self.assertTrue(result.endswith('|2026-03-22 09:00||}}' + '\n'))


# ---------------------------------------------------------------------------
# generate_case_table
# ---------------------------------------------------------------------------

class TestGenerateCaseTable(unittest.TestCase):

    def test_empty_cases_includes_spi_zero_template(self):
        result = run_bot.generate_case_table([])
        self.assertIn('{{SPIstatusheader}}', result)
        self.assertIn('|}', result)
        self.assertIn('{{User:Mz7/SPI 0}}', result)

    def test_non_empty_cases_does_not_include_spi_zero_template(self):
        cases = [{
            'name': 'Example',
            'status': 'clerk',
            'file_time': '2026-03-22 10:00',
            'last_user': 'User1',
            'last_user_time': '2026-03-22 09:00',
            'last_clerk': 'Clerk1',
            'last_clerk_time': '2026-03-22 08:00',
        }]
        result = run_bot.generate_case_table(cases)
        self.assertIn('{{SPIstatusheader}}', result)
        self.assertIn('SPIstatusentry', result)
        self.assertIn('|}', result)
        self.assertNotIn('{{User:Mz7/SPI 0}}', result)


# ---------------------------------------------------------------------------
# sort_cases
# ---------------------------------------------------------------------------

class TestSortCases(unittest.TestCase):

    def test_sorts_by_rank(self):
        cases = [
            {'name': 'B', 'status': 'clerk',      'file_time': '2026-03-22 10:00'},
            {'name': 'A', 'status': 'inprogress', 'file_time': '2026-03-22 10:00'},
        ]
        result = run_bot.sort_cases(cases)
        self.assertEqual(result[0]['name'], 'A')
        self.assertEqual(result[1]['name'], 'B')

    def test_same_rank_sorted_by_file_time_ascending(self):
        cases = [
            {'name': 'B', 'status': 'open', 'file_time': '2026-03-22 11:00'},
            {'name': 'A', 'status': 'open', 'file_time': '2026-03-22 09:00'},
        ]
        result = run_bot.sort_cases(cases)
        self.assertEqual(result[0]['name'], 'A')
        self.assertEqual(result[1]['name'], 'B')

    def test_quick_ranked_above_curequest(self):
        cases = [
            {'name': 'B', 'status': 'CUrequest', 'file_time': '2026-03-22 10:00'},
            {'name': 'A', 'status': 'QUICK',     'file_time': '2026-03-22 10:00'},
        ]
        result = run_bot.sort_cases(cases)
        self.assertEqual(result[0]['name'], 'A')

    def test_close_ranked_last(self):
        cases = [
            {'name': 'A', 'status': 'close', 'file_time': '2026-03-22 10:00'},
            {'name': 'B', 'status': 'hold',  'file_time': '2026-03-22 10:00'},
        ]
        result = run_bot.sort_cases(cases)
        self.assertEqual(result[-1]['name'], 'A')


# ---------------------------------------------------------------------------
# get_clerk_list
# ---------------------------------------------------------------------------

class TestGetClerkList(unittest.TestCase):

    def setUp(self):
        self.mock_page = MagicMock()
        run_bot.pywikibot.Page.return_value = self.mock_page

    def test_extracts_clerks_from_active_section(self):
        self.mock_page.text = '\n'.join([
            '== Some section ==',
            '=== Active clerks ===',
            '{{UserActive|ClerkOne}}',
            '{{User|ClerkTwo}}',
            '=== Inactive clerks ===',
            '{{User|FormerClerk}}',
        ])
        result = run_bot.get_clerk_list()
        self.assertIn('ClerkOne', result)
        self.assertIn('ClerkTwo', result)
        self.assertNotIn('FormerClerk', result)

    def test_does_not_include_users_before_active_section(self):
        self.mock_page.text = '\n'.join([
            '{{User|NotAClerk}}',
            '=== Active clerks ===',
            '{{User|RealClerk}}',
            '=== Inactive clerks ===',
        ])
        result = run_bot.get_clerk_list()
        self.assertIn('RealClerk', result)
        self.assertNotIn('NotAClerk', result)

    def test_capitalizes_first_letter_of_username(self):
        self.mock_page.text = '\n'.join([
            '=== Active clerks ===',
            '{{User|lowercase}}',
            '=== Inactive clerks ===',
        ])
        result = run_bot.get_clerk_list()
        self.assertIn('Lowercase', result)
        self.assertNotIn('lowercase', result)

    def test_returns_empty_set_when_no_active_section(self):
        self.mock_page.text = '{{User|SomeUser}}'
        result = run_bot.get_clerk_list()
        self.assertEqual(result, set())


# ---------------------------------------------------------------------------
# get_quick_cu_requests
# ---------------------------------------------------------------------------

class TestGetQuickCuRequests(unittest.TestCase):

    def setUp(self):
        self.mock_page = MagicMock()
        self.mock_page.editTime.return_value = datetime(2026, 3, 22, 10, 0)
        run_bot.pywikibot.Page.return_value = self.mock_page

    def test_open_request_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick}}',
        ])
        result = run_bot.get_quick_cu_requests()
        self.assertEqual(len(result), 1)
        self.assertIn('Example case', result[0]['name'])
        self.assertEqual(result[0]['status'], 'QUICK')

    def test_open_request_with_empty_param_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick|}}',
        ])
        result = run_bot.get_quick_cu_requests()
        self.assertEqual(len(result), 1)

    def test_done_request_not_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick|done}}',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_close_request_not_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick|close}}',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_closed_request_not_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick|closed}}',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_archive_request_not_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick|archive}}',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_cases_outside_quick_section_ignored(self):
        self.mock_page.text = '\n'.join([
            '=== Some other section ===',
            '==== Example case ====',
            '{{SPIquick}}',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_cases_after_quick_section_ends_ignored(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Open case ====',
            '{{SPIquick}}',
            '=== Another section ===',
            '==== Should be ignored ====',
            '{{SPIquick}}',
        ])
        result = run_bot.get_quick_cu_requests()
        self.assertEqual(len(result), 1)
        self.assertIn('Open case', result[0]['name'])

    def test_name_includes_link_and_label(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            '{{SPIquick}}',
        ])
        result = run_bot.get_quick_cu_requests()
        self.assertEqual(
            result[0]['name'],
            'link=Wikipedia:Sockpuppet investigations#Example case|Quick check: Example case'
        )

    def test_case_without_spiequick_template_not_added(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Example case ====',
            'Some text with no template',
        ])
        self.assertEqual(run_bot.get_quick_cu_requests(), [])

    def test_multiple_open_and_closed_requests(self):
        self.mock_page.text = '\n'.join([
            '=== Quick CheckUser requests ===',
            '==== Case one ====',
            '{{SPIquick}}',
            '==== Case two ====',
            '{{SPIquick|}}',
            '==== Case three ====',
            '{{SPIquick|done}}',
        ])
        result = run_bot.get_quick_cu_requests()
        self.assertEqual(len(result), 2)
        names = [r['name'] for r in result]
        self.assertTrue(any('Case one' in n for n in names))
        self.assertTrue(any('Case two' in n for n in names))


# ---------------------------------------------------------------------------
# get_case_details
# ---------------------------------------------------------------------------

class TestGetCaseDetails(unittest.TestCase):

    def setUp(self):
        self.ts_mock = MagicMock()
        self.ts_mock.timestripper.return_value = None
        run_bot.textlib.TimeStripper.return_value = self.ts_mock

    def _make_page(self, title, cat_names, revisions, text=''):
        page = MagicMock()
        page.title.return_value = title
        page.categories.return_value = [make_category(c) for c in cat_names]
        page.revisions.return_value = iter(revisions)
        page.text = text
        return page

    def test_name_extracted_from_spi_namespace(self):
        rev = make_revision('SomeUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page)
        # split('/', 1)[1] strips everything up to and including the first '/'
        self.assertEqual(case['name'], 'Foobar')

    def test_name_preserves_subpages_in_spi_namespace(self):
        rev = make_revision('SomeUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foo/Bar',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['name'], 'Foo/Bar')

    def test_name_uses_link_hack_outside_spi_namespace(self):
        rev = make_revision('SomeUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Some other page',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['name'], 'link=Wikipedia:Some other page|Wikipedia:Some other page')

    def test_last_user_is_most_recent_editor(self):
        revs = [
            make_revision('RecentUser', datetime(2026, 3, 22, 10, 0)),
            make_revision('OlderUser',  datetime(2026, 3, 21, 10, 0)),
        ]
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            revs
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['last_user'], 'RecentUser')

    def test_last_clerk_set_when_most_recent_editor_is_clerk(self):
        rev = make_revision('ClerkUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page, clerks={'ClerkUser'})
        self.assertEqual(case['last_clerk'], 'ClerkUser')
        self.assertEqual(case['last_clerk_time'], '2026-03-22 10:00')

    def test_last_clerk_found_in_revision_history(self):
        revs = [
            make_revision('RegularUser', datetime(2026, 3, 22, 10, 0)),
            make_revision('ClerkUser',   datetime(2026, 3, 21, 10, 0)),
        ]
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            revs
        )
        case = run_bot.get_case_details(page, clerks={'ClerkUser'})
        self.assertEqual(case['last_clerk'], 'ClerkUser')

    def test_clerk_search_stops_at_archive_edit_summary(self):
        revs = [
            make_revision('RegularUser',  datetime(2026, 3, 22, 10, 0)),
            make_revision('RegularUser2', datetime(2026, 3, 21, 12, 0), comment='Archiving case'),
            make_revision('ClerkUser',    datetime(2026, 3, 21, 10, 0)),
        ]
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            revs
        )
        case = run_bot.get_case_details(page, clerks={'ClerkUser'})
        self.assertEqual(case['last_clerk'], '')

    def test_clerk_search_stops_at_moving_case_edit_summary(self):
        revs = [
            make_revision('RegularUser',  datetime(2026, 3, 22, 10, 0)),
            make_revision('RegularUser2', datetime(2026, 3, 21, 12, 0), comment='moving case to Foobar2'),
            make_revision('ClerkUser',    datetime(2026, 3, 21, 10, 0)),
        ]
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            revs
        )
        case = run_bot.get_case_details(page, clerks={'ClerkUser'})
        self.assertEqual(case['last_clerk'], '')

    def test_lowercase_username_applied_to_last_user(self):
        rev = make_revision('Asilvering', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['last_user'], 'asilvering')

    def test_lowercase_username_applied_to_last_clerk(self):
        rev = make_revision('Asilvering', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev]
        )
        case = run_bot.get_case_details(page, clerks={'Asilvering'})
        self.assertEqual(case['last_clerk'], 'asilvering')

    def test_file_time_unknown_when_no_timestamp_in_text(self):
        self.ts_mock.timestripper.return_value = None
        rev = make_revision('SomeUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev],
            text='No timestamp here'
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['file_time'], 'Unknown')

    def test_file_time_parsed_from_page_text(self):
        fake_time = datetime(2026, 3, 20, 8, 30)
        self.ts_mock.timestripper.return_value = fake_time
        rev = make_revision('SomeUser', datetime(2026, 3, 22, 10, 0))
        page = self._make_page(
            'Wikipedia:Sockpuppet investigations/Foobar',
            ['SPI cases needing a Clerk'],
            [rev],
            text='Filed by SomeUser at 08:30, 20 March 2026'
        )
        case = run_bot.get_case_details(page)
        self.assertEqual(case['file_time'], '2026-03-20 08:30')


if __name__ == '__main__':
    unittest.main()
