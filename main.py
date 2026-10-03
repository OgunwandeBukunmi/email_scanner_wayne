
from playwright.async_api import async_playwright
from urllib.parse import urlparse
import asyncio
import re
import csv


# =========================
# CONFIG
# =========================

INPUT_FILE = "pet grooming in Phoenix_leads.csv"
OUTPUT_FILE = "pet grooming in Phoenix_leads_with_email.csv"

MAX_PAGES = 10

EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

EXCLUDED_DOMAINS = {
    "sentry.io",
    "sentry.wixpress.com",
    "sentry-next.wixpress.com",
    "wixapps.com",
    "2x.png",
    "2x.jpg",
    "052021",
    "052021.jpg",
    "@2x.jpg",
    "@2x.png",
    "email.com",
    "domain.com",
    "example.com"

}

# =========================
# URL HELPERS
# =========================

def normalize_domain(domain):
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def is_internal_url(url, base_domain):
    hostname = urlparse(url).hostname

    if not hostname:
        return False

    return normalize_domain(hostname) == normalize_domain(base_domain)


# =========================
# EMAIL EXTRACTION
# =========================

def extract_emails(html, mailto_links):
    emails = set()

    # Find email-looking strings in the HTML
    found_emails = re.findall(EMAIL_REGEX, html)

    for email in found_emails:
        email = email.lower().strip()

        email_domain = email.split("@")[1]

        if email_domain not in EXCLUDED_DOMAINS:
            emails.add(email)

    # Find emails from mailto links
    for link in mailto_links:
        email = (
            link
            .replace("mailto:", "")
            .split("?")[0]
            .strip()
            .lower()
        )

        if "@" not in email:
            continue

        email_domain = email.split("@")[1]

        if email_domain not in EXCLUDED_DOMAINS:
            emails.add(email)

    return emails


# =========================
# WEBSITE CRAWLER
# =========================

async def scrape_website(page, start_url):

    base_domain = urlparse(start_url).hostname

    to_visit = [start_url]
    visited = set()
    emails = set()

    while to_visit and len(visited) < MAX_PAGES:


        current_url = to_visit.pop(0)

        if current_url in visited:
            continue

        print(f"    Visiting: {current_url}")

        visited.add(current_url)

        try:
            await page.goto(
                current_url,
                wait_until="domcontentloaded",
            )

            await page.wait_for_timeout(3000)

            html = await page.content()

            # Find mailto links
            mailto_links = await page.locator(
                'a[href^="mailto:"]'
            ).evaluate_all(
                """elements =>
                    elements.map(element => element.href)
                """
            )

            page_emails = extract_emails(
                html,
                mailto_links
            )

            emails.update(page_emails)

            if page_emails:
                print(f"        Emails: {page_emails}")

            # Find links for further crawling
            links = await page.locator("a").evaluate_all(
                """elements =>
                    elements.map(element => element.href)
                """
            )

            for link in links:

                if is_internal_url(link, base_domain):

                    if link not in visited:
                        to_visit.append(link)

        except Exception as error:

            print(f"        Failed: {current_url}")
            print(f"        {error}")
    page.wait_for_timeout(5000)
    return emails


# =========================
# MAIN
# =========================

async def main():

    # -------------------------
    # Read CSV
    # -------------------------

    with open(
        INPUT_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        rows = list(reader)
        output_rows = []
        fieldnames = reader.fieldnames


    # Make sure email column exists

    if "email" not in fieldnames:
        fieldnames.append("email")


    print(f"Loaded {len(rows)} leads.")


    # -------------------------
    # Start Playwright
    # -------------------------

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False
        )

        



        # -------------------------
        # Process each lead
        # -------------------------

        for index, row in enumerate(rows, start=1):
            page = await browser.new_page()

            business_name = row.get(
                "Name",
                "Unknown business"
            )

            website = row.get(
                "Website",
                ""
            ).strip()


            print("\n==============================")
            print(f"Lead {index}/{len(rows)}")
            print(f"Business: {business_name}")
            print(f"Website: {website}")
            print("==============================")


            # No website

            if not website:

                print("    No website. Skipping.")

                row["email"] = ""
                await page.close()

                continue


            # Scrape website

            emails = await scrape_website(page, website)

            await page.close()

            if emails:

                for email in sorted(emails):

                    new_row = row.copy()

                    new_row["email"] = email

                    output_rows.append(new_row)

            else:

                new_row = row.copy()

                new_row["email"] = ""

                output_rows.append(new_row)

        await browser.close()


    # -------------------------
    # Save new CSV
    # -------------------------

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(output_rows)


    print("\n==============================")
    print("DONE")
    print("==============================")
    print(f"Saved to: {OUTPUT_FILE}")


asyncio.run(main())

