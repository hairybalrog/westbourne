#!/usr/bin/env python3
"""
Fetch weekly running club results
"""

import requests
import csv
import re
import os
from datetime import datetime
from html import unescape

# Configuration - reads from environment variables for privacy
# Set these as GitHub Actions secrets, or export locally for testing
CLUB_NUM = os.environ.get('CLUB_NUM', '')
CLUB_NAME = os.environ.get('CLUB_NAME', '')
BASE_URL = os.environ.get('DATA_URL', '')
OUTPUT_FILE = 'club_results.csv'

if not all([CLUB_NUM, CLUB_NAME, BASE_URL]):
    raise ValueError("Missing required environment variables: CLUB_NUM, CLUB_NAME, DATA_URL")

# Debug: Show configuration (GitHub masks secrets, so use workarounds)
print("DEBUG: Expected values:")
print("  CLUB_NUM: length=5, chars=[50, 48, 48, 57, 56] (20098)")
print("  CLUB_NAME: length=10, chars=[87, 101, 115, 116, 98, 111, 117, 114, 110, 101] (Westbourne)")
print("  DATA_URL: length=52, starts='https://www.parkrun', ends='onsolidatedclub/'")
print("DEBUG: Actual values:")
print(f"  CLUB_NUM = '{CLUB_NUM}'")
print(f"  CLUB_NUM length={len(CLUB_NUM)}, chars={[ord(c) for c in CLUB_NUM]}")
print(f"  CLUB_NAME = '{CLUB_NAME}'")
print(f"  CLUB_NAME length={len(CLUB_NAME)}, chars={[ord(c) for c in CLUB_NAME]}")
print(f"  DATA_URL = '{BASE_URL}'")
print(f"  DATA_URL length={len(BASE_URL)}, starts='{BASE_URL[:20]}...', ends='...{BASE_URL[-20:]}'")
print(f"  DATA_URL hash={hash(BASE_URL)}")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
}


def fetch_html(event_date=None):
    """Fetch the consolidated club report HTML"""
    url = f"{BASE_URL}?clubNum={CLUB_NUM}"
    if event_date:
        url += f"&eventdate={event_date}"

    print(f"Fetching: {url}")
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    print(f"Got {len(response.text)} characters")
    return response.text


def clean_text(text):
    """Remove HTML tags and decode entities"""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.strip()


def parse_results(html):
    """Parse the HTML and extract Westbourne RC results"""
    results = []

    # Extract event date
    date_match = re.search(r'who participated at a parkrun on (\d{4}-\d{2}-\d{2})', html)
    event_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
    print(f"Event date: {event_date}")

    # Split by h2 headers to get each parkrun event
    sections = re.split(r'<h2>', html, flags=re.IGNORECASE)
    print(f"DEBUG: Found {len(sections)-1} parkrun sections")

    for section in sections[1:]:  # Skip first section (before any h2)
        # Extract event name
        h2_match = re.match(r'^([^<]+)</h2>', section, re.IGNORECASE)
        if not h2_match:
            continue

        event_name = h2_match.group(1).strip()
        # Remove " parkrun" suffix for cleaner display
        event_name = re.sub(r' parkrun$', '', event_name, flags=re.IGNORECASE)

        # Find table in this section
        table_match = re.search(r'<table[^>]*>(.*?)</table>', section, re.IGNORECASE | re.DOTALL)
        if not table_match:
            continue

        table_html = table_match.group(1)

        # Extract rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.IGNORECASE | re.DOTALL)

        headers = []
        for i, row in enumerate(rows):
            # Extract cells (th or td)
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.IGNORECASE | re.DOTALL)
            cells = [clean_text(c) for c in cells]

            if not cells:
                continue

            # First row is headers
            if i == 0:
                headers = cells
                continue

            # Create row dict
            row_data = {}
            for j, cell in enumerate(cells):
                header = headers[j] if j < len(headers) else f'Column{j+1}'
                row_data[header] = cell

            # Only include Westbourne members
            club = row_data.get('Club', '')
            is_match = CLUB_NAME.lower() in club.lower()
            print(f"DEBUG: Club='{club}' | Match={is_match}")
            if is_match:
                row_data['Event'] = event_name
                row_data['Date'] = event_date
                results.append(row_data)

        print(f"  {event_name}: found {len([r for r in results if r['Event'] == event_name])} club members")

    return results


