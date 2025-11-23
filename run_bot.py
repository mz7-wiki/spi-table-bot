import pywikibot
from pywikibot import pagegenerators, textlib
import re
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Rotate logs whenever we reach 100 MB
# It will keep 3 log files of 100 MB long - the oldest file will be deleted
file_handler = RotatingFileHandler(
    '/data/project/spi-table-bot/logs/spi-table-bot.log',
    maxBytes=100 * 1024 * 1024,  # 100 MB
    backupCount=3
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

site = pywikibot.Site('en', 'wikipedia')
TABLE_LOCATION = 'Wikipedia:Sockpuppet investigations/SPI/Cases'  # location where this program should post the SPI case list

LOWERCASE_USERNAMES = {'Asilvering'}

def get_clerk_list():
	"""
	Retrieve the list of active clerks from WP:SPICL

	The procedure for this is as follows (also documented in the hidden text
	at WP:SPICL itself):

	1. First we scan the page [[Wikipedia:Sockpuppet investigations/SPI/Clerks]]
	   for the first section containing the string 'Active clerks'
	2. In that section and its subsections, match each line looking for the first
	   template that starts with 'user', and assume it takes the username as an
	   anonymous first parameter.
	"""
	logger.info("Getting list of clerks")
	clerks = set()
	page = pywikibot.Page(site, 'Wikipedia:Sockpuppet investigations/SPI/Clerks')
	lines = page.text.split('\n')

	# Scan through the lines of Wikipedia:Sockpuppet investigations/SPI/Clerks
	# until we see a line containing the string "Active clerks"
	i = 0
	while i < len(lines) and 'Active clerks' not in lines[i]:
		i += 1

	# Now on each subsequent line until we see one that has "inactive clerks" in it,
	# look for templates that start with 'user' and grab the first anonymous parameter.
	#
	# Explanation of regex:
	# - Looking for a line that starts with '{{user' or '{{User'
	# - [^\|]* looks for any character that is not '|' (part of template name)
	# - ([^}]+) is what we're looking for: any character that is not '}', which
	#   would be the anonymous first parameter of the user template
	pattern = re.compile(r'{{(?:u|U)ser[^\|]*\|([^}]+)}}')
	while i < len(lines) and 'inactive clerks' not in lines[i].lower():
		m = pattern.search(lines[i])
		if m:
			username = m.group(1)

			# Make the first character of the username case insenstive.
			# This is for clerks who prefer to have the first letter of their
			# username be lowercase in the list.
			username = username[0].upper() + username[1:]

			clerks.add(username)
		i += 1

	logger.info(clerks)
	return clerks


def get_checkuser_list():
	logger.info("Getting list of checkusers")
	checkusers = {user['name'] for user in site.allusers(group='checkuser')}
	logger.info(checkusers)
	return checkusers


def get_status_from_categories(categories):
	"""
	For concision, cases will usually appear in the SPI case table only once, except that
	the following statuses will always appear: clerk, admin, checked, close, and one of 
	(inprogress, endorsed, relist, CUrequest).
	
	For example, if an SPI case has five active reports, one with 'clerk', one with 'close'
	one with 'endorsed', one with 'CUrequest', and one with 'open', it will appear three times
	in the table as 'clerk', 'close', and 'endorsed'.
	"""
	logger.debug("Getting case status")
	cat2status = {
		'SPI cases currently being checked': 'inprogress',
		'SPI cases awaiting a CheckUser': 'endorsed',
		'SPI cases relisted for a CheckUser': 'relist',
		'SPI cases requesting a checkuser': 'CUrequest',
		'SPI cases needing an Administrator': 'admin',
		'SPI cases needing a Clerk': 'clerk',
		'SPI cases CU complete': 'checked',
		'New SPI cases': 'new',
		'SPI cases awaiting review': 'open',
		'SPI cases declined for checkuser by CU': 'cudeclined',
		'SPI cases declined for checkuser by clerk': 'declined',
		'SPI cases requesting more information': 'moreinfo',
		'SPI cases on hold by checkuser': 'cuhold',
		'SPI cases on hold by clerk': 'hold',
		'SPI cases awaiting archive': 'close',
	}

	# get category names as strings from the category objects
	cat_titles = [cat.title(with_ns=False) for cat in categories]

	# from the category names, get all of the possible case statuses for this case
	statuses = []
	for title in cat_titles:
		if title == 'SPI cases requesting more information' and 'SPI cases for pre-CheckUser review' in cat_titles:
			# special case where more info is requested for a CU request
			statuses.append('cumoreinfo')
		elif title in cat2status:
			statuses.append(cat2status[title])

	# from the possible case statuses, we'll now choose the ones the display on the
	# final table and place them in the 'result' list according to the logic described above
	priority = ['clerk', 'admin', 'checked', 'close']
	result = []
	curequest = {'inprogress': 0, 'relist': 1, 'endorsed': 2, 'CUrequest': 3}
	curequest_only = []
	misc = {'new': 0, 'open': 1, 'cudeclined': 2, 'declined': 3, 'cumoreinfo': 4, 'moreinfo': 5, 'cuhold': 6, 'hold': 7}
	misc_only = []
	for status in statuses:
		if status in priority:
			result.append(status)
		elif status in curequest:
			curequest_only.append(status)
		elif status in misc:
			misc_only.append(status)
	if curequest_only:
		result.append(min(curequest_only, key=lambda x: curequest[x]))
	if misc_only and (len(result) == 0 or (len(result) == 1 and result[0] == 'close')):
		result.append(min(misc_only, key=lambda x: misc[x]))
	return result


def get_case_details(case_page, clerks=set()):
	case_title = case_page.title()
	logger.info(f"Now getting case details for {case_title}")
	case = {}

	# get case name
	if case_title.startswith("Wikipedia:Sockpuppet investigations/"):
		# everything after the first '/' in the string
		case['name'] = case_title.split('/', 1)[1]
	else:
		# rare case in which a case name isn't in the SPI namespace
		# the implementation for 'name' below is a bit of a hack: it adds a named parameter "|link="
		# and then assumes 'name' is the first unnamed positional parameter |1= (see format_table_row below)
		case['name'] = f"link={case_title}|{case_title}"

	# get case status
	case['status'] = get_status_from_categories(case_page.categories())

	# get page revisions
	revisions = case_page.revisions()

	# get last user and time
	logger.debug("Getting last user")
	last_rev = next(revisions)
	case['last_user'] = last_rev.user
	case['last_user_time'] = last_rev.timestamp.strftime('%Y-%m-%d %H:%M')

	# get last clerk/checkuser and time
	# the clerks list passed as a parameter also includes checkusers
	logger.debug("Getting last clerk or checkuser")
	if last_rev.user in clerks:
		case['last_clerk'] = last_rev.user
		case['last_clerk_time'] = last_rev.timestamp.strftime('%Y-%m-%d %H:%M')
	else:
		case['last_clerk'] = ''
		case['last_clerk_time'] = ''
		for rev in revisions:
			lowercase_edit_summary = rev.comment.lower()
			if 'archiv' in lowercase_edit_summary or 'moving case' in lowercase_edit_summary:
				# only look for clerks/CUs up to the last archive or case moved to another case
				break
			if rev.user in clerks:
				case['last_clerk'] = rev.user
				case['last_clerk_time'] = rev.timestamp.strftime('%Y-%m-%d %H:%M')
				break

	# a little hardcoded easter egg because asilvering likes their username lowercase
	# let me know if this breaks anything and I can remove it lol
	if case['last_user'] in LOWERCASE_USERNAMES:
		case['last_user'] = case['last_user'].lower()
	if case['last_clerk'] in LOWERCASE_USERNAMES:
		case['last_clerk'] = case['last_clerk'].lower()

	# get file time
	logger.debug("Getting file time")
	ts = textlib.TimeStripper(site)
	case_lines = case_page.text.split('\n')
	for line in case_lines:
		time = ts.timestripper(line)
		if time:
			break
	if time:
		case['file_time'] = time.strftime('%Y-%m-%d %H:%M')
	else:
		case['file_time'] = 'Unknown'

	logger.info(case)

	return case


def format_table_row(case):
	return "{{" + "SPIstatusentry|{0}|{1}|{2}|{3}|{4}|{5}|{6}".format(
		case['name'],
		case['status'],
		case['file_time'],
		case['last_user'],
		case['last_user_time'],
		case['last_clerk'],
		case['last_clerk_time']
		) + "}}\n"


def generate_case_table(cases):
	result = "{{SPIstatusheader}}\n"
	for case in cases:
		result += format_table_row(case)
	result += '|}'
	if len(cases) == 0:
		logger.info("No SPI cases detected!")
		result += '{{User:Mz7/SPI 0}}'
	return result


def sort_cases(cases):
	"""
	Order of the SPI case table
	"""
	rank = {
		'inprogress': 0,
		'endorsed': 1,
		'relist': 2,
		'QUICK': 3,
		'CUrequest': 4,
		'admin': 5,
		'clerk': 6,
		'checked': 7,
		'new': 8,
		'open': 9,
		'cudeclined': 10,
		'declined': 11,
		'cumoreinfo': 12,
		'moreinfo': 13,
		'cuhold': 14,
		'hold': 15,
		'close': 16
	}
	return sorted(cases, key=lambda case: (rank[case['status']], case['file_time']))


def get_all_cases(clerks):
	cat = pywikibot.Category(site, 'Category:Open SPI cases')
	gen = pagegenerators.CategorizedPageGenerator(cat)
	cases = []
	for page in gen:
		case = get_case_details(page, clerks)
		if len(case['status']) > 1:
			statuses = case['status']
			for status in statuses:
				case_copy = case.copy()
				case_copy['status'] = status
				cases.append(case_copy)
		else:
			try:
				case['status'] = case['status'][0]
				cases.append(case)
			except IndexError:
				logger.exception(f"The following case may have been archived while the case details were being grabbed: {case}")
	cases += get_cu_needed_templates()
	return sort_cases(cases)


def get_cu_needed_templates():
	logger.info("Getting CU needed templates")
	cat = pywikibot.Category(site, 'Category:Requests for checkuser')
	gen = pagegenerators.CategorizedPageGenerator(cat)
	cases = []
	for page in gen:
		# ignoring User and Template namespaces because of the issue where some users transclude AIV etc. in those namespaces
		if page.namespace() == 2 or page.namespace() == 10:
			continue
		cases.append({
			# the implementation for 'name' below is a bit of a hack: it adds a named parameter "|link="
			# and then assumes 'name' is the first unnamed positional parameter |1= (see format_table_row above)
			'name': 'link={0}#checkuser_needed|CU needed: {0}'.format(page.title()),
			'status': 'QUICK',
			'file_time': page.editTime().strftime('%Y-%m-%d %H:%M'),
			'last_user': '',
			'last_user_time': '',
			'last_clerk': '',
			'last_clerk_time': ''
		})
	if cases:
		logger.info(cases)
	else:
		logger.info("No CU needed templates found")
	return cases


def main():
	clerks = get_clerk_list() | get_checkuser_list()
	cases = get_all_cases(clerks)
	page = pywikibot.Page(site, TABLE_LOCATION)
	page.text = generate_case_table(cases)
	page.save(summary=f'Updating SPI case list ({len(cases)} active reports)', minor=False, botflag=True)
	logger.info(f'Successfully updated SPI case list ({len(cases)} active reports)')


if __name__ == "__main__":
    main()
