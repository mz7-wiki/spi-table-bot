import pywikibot
from pywikibot import pagegenerators, textlib
import re

site = pywikibot.Site('en', 'wikipedia')
TABLE_LOCATION = 'User:Mz7/SPI case list'  # location where this program should post the SPI case list


def get_clerk_list():
	clerks = []
	page = pywikibot.Page(site, 'Wikipedia:Sockpuppet investigations/SPI/Clerks')
	lines = page.text.split('\n')
	i = 0
	while i < len(lines) and 'Active clerks' not in lines[i]:
		i += 1
	pattern = re.compile(r'{{(?:u|U)ser[^\|]*\|([^}]+)}}')
	while i < len(lines) and 'inactive clerks' not in lines[i].lower():
		m = pattern.search(lines[i])
		if m:
			clerks.append(m.group(1))
		i += 1
	return clerks


def get_status_from_categories(categories):
	"""
	For concision, each case will only appear one time in the list. The following
	order determines the case's status if there are multiple reports on the same
	case with different statuses.

	Hierarchy:
		inprogress > endorsed > relist > CUrequest > admin > clerk > checked > open > 
		cudeclined > declined > moreinfo > cuhold > hold > close
	"""
	print("Getting case status")
	cat2status = {
		'SPI cases currently being checked': ('inprogress', 0),
		'SPI cases awaiting a CheckUser': ('endorsed', 1),
		'SPI cases relisted for a checkuser': ('relist', 2),
		'SPI cases requesting a checkuser': ('CUrequest', 3),
		'SPI cases needing an Administrator': ('admin', 4),
		'SPI cases needing a Clerk': ('clerk', 5),
		'SPI cases CU complete': ('checked', 6),
		'SPI cases awaiting review': ('open', 7),
		'SPI cases declined for checkuser by CU': ('cudeclined', 8),
		'SPI cases declined for checkuser by clerk': ('declined', 9),
		'SPI cases requesting more information': ('moreinfo', 10),
		'SPI cases on hold by checkuser': ('cuhold', 11),
		'SPI cases on hold by clerk': ('hold', 12),
		'SPI cases awaiting archive': ('close', 13)
	}
	statuses = []
	for cat in categories:
		title = cat.title(with_ns=False)
		if title in cat2status.keys():
			statuses.append(cat2status[title])
	return min(statuses, key=lambda x: x[1])[0]


def get_case_details(case_page, clerks=[]):
	print("Now getting case details for {0}".format(case_page.title()))
	case = {}

	# get case name
	case['name'] = case_page.title().split("/")[1]

	# get case status
	case['status'] = get_status_from_categories(case_page.categories())

	# get page revisions
	revisions = case_page.revisions()

	# get last user and time
	print("Getting last user")
	last_rev = next(revisions)
	case['last_user'] = last_rev.user
	case['last_user_time'] = last_rev.timestamp.strftime('%Y-%m-%d %H:%M')

	# get last clerk and time
	print("Getting last clerk")
	last_user = pywikibot.User(site, last_rev.user)
	if last_rev.user in clerks or 'checkuser' in last_user.groups():
		case['last_clerk'] = last_rev.user
		case['last_clerk_time'] = last_rev.timestamp.strftime('%Y-%m-%d %H:%M')
	else:
		case['last_clerk'] = ''
		case['last_clerk_time'] = ''
		for rev in revisions:
			if 'archiv' in rev.comment.lower() or 'moving' in rev.comment.lower() or 'moved' in rev.comment.lower():
				break
			rev_user = pywikibot.User(site, rev.user)
			if rev.user in clerks or 'checkuser' in rev_user.groups():
				case['last_clerk'] = rev.user
				case['last_clerk_time'] = rev.timestamp.strftime('%Y-%m-%d %H:%M')

	# get file time
	print("Getting file time")
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

	print(case)

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
	return result


def sort_cases(cases):
	"""
	Order of the SPI case table:
	inprogress, endorsed, relisted, CUrequest, checked, open, admin, clerk, moreinfo,
	declined, cudeclined, hold, cuhold, close
	"""
	rank = {'inprogress': 0, 'endorsed': 1, 'relisted': 2, 'CUrequest': 3, 'checked': 4,
	'open': 5, 'admin': 6, 'clerk': 7, 'moreinfo': 8, 'declined': 9, 'cudeclined': 10, 'hold': 11,
	'cuhold': 12, 'close': 13}
	return sorted(cases, key=lambda case: (rank[case['status']], case['file_time']))


def main():
	clerks = get_clerk_list()
	
	cat = pywikibot.Category(site, 'Category:Open SPI cases')
	gen = pagegenerators.CategorizedPageGenerator(cat)
	cases = sort_cases([get_case_details(page, clerks) for page in gen])
	
	page = pywikibot.Page(site, TABLE_LOCATION)
	page.text = generate_case_table(cases)
	page.save(summary='Updating SPI case list ({0} open cases)'.format(len(cases)), minor=False)


main()