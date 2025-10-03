import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import json
import os

# GET ALL THE ENVIRONMENTAL VARS.
URL = os.environ.get("BASE_URL")

senderEmail = os.environ.get("EMAIL")
gatewayAddress = senderEmail
appKey = os.environ.get("WORD")

curTime = datetime.now()
print("RUN OF test.py at time=", curTime)

STATE_FILE = "./scraped_jobs.json"

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

initial_num_past_jobs = len(past_jobs)

last_past_job = None
if len(past_jobs) > 0:
    # Get the most recently-posted job, out of all the jobs that had already been collected on previous runs of test.py .
    last_past_job = past_jobs[0]

jobs_to_add = []

if len(past_jobs) > MAX_ALLOWED_JOBS_IN_FILE:
    past_jobs = past_jobs[0:MAX_ALLOWED_JOBS_IN_FILE]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(URL)
        
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_selector("markdown-accessiblity-table > table > tbody > tr")
        
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
        if len(jobs_to_add) == 0:
            # Do NOT need to over-write the .json file
            # If the .json file initially had more jobs than allowed, then I need to write to the .json file
            if initial_num_past_jobs > MAX_ALLOWED_JOBS_IN_FILE:
                # Note that we already truncated "past_jobs"
                with open(STATE_FILE, "w") as f:
                    json.dump(past_jobs, f, indent=2)
            pass
        else:
            jobs_to_add = jobs_to_add + past_jobs
            if len(jobs_to_add) > MAX_ALLOWED_JOBS_IN_FILE:
                jobs_to_add = jobs_to_add[0:MAX_ALLOWED_JOBS_IN_FILE]
            with open(STATE_FILE, "w") as f:
                json.dump(jobs_to_add, f, indent=2)

        num_jobs_to_add = len(jobs_to_add)
        msg_content = "Below is the NUM=[ " + str(num_jobs_to_add) + " ] jobs on the Github Job Board, in order from MOST RECENTLY POSTED (TOP OF THE EMAIL) on the Github Job Board TO LEAST RECENTLY POSTED (BOTTOM OF THE EMAIL).\nDAY POSTED refers to day posted on the Github Board in Dallas time, estimated by me.\n"
        for i in range(num_jobs_to_add):
            if i != 0:
                msg_content += "\n\n=========\n\n"

            cur_job_day_posted = None
            if isinstance(jobs_to_add[i]["day_posted"], str) and len(jobs_to_add[i]["day_posted"])>0:
                cur_job_day_posted = datetime.strptime(jobs_to_add[i]["day_posted"], "%m-%d-%Y").strftime("%b %d, %Y")
            msg_content += (str(i+1) + ":\nCOMPANY: " + jobs_to_add[i]["company"] + "\nROLE TITLE:" + jobs_to_add[i]["role"] + "\nLOCATION:" + jobs_to_add[i]["location"] + "\nAPPLY:" + ("\n\tURL:"+jobs_to_add[i]["links"]["url"] if jobs_to_add[i]["links"]["url"] else "") + (("\n\tSIMPLIFY:"+jobs_to_add[i]["links"]["simplify"]) if jobs_to_add[i]["links"]["simplify"] else "") + "\nDAY POSTED:" + (cur_job_day_posted if cur_job_day_posted else "Date not found"))
        
        # NEXT SECTION: Just send a email, do NOT try to send a message. Called one time per run of test.py.
        msg = EmailMessage()

        emailTime = datetime.now()
        
        msg['From'] = senderEmail
        msg['To'] = gatewayAddress
        msg['Subject'] = 'Job Update | ' + emailTime.strftime("%b %-d, %Y : At %-I:%M %p")
        
        msg.set_content(msg_content)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(senderEmail, appKey)
            smtp.send_message(msg)
        
        print("Email sent successfully!")

# await main()
if __name__ == "__main__":
    asyncio.run(main())