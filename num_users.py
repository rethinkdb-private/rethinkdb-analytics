#! /usr/bin/env python
import os, sys
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import argparse
import collections
from prettytable import PrettyTable

LOG_FILES_DIR = 'update_logs'
DATE_FMT = '%Y-%m-%d'

# Roll a date back to the most recent Monday
def roll_back_a_week(adate):
    return adate - timedelta(days=adate.weekday())

# Roll a date forward a week
def roll_forward_a_week(adate):
    return adate + timedelta(7)

# Roll a date back to the first day of the month
def roll_back_a_month(adate):
    return adate - timedelta(days=(adate.day - 1))

# Roll a date forward a month
def roll_forward_a_month(adate):
    return adate + relativedelta(months=1)

# Pretty-print a date range
def pp_dates(from_date,to_date):
    date_fmt = "%b %d"
    date_range = from_date.strftime(date_fmt) + " - " + to_date.strftime(date_fmt)
    return date_range

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Report usage statistics based on an interval. Accepts an interval in days, and aggregates data over this interval since the beginning of time.')
parser.add_argument('interval', nargs=1, default='week', help='interval to analyze: week, month')
parser.add_argument('--cached', action='store_true', help='use cached logs instead of fetching new logs via rsync.')
args = parser.parse_args()

interval = args.interval[0]
if interval != 'week' and interval != 'month':
    print "%s is not a recognized interval, use: week, month" % interval
    sys.exit()

# Fetch log files (and create the directory they'll live in if it doesn't exist)
if not os.path.exists(LOG_FILES_DIR):
    os.makedirs(LOG_FILES_DIR)
if not args.cached:
    os.system("rsync -Pavzrh -e 'ssh -p 440' teapot@rethinkdb.com:/srv/www/update.rethinkdb.com/flask_logs/ %s" % LOG_FILES_DIR)

ips_per_date = []
for f in sorted(os.listdir(LOG_FILES_DIR)):
    file_date = datetime.strptime(os.path.splitext(f)[0], DATE_FMT)

    ips = []
    with open(os.path.join(LOG_FILES_DIR,f),'r') as log:
        for row in log.readlines():
            ips.append(row.split()[3])

    ips_per_date.append({
        'datetime': file_date,
        'ips': ips,
    })


first_date = ips_per_date[0]['datetime']

if interval == 'week':
    from_date = roll_back_a_week(first_date)
    to_date = roll_forward_a_week(from_date)
elif interval == 'month':
    from_date = roll_back_a_month(first_date)
    to_date = roll_forward_a_month(from_date)


i = 0
buckets = []
bucket = []
while True:
    # We've gone through all the log files
    if i >= len(ips_per_date):
        # If this bucket had any dates in it, keep the partial bucket, then end the loop
        if len(bucket) > 0:
            buckets.append(bucket)
        break

    date = ips_per_date[i]['datetime']
    # If the date of this log file is out of range, this bucket is full
    if not from_date <= date < to_date:
        buckets.append(bucket)
        bucket = []

        # Move the range up to the next interval (week / month)
        from_date = to_date
        if interval == 'week':
            to_date = roll_forward_a_week(to_date)
        elif interval == 'month':
            to_date = roll_forward_a_month(to_date)
        continue

    # Keep building this bucket!
    bucket.append(ips_per_date[i])
    i += 1

existing_ips = set() # this is a set so each element only appears exactly once
all_ips = []
table_rows = [] # rows for the results table
for bucket in buckets:
    ips_for_bucket = [ip for day in bucket for ip in day['ips']] # list comprehension for nested lists
    all_ips += ips_for_bucket # first add to the global set

    # set operations to determine vital stats
    uniques_for_bucket = set(ips_for_bucket)
    new_for_bucket = uniques_for_bucket - existing_ips
    num_existing = len(uniques_for_bucket) - len(new_for_bucket)

    # add onto our list of known ips
    existing_ips.update(uniques_for_bucket)

    # record a summary for this row
    daterange = pp_dates(bucket[0]['datetime'],bucket[-1]['datetime'])
    table_rows.append([daterange, len(ips_for_bucket), len(uniques_for_bucket), len(new_for_bucket), num_existing])

# Build the table
x = PrettyTable(["date range","hits","uniques","new users", "existing users"])
for row in table_rows:
    x.add_row(row)
print x

daterange = pp_dates(buckets[0][0]['datetime'],buckets[-1][-1]['datetime'])
print "Total stats for %s:\n\t%d hits\n\t%d unique users" % (daterange, len(all_ips), len(existing_ips))
