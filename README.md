# MSFedPingSpray
MSFedPingSpray is a tool designed for security professionals and penetration testers. It leverages Selenium to perform automated password spraying attacks against PingFederate authentication systems federated through Microsoft Azure AD. This tool assists in identifying weak credentials within enterprise environments that use Microsoft as a federation provider to PingFederate for identity management and access control.

# Key Features
* Microsoft Federated Login Support: Navigates through login.microsoftonline.com and follows the redirect to the PingFederate portal automatically.
* Password Spraying Capabilities: Executes password spraying attacks, testing a list of common passwords against identified valid users, aiding in uncovering weak credentials.
* Headless Browser Support: Runs in headless mode for seamless operation in background and automated environments.
* Incognito Mode Option: Ensures cleaner sessions with less traceability, enhancing the tool's discreetness during testing.
* Customizable Workflow: Supports various command-line arguments for a personalized and flexible usage experience.
  
# Usage Scenarios
MSFedPingSpray is particularly useful in penetration testing and security auditing scenarios where organizations utilize PingFederate federated through Microsoft Azure AD. It helps in:
* Educational Purposes
* Assessing the strength of user credentials in the target system.
* Identifying potential security gaps related to user authentication.
* Complementing broader security assessments with focused testing on authentication mechanisms.

# Usage
MSFedPingSpray.py [-h] --output OUTPUT --password PASSWORD --users USERS [--incognito] [--headless]

options:
*  -h, --help           show this help message and exit
*  --output OUTPUT      Path to the output file for valid sprayed users
*  --password PASSWORD  Password to use for spraying
*  --users USERS        Path to the input user file
*  --incognito          Enable incognito mode for the browser
*  --headless           Enable headless mode for the browser

## Example
```bash
python MSFedPingSpray.py \
  --users users.txt \
  --password "Spring2026!" \
  --output pwned.txt \
  --headless
```

## Flow
1. Navigates to the Microsoft login page (`login.microsoftonline.com`)
2. Enters the username and clicks "Next"
3. Azure AD redirects to the federated PingFederate portal
4. Enters the username and password on the PingFederate login form
5. Submits and checks whether the login succeeded

# Chrome Selenium Driver
If needed, download the Chrome Selenium driver from:
https://googlechromelabs.github.io/chrome-for-testing/

Ensure the chromedriver version matches your installed Chrome version.
