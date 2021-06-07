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
	For concision, cases will usually appear in the SPI case table only once, except that
	the following statuses will always appear: clerk, admin, checked, close, and one of 
	(inprogress, endorsed, relist, CUrequest).
	
	For example, if an SPI case has five active reports, one with 'clerk', one with 'close'
	one with 'endorsed', one with 'CUrequest', and one with 'open', it will appear three times
	in the table as 'clerk', 'close', and 'endorsed'.
	"""
	print("Getting case status")
	cat2status = {
		'SPI cases currently being checked': 'inprogress',
		'SPI cases awaiting a CheckUser': 'endorsed',
		'SPI cases relisted for a checkuser': 'relist',
		'SPI cases requesting a checkuser': 'CUrequest',
		'SPI cases needing an Administrator': 'admin',
		'SPI cases needing a Clerk': 'clerk',
		'SPI cases CU complete': 'checked',
		'SPI cases awaiting review': 'open',
		'SPI cases declined for checkuser by CU': 'cudeclined',
		'SPI cases declined for checkuser by clerk': 'declined',
		'SPI cases requesting more information': 'moreinfo',
		'SPI cases on hold by checkuser': 'cuhold',
		'SPI cases on hold by clerk': 'hold',
		'SPI cases awaiting archive': 'close',
	}
	statuses = []
	for cat in categories:
		title = cat.title(with_ns=False)
		if title in cat2status:
			statuses.append(cat2status[title])

	priority = ['clerk', 'admin', 'checked', 'close']
	result = []
	curequest = {'inprogress': 0, 'endorsed': 1, 'relist': 2, 'CUrequest': 3}
	curequest_only = []
	misc = {'open': 0, 'cudeclined': 1, 'declined': 2, 'moreinfo': 3, 'cuhold': 4, 'hold': 5}
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
	inprogress > endorsed > relist > CUrequest > admin > clerk > checked > open > cudeclined >
	declined > moreinfo > cuhold > hold > close
	"""
	rank = {'inprogress': 0, 'endorsed': 1, 'relisted': 2, 'CUrequest': 3, 'admin': 4,
	'clerk': 5, 'checked': 6, 'open': 7, 'cudeclined': 8, 'declined': 9, 'moreinfo': 10, 'cuhold': 11,
	'hold': 12, 'close': 13}
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
			except IndexError as e:
				print(e)
				print("The following case may have been archived while the case details were being grabbed:")
				print(case)
	return sort_cases(cases)


def main():
	clerks = get_clerk_list()
	cases = get_all_cases(clerks)
	page = pywikibot.Page(site, TABLE_LOCATION)
	page.text = generate_case_table(cases)
	page.save(summary='Updating SPI case list ({0} active reports)'.format(len(cases)), minor=False, botflag=True)


main()