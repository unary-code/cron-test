import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import pytz
import smtplib
from email.message import EmailMessage
import json
import os, re
from dotenv import load_dotenv
from datetime import datetime, timedelta

# GET ALL THE ENVIRONMENTAL VARS.
#URL = os.environ.get("BASE_URL")
#print(f"{URL=}")
# URL = "dice.com"
# URL = "https://www.dice.com/jobs?filters.workplaceTypes=Remote&q=Senior+IT+Project+Manager"
LABELS_AND_URLS = [("Dice", "https://www.dice.com/jobs?filters.postedDate=ONE&filters.workplaceTypes=Remote&q=Senior+IT+Project+Manager")]

print(f"{LABELS_AND_URLS=}")

load_dotenv()
# senderEmail = os.environ.get("EMAIL")
senderEmail = os.getenv("EMAIL")
gatewayAddress = senderEmail
appKey = os.getenv("WORD")
dallas_tz = pytz.timezone("America/Chicago")

curTime = datetime.now(dallas_tz)
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
    print("RUN main")
    for (label, url) in LABELS_AND_URLS:
        print(f"PROCESSING website: {label} which is at {url=}")
        await process_website(label, url)

async def process_website(label, url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        
        await page.goto(url, wait_until="networkidle")
        #await page.wait_for_selector("markdown-accessiblity-table > table > tbody > tr")
        await page.wait_for_selector('div[aria-label="Job search results"] > div[role="listitem"]')
        
        # div[Job search results"] > div[listitem] > X > div.self-stretch > a[data-testid="job-search-job-detail-link"] .innerHTML (is the Job Title) & .href
        #
        # Let jobCardDivs = (div[Job search results"] > div[listitem] .child[0].child[0].child[0]
        #   or equivalently div[Job search results"] > div[data-testid="job-card" role="article"])
        # jobCardDivs > div > div(1st div child) > div(1st div child) > span (1st span child of the <div>) > a (2nd <a> child of <span>  or equivalently, 1st <a> child of <span> that does not have a aria-label="Company Logo") > p .innerHTML (is the Company Name)
        # div.self-stretch > a[data-testid="job-search-job-detail-link"] 
        print("AFTER waiting for markdown-accessiblity-table > table > tbody > tr to appear / be loaded on the page")

        tableRows = page.locator('div[aria-label="Job search results"] > div[role="listitem"]')
        tableRows_num = await tableRows.count()
        print("NUMBER OF ...posting-date tableRows=", tableRows_num)
        tableRows = await tableRows.all()

        numRowsChecked = 0

        currentTime = datetime.now(dallas_tz)
        currentDay = datetime.today()
        # print("CURRENT DAY=", currentDay)

        jobs_to_add = []

        with open("job_duplicates.log", "w", encoding="utf-8") as f:
            f.write("NEW LOG\n")
        
        for currentTableRow in tableRows:
            print("START OF THE " + str(numRowsChecked+1) + "TH ITERATION")
            if numRowsChecked > MAX_ROWS_TO_CHECK:
                print("STOPPED SEARCHING FOR JOBS ON THE WEBSITE, BECAUSE I SCRAPED THE LIMIT OF=", numRowsChecked, "JOBS PER RUN OF ME (test.py)")
                break
            print("\n\ncurrentTableRow=", currentTableRow)
            # NEW CODE ON MAY 2, 2026:
            # currentTableRow.locator("")
            company_name_selector = ('div > div > div > div > div > span > a:not([aria-label="Company Logo"]) > p')
            # .text_content() is preferred over .inner_html()
            company_name = await currentTableRow.locator(company_name_selector).text_content()
            print(f"\n\n\nATTENTION")

            main_info_selector = ('div > div > div > div > div[role="main"] > div > div > a')
            main_info_element = currentTableRow.locator(main_info_selector)
            job_title = await main_info_element.text_content()
            job_link = await main_info_element.get_attribute("href")

            job_type_and_date_ele = currentTableRow.locator('div > div > div > div > div[role="main"] > span:first-of-type > div')
            children = job_type_and_date_ele.locator("div:nth-of-type(1) > div > *")
            count = await children.count()
            for i in range(count):
                child = children.nth(i)
                print(await child.evaluate("el => el.outerHTML"))
            #return
            job_type = await job_type_and_date_ele.locator('div:nth-of-type(1) > div > p').text_content()
            job_date = await job_type_and_date_ele.locator('div:nth-of-type(2) > div:nth-of-type(2) > p').text_content()
            date_posted = None
                    
            if job_date.lower() == "today":
                date_posted = (datetime.today()).strftime("%B %d, %Y")
            elif job_date.lower() == "yesterday":
                date_posted = (datetime.today() - timedelta(days=1)).strftime("%B %d, %Y")
            elif bool(re.fullmatch(r".+\*d ago.*", job_date)):
                # "2d ago" or "30+d" ago
                num_days_ago = None
                more_than = False
                for date_part_ind, date_part in enumerate(job_date.split(" ")):
                    if date_part[-2:] == "+d":
                        num_days_ago = int(date_part[:-2])
                        more_than = True
                    if date_part[-1] == "d":
                        num_days_ago = int(date_part[:-1])
                date_posted = (datetime.today() - timedelta(days=num_days_ago)).strftime("%B %d, %Y")
                if more_than:
                    date_posted = "<= " + date_posted
            else:
                # Do not know the exact type so
                date_posted = "{'day_scraped':"+(datetime.today()).strftime("%B %d, %Y") + ",'text_shown_on_that_day':"+job_date+"}"
            print(f"{company_name=} {job_title=} {job_type=} {job_date=} {job_link=}")
            job_to_add = {"company": company_name, "role": job_title, "location": job_type, "link": job_link, "day_posted": date_posted}
            already_exists = any(past_job.get("company") == job_to_add.get("company") and past_job.get("role") == job_to_add.get("role") and past_job.get("location") == job_to_add.get("location") for past_job in past_jobs)
            if already_exists:
                with open("job_duplicates.log", "a", encoding="utf-8") as f:
                    f.write(f"ON {datetime.today().strftime('%B %d, %Y')} , FOUND A DUPLICATE JOB {job_to_add=} THAT ALREADY EXISTED IN scraped_jobs.json\n")
                print("JOB ALREADY EXISTS IN scraped_jobs.json FILE")
                continue

            # Add the just-scraped-from-website job to the json file.
            jobs_to_add.append({"company": company_name, "role": job_title, "location": job_type, "link": job_link, "day_posted": date_posted})

            numRowsChecked += 1
            continue
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

        # SECTION: Send 1 email per run of test.py.
        
        num_jobs_to_add = len(jobs_to_add)
        print(f"{num_jobs_to_add=}")
        if num_jobs_to_add > 0:
            # ONLY send out a email if we actually found new jobs.
            msg_content = "Below is the NUM=[ " + str(num_jobs_to_add) + " ] jobs on the Github Job Board, in order from MOST RECENTLY POSTED (TOP OF THE EMAIL) on the Github Job Board TO LEAST RECENTLY POSTED (BOTTOM OF THE EMAIL).\nDAY POSTED refers to day posted on the Github Board in Dallas time, estimated by me.\n"
            print(f"{msg_content=}")
            for i in range(num_jobs_to_add):
                if i != 0:
                    msg_content += "\n\n=========\n\n"
    
                #cur_job_day_posted = None
                # if isinstance(jobs_to_add[i]["day_posted"], str) and len(jobs_to_add[i]["day_posted"])>0:
                #     cur_job_day_posted = datetime.strptime(jobs_to_add[i]["day_posted"], "%m-%d-%Y").strftime("%b %d, %Y")
                msg_content += (str(i+1) + ":\nCOMPANY: " + jobs_to_add[i]["company"] + "\nROLE TITLE:" + jobs_to_add[i]["role"] + "\nLOCATION:" + jobs_to_add[i]["location"] + "\nAPPLY:" + ("\n\tURL:"+jobs_to_add[i]["link"] if jobs_to_add[i]["link"] else "No URL found.") + "\nDAY POSTED:" + (jobs_to_add[i]["day_posted"] if jobs_to_add[i]["day_posted"] else "Date not found"))
            
            msg = EmailMessage()
    
            emailTime = datetime.now(dallas_tz)

            msg['From'] = senderEmail
            msg['To'] = gatewayAddress
            msg['Subject'] = 'Job Update | ' + emailTime.strftime("%b %-d, %Y : At %-I:%M %p")
            
            msg.set_content(msg_content)
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(senderEmail, appKey)
                smtp.send_message(msg)
            
            print("Email sent successfully!")

        # SECTION: OVERWRITE THE .json FILE IF WE FOUND NEW JOBS ON THIS RUN OF TEST.PY
        if len(jobs_to_add) == 0:
            # Do NOT need to over-write the .json file
            # If the .json file initially had more jobs than allowed, then I need to write to the .json file
            # if initial_num_past_jobs > MAX_ALLOWED_JOBS_IN_FILE:
            #     # Note that we already truncated "past_jobs"
            #     with open(STATE_FILE, "w") as f:
            #         json.dump(past_jobs, f, indent=2)
            pass
        else:
            jobs_to_add = jobs_to_add + past_jobs
            if len(jobs_to_add) > MAX_ALLOWED_JOBS_IN_FILE:
                jobs_to_add = jobs_to_add[0:MAX_ALLOWED_JOBS_IN_FILE]
            with open(STATE_FILE, "w") as f:
                json.dump(jobs_to_add, f, indent=2)


# await main()
if __name__ == "__main__":
    asyncio.run(main())