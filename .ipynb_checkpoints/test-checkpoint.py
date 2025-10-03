import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import json
import os

curTime = datetime.now()
print("RUN OF test.py at time=", curTime)

STATE_FILE = "./scraped_jobs.json"

URL = "https://github.com/SimplifyJobs/New-Grad-Positions/tree/dev"
print(URL)

# If we find that there are more than this number of jobs in the JSON file, then we remove the oldest jobs from the JSON file.
MAX_ALLOWED_JOBS_IN_FILE = 1000

# Check the MAX_ROWS_TO_CHECK top (most recent) rows from the website
MAX_ROWS_TO_CHECK = 10

# All the jobs that the scraper ALREADY has found on past runs of this file ( test.py ).
past_jobs = []
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r") as f:
            past_jobs = json.load(f)
    except Exception as e:
        past_jobs = []

last_past_job = None
if len(past_jobs) > 0:
    # Get the most recent job, out of all the jobs that had already been collected on previous runs of test.py .
    last_past_job = past_jobs[-1]

jobs_to_add = []

if len(past_jobs) > MAX_ALLOWED_JOBS_IN_FILE:
    past_jobs = past_jobs[len(past_jobs)-MAX_ALLOWED_JOBS_IN_FILE:]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(URL)
        print(await page.title())
        
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_selector("markdown-accessiblity-table > table > tbody > tr")
        # await page.wait_for_selector("li.job-list-item__job-info-item")
        print("AFTER waiting for markdown-accessiblity-table > table > tbody > tr to appear / be loaded on the page")

        tableRows = page.locator("markdown-accessiblity-table > table > tbody > tr")
        tableRows_num = await tableRows.count()
        print("NUMBER OF ...posting-date tableRows=", tableRows_num)
        tableRows = await tableRows.all()

        numRowsChecked = 0

        currentTime = datetime.now()
        currentDay = datetime.today()
        print("CURRENT DAY=", currentDay)

        jobs_to_add = []
        
        for currentTableRow in tableRows:
            print("START OF THE " + str(numRowsChecked+1) + "TH ITERATION")
            if numRowsChecked > MAX_ROWS_TO_CHECK:
                print("STOPPED SEARCHING FOR JOBS ON THE WEBSITE, BECAUSE I SCRAPED THE LIMIT OF=", numRowsChecked, "JOBS PER RUN OF ME (test.py)")
                break
            print("\n\ncurrentTableRow=", currentTableRow)
            currentTableRowHTML = await currentTableRow.evaluate("element => element.innerHTML")
            print(currentTableRowHTML)

            # Extract all <td> innerHTML into a Python list
            td_values = await currentTableRow.locator("td").evaluate_all(
                "nodes => nodes.map(n => n.innerText)"
            )

            # Check if the 4th column of this row actually has a hyperlink (has a <a> element)
            anchor = currentTableRow.locator("td").nth(3).locator("a")
            url = None
            simplify_url = None
            
            if await anchor.count() > 0:
                # Get the URL of the 1st column of the row, if it exists.
                url = await anchor.first.get_attribute("href")
                if await anchor.count() > 1:
                    simplify_url = await anchor.nth(1).get_attribute("href")                

            print("td_values")
            print(td_values)  # Example output: ['Alice', 'Bob', 'Charlie']

            td_values[3] = {}
            td_values[3]["url"] = url
            td_values[3]["simplify_url"] = simplify_url

            try:
                index = td_values[4].index("d")
                print(f"The first occurrence of 'd' is at index: {index}")
                td_values[4] = td_values[4][0:index]
                try:
                    td_values[4] = int(td_values[4])
                except ValueError:
                    print(f"Error: '{td_values[4]}' cannot be converted to an integer.")
            except ValueError:
                print(f"'d' not found in the string.")

            print("url=")
            print(url)

            print("simplify_url=")
            print(simplify_url)

            # CHECK IF THE CURRENT JOB WE'RE LOOKING AT FROM THE WEBSITE IS ACTUALLY THE MOST-RECENT JOB THAT WE COLLECTED
            # IF YES, THEN WE CAN STOP LOOKING AT JOBS FROM THE WEBSITE OLDER THAN THIS ONE.
            if (last_past_job is not None):
                if (td_values[0] == last_past_job["company"] and td_values[1] == last_past_job["role"] and td_values[2] == last_past_job["location"]):
                    print("STOPPED SEARCHING FOR JOBS ON THE WEBSITE, BECAUSE I SCRAPED A JOB THAT A PREVIOUS CALL OF ME HAD ALREADY FOUND AND WROTE INTO scraped_jobs.json")
                    break

            day_posted = td_values[4]
            if isinstance(td_values[4], int):
                day_posted = currentDay - timedelta(days=td_values[4])
                day_posted = day_posted.strftime("%m-%d-%Y")

            # Add the just-scraped-from-website job to the json file.
            jobs_to_add.append({"company": td_values[0], "role": td_values[1], "location": td_values[2], "links": td_values[3], "day_posted": day_posted})
            
            numRowsChecked += 1
            # END OF THIS ITER OF THE FOR LOOP; MOVE ON TO THE NEXT ROW.
        

       
        await browser.close()

        jobs_to_add = past_jobs + jobs_to_add
        if len(jobs_to_add) > MAX_ALLOWED_JOBS_IN_FILE:
            jobs_to_add = jobs_to_add[len(jobs_to_add)-MAX_ALLOWED_JOBS_IN_FILE:]
        with open(STATE_FILE, "w") as f:
            json.dump(list(jobs_to_add), f, indent=2)

# await main()
if __name__ == "__main__":
    asyncio.run(main())