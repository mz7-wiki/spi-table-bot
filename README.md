# spi-table-bot

A [pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot)-based bot that automatically updates the open case table at [Wikipedia:Sockpuppet investigations/SPI/Cases](https://en.wikipedia.org/wiki/Wikipedia:Sockpuppet_investigations/SPI/Cases) on the English Wikipedia.

## What it does

The bot runs every 10 minutes and scans three sources for open SPI cases:

1. **[Category:Open SPI cases](https://en.wikipedia.org/wiki/Category:Open_SPI_cases)** — the main source of active sockpuppet investigation pages. For each page, the bot reads the case's categories to determine its status (e.g. `clerk`, `admin`, `CUrequest`), finds the most recent editor and most recent clerk/checkuser, and extracts the filing timestamp from the page text.

2. **[Category:Requests for checkuser](https://en.wikipedia.org/wiki/Category:Requests_for_checkuser)** — pages outside the SPI namespace that transclude a `{{checkuser needed}}`-style template. These appear in the table as `CU needed: <page title>`.

3. **[Wikipedia:Sockpuppet investigations](https://en.wikipedia.org/wiki/Wikipedia:Sockpuppet_investigations)** — the bot scans the `===Quick CheckUser requests===` section for level-4 subsections containing an open `{{SPIquick}}` template. Requests marked as `{{SPIquick|done}}`, `{{SPIquick|close}}`, `{{SPIquick|closed}}`, or `{{SPIquick|archive}}` are skipped.

Cases are then sorted and written to the case table using the `{{SPIstatusentry}}` template.

## Running the bot

The bot requires pywikibot to be installed and configured with a valid account (see [here](https://www.mediawiki.org/wiki/Manual:Pywikibot/Installation) for how to install pywikibot). It is scheduled as a Toolforge job (see [here](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Running_jobs) for more info about Toolforge jobs):

```
python3 run_bot.py
```

## Running the unit tests

The test suite uses Python's built-in `unittest` module and mocks all pywikibot calls, so no Wikipedia account or network access is needed.

```
python3 -m unittest test_run_bot -v
```

## Frequency of cases in the table

Sometimes, the same case name may appear multiple times in the SPI table if there are multiple statuses associated with that case name, but not all the time. The logic for this is somewhat convoluted. It is based on Dreamy Jazz's suggestion from [this discussion](https://en.wikipedia.org/wiki/Wikipedia_talk:Sockpuppet_investigations/Archive_23#Amaltheabot_malfunctioning) back in May 2021. Originally, when Amalthea's bot was the one updating the table, SPI cases would appear only once in the table, and there was probably some kind of hierarchy that decided which one takes priority. We decided that there are certain times where we want to have a case appear multiple times in the table, but we didn't want to just throw *all* of the statuses on the table, lest it grow too long.

1. **Category 1**: if a case has one of these statuses, then it will *always* appear in the table under that status:
    * new
    * clerk
    * admin
    * checked
    * close
2. **Category 2**: if a case has one of these statuses, then *one* of them will always appear in the table (listed in order of highest to lowest priority):
    * inprogress
    * relist
    * endorsed
    * CUrequest
3. **Category 3**: if none of the Category 1 or 2 statuses are present, then an SPI case name will only appear once in the table. The order of the following list determines which status is the one the case name appears as:
    * open
    * cudeclined
    * declined
    * cumoreinfo
    * moreinfo
    * cuhold
    * hold

For example, if an SPI has the statuses "CUrequest", "clerk", "close", "endorsed", "open", and "moreinfo", then it will appear 3 times in the SPI case table as "endorsed", "clerk", and "close". "clerk" and "close" appear because they are Category 1. "CUrequest" does not appear because it is trumped by the "endorsed" in Category 2, and "open" and "moreinfo" do not appear because Category 3 statuses will only appear if no other status is present. If the case only had the statuses "open" and "moreinfo", then it would only appear once in the table as "open" because that trumps "moreinfo".

The rationale for having "close" always appear (i.e. Category 1) was that sometimes if a sockmaster is very prolific, there will often be a case open for that sockmaster, and if "close" gets hidden by any active case, then for those sockmasters, a backlog of closed, waiting-to-be-archived cases starts to pile up.