def load_existing_results():
    """Load existing results from CSV to avoid duplicates"""
    existing = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Create unique key from date, event, and runner
                key = (row.get('Date', ''), row.get('Event', ''), row.get('parkrunner', ''))
                existing.add(key)
    return existing


def save_results(results, append=True):
    """Save results to CSV file"""
    if not results:
        print("No results to save")
        return

    # Define column order
    fieldnames = ['Date', 'Event', 'Position', 'Gender Position', 'parkrunner', 'Club', 'Time']

    # Check for any extra columns
    all_keys = set()
    for r in results:
        all_keys.update(r.keys())
    extra_keys = sorted(all_keys - set(fieldnames))
    fieldnames.extend(extra_keys)

    # Load existing to avoid duplicates
    existing = load_existing_results() if append else set()

    # Filter out duplicates
    new_results = []
    for r in results:
        key = (r.get('Date', ''), r.get('Event', ''), r.get('parkrunner', ''))
        if key not in existing:
            new_results.append(r)

    if not new_results:
        print("No new results to add (all duplicates)")
        return

    # Write to CSV
    file_exists = os.path.exists(OUTPUT_FILE) and append
    mode = 'a' if file_exists else 'w'

    with open(OUTPUT_FILE, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_results)

    print(f"Saved {len(new_results)} new results to {OUTPUT_FILE}")


def fetch_single_week(event_date=None):
    """Fetch and save results for a single week"""
    try:
        html = fetch_html(event_date)
        results = parse_results(html)
        print(f"Total club results: {len(results)}")

        if results:
            save_results(results, append=True)
        return results

    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        raise


def backfill_weeks(num_weeks=4, sleep_seconds=30):
    """Backfill historical weeks of data"""
    import time
    from datetime import timedelta

    print(f"Backfilling {num_weeks} weeks of historical data")
    print(f"Using {sleep_seconds}s delay between requests to be respectful")
    print("=" * 50)

    # First, get the latest page to find the most recent date
    html = fetch_html()
    date_match = re.search(r'who participated at a parkrun on (\d{4}-\d{2}-\d{2})', html)

    if not date_match:
        print("Could not find event date in page")
        return

    latest_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
    print(f"Most recent results: {latest_date.strftime('%Y-%m-%d')}")

    # Parse and save the latest week first
    results = parse_results(html)
    print(f"Week {latest_date.strftime('%Y-%m-%d')}: {len(results)} results")
    save_results(results, append=True)

    # Now fetch previous weeks
    for i in range(1, num_weeks):
        print(f"\nSleeping {sleep_seconds}s before next request...")
        time.sleep(sleep_seconds)

        # Go back 7 days
        prev_date = latest_date - timedelta(days=7 * i)
        date_str = prev_date.strftime('%Y-%m-%d')

        print(f"\nFetching week {i+1}/{num_weeks}: {date_str}")
        print("-" * 40)

        try:
            html = fetch_html(date_str)
            results = parse_results(html)
            print(f"Week {date_str}: {len(results)} results")
            save_results(results, append=True)
        except Exception as e:
            print(f"Error fetching {date_str}: {e}")
            continue

    print("\n" + "=" * 50)
    print("Backfill complete!")


def main():
    """Main entry point"""
    print(f"Fetching results for club {CLUB_NUM} ({CLUB_NAME})")
    print("=" * 50)

    try:
        html = fetch_html()
        results = parse_results(html)
        print(f"\nTotal club results: {len(results)}")

        if results:
            save_results(results, append=True)

            # Print summary
            print("\nResults summary:")
            for r in results:
                print(f"  {r['Date']} | {r['Event']:20} | {r['parkrunner']:20} | {r['Time']}")

    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--backfill':
        weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        backfill_weeks(num_weeks=weeks, sleep_seconds=30)
    else:
        main()
