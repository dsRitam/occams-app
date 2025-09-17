from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import json
import os
from collections import deque
import urllib.parse # to manipulate urls


# options
chrome_options = Options()
chrome_options.add_argument("--disable-http2")
chrome_options.add_argument("--incognito")
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_argument("--enable-features=NetworkServiceInProcess")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36")
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--headless')


# wait
def wait_for_page_to_load(driver, wait):
    title = driver.title
    try:
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print(f"The Webpage {title} got fully loaded.")
    except:
        print(f"The Webpage {title} did not get loaded.")


# scrapping logic
def scraper(base_url="https://www.occamsadvisory.com/"):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 10)
    driver.maximize_window()
    
    data  = [] # to store: {'url':str, 'content':str}
    visited = set() # to track already visited urls
    queue = deque([base_url]) # starting with homepage
    
    print("Starting scraping .....")
    while queue:
        current_url = queue.popleft() # getting next url (bfs)
        if current_url in visited:
            continue
        try:
            print(f"DEBUG: scraping url -> {current_url}")
            driver.get(current_url)
            wait_for_page_to_load(driver, wait)
            time.sleep(2) # extra delay for js rendering
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            content = soup.get_text(separator="\n", strip=True)
            
            # adding url to data
            data.append({"url": current_url, "content": content})
            visited.add(current_url)
            
            # PREVIEW
            # print(f"content length: {len(content)} chars\n")
            # print(f"content snippet: {content[:200]}\n")
            # print("-"*50 + "\n")
            
            # Find internal links 
            links = soup.find_all('a', href=True)
            for a in links:
                href = a['href']
                if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                    continue # skipping achors, emails, phone numbers
                full_url = urllib.parse.urljoin(base_url, href)
                if "/blog/" in full_url:
                    print(f"DEBUG: skipping blog page -> {full_url}")
                    continue
                if "/podcasts" in full_url:
                    print(f"DEBUG: skipping podcast -> {full_url}")
                    continue
                if full_url.startswith(base_url) and full_url not in visited and full_url not in queue:
                    queue.append(full_url)
                    print(f"DEBUG: adding to the queue -> {full_url}")
                # break
                    
        except Exception as e:
            print(f"Can't scrape -> {current_url}: {e}\n")
            
    driver.quit()
    print(f"Scarping completed......")
    print(f"No of pages scraped: {len(data)}")
    return data

# scraped_data = scraper() # Appx 15 mins

# with open('occams_scraped_data.json', 'w') as f:
#     json.dump(scraped_data, f, indent=4)
# print("saved as json ....")