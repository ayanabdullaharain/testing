
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib.parse import urlparse
import time

URL = "https://hospital-management-system-eight-ashen.vercel.app/login"
BASE_HOST = urlparse(URL).netloc

results = []


def report(test_id, name, status, evidence=""):
    results.append((test_id, name, status, evidence))
    print(f"[{status}] {test_id}: {name}")
    if evidence:
        print("    Evidence:", evidence[:500])


def open_login(driver):
    driver.get(URL)
    wait = WebDriverWait(driver, 12)
    email = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[type='email']")
        )
    )
    password = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[type='password']")
        )
    )
    return email, password, wait


def get_submit_button(driver):
    for button in driver.find_elements(By.TAG_NAME, "button"):
        if not button.is_displayed() or not button.is_enabled():
            continue

        text = button.text.strip().lower()
        if any(word in text for word in ("login", "sign in", "submit")):
            return button

    # Fallback for icon-only or unlabeled submit buttons
    buttons = driver.find_elements(
        By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"
    )
    for button in buttons:
        if button.is_displayed() and button.is_enabled():
            return button

    raise RuntimeError("Could not locate an enabled submit button")


def visible_feedback(driver):
    selectors = [
        '[role="alert"]',
        '[role="status"]',
        '[aria-live="polite"]',
        '[aria-live="assertive"]',
        ".error",
        ".error-message",
        ".text-red-500",
        ".text-red-600",
    ]

    messages = []
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if element.is_displayed():
                text = element.text.strip()
                if text and text not in messages:
                    messages.append(text)

    return messages


def body_text(driver):
    try:
        return driver.find_element(By.TAG_NAME, "body").text[:3000]
    except Exception:
        return ""


def current_path(driver):
    return urlparse(driver.current_url).path.rstrip("/") or "/"


def attempt_login(driver, email_value, password_value):
    email, password, wait = open_login(driver)

    email.clear()
    email.send_keys(email_value)

    password.clear()
    password.send_keys(password_value)

    button = get_submit_button(driver)
    button.click()

    # Wait for navigation or visible feedback; otherwise inspect after timeout.
    try:
        wait.until(
            lambda d: current_path(d) != "/login"
            or bool(visible_feedback(d))
        )
    except TimeoutException:
        pass

    time.sleep(0.5)

    return {
        "url": driver.current_url,
        "path": current_path(driver),
        "messages": visible_feedback(driver),
        "body": body_text(driver),
    }


driver = webdriver.Chrome()
driver.set_window_size(1365, 900)

try:
    print("\n=== HOSPITAL MANAGEMENT SYSTEM: NEGATIVE TESTS ===")

    # AUTH-01: SQL injection-style input
    for payload in ["' OR '1'='1' --", "admin'--"]:
        try:
            result = attempt_login(driver, payload, "InvalidPass123!")

            if result["path"] != "/login":
                report(
                    "AUTH-01",
                    "Injection-style input rejected",
                    "INVESTIGATE",
                    f"Input={payload!r}; destination={result['url']}"
                )
            else:
                report(
                    "AUTH-01",
                    "Injection-style input did not navigate away",
                    "OBSERVED",
                    f"Input={payload!r}; feedback={result['messages']}"
                )

        except Exception as error:
            report("AUTH-01", "Injection input handling", "ERROR", str(error))

    # AUTH-02: Extremely long values (bounded to 512 characters)
    try:
        long_email = "a" * 500 + "@example.com"
        long_password = "P" * 512
        result = attempt_login(driver, long_email, long_password)

        report(
            "AUTH-02",
            "Long input handling",
            "OBSERVED",
            f"Destination={result['url']}; "
            f"feedback={result['messages']}; "
            f"page responsive={bool(result['body'])}"
        )
    except Exception as error:
        report("AUTH-02", "Long input handling", "ERROR", str(error))

    # AUTH-03: Whitespace-only values
    try:
        result = attempt_login(driver, "   ", "          ")

        report(
            "AUTH-03",
            "Whitespace-only input handling",
            "OBSERVED",
            f"Destination={result['url']}; feedback={result['messages']}"
        )
    except Exception as error:
        report("AUTH-03", "Whitespace input handling", "ERROR", str(error))

    # AUTH-04: Malformed email formats
    malformed_emails = [
        "plain-text",
        "user@",
        "@example.com",
        "user..name@example.com",
    ]

    for malformed in malformed_emails:
        try:
            result = attempt_login(driver, malformed, "DummyPass123!")

            report(
                "AUTH-04",
                f"Malformed email: {malformed!r}",
                "OBSERVED",
                f"Destination={result['url']}; "
                f"feedback={result['messages']}"
            )
        except Exception as error:
            report(
                "AUTH-04",
                f"Malformed email: {malformed!r}",
                "ERROR",
                str(error)
            )

    # AUTH-05: Repeated invalid attempts (5 only; not a load test)
    try:
        observations = []

        for index in range(5):
            result = attempt_login(
                driver,
                "invalid-test@example.com",
                "WrongPassword123!"
            )
            observations.append({
                "attempt": index + 1,
                "path": result["path"],
                "feedback": result["messages"],
            })

        report(
            "AUTH-05",
            "Five invalid login attempts",
            "OBSERVED",
            str(observations)
        )
    except Exception as error:
        report("AUTH-05", "Repeated invalid attempts", "ERROR", str(error))

    # AUTH-06: Refresh after invalid login
    try:
        attempt_login(
            driver,
            "invalid-test@example.com",
            "WrongPassword123!"
        )

        driver.refresh()

        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "input[type='password']")
            )
        )

        report(
            "AUTH-06",
            "Login form survives refresh after rejection",
            "OBSERVED",
            f"Destination={driver.current_url}"
        )
    except Exception as error:
        report("AUTH-06", "Refresh after rejection", "ERROR", str(error))

    # AUTH-07: Browser back after invalid login
    try:
        attempt_login(
            driver,
            "invalid-test@example.com",
            "WrongPassword123!"
        )

        driver.back()
        time.sleep(1)

        report(
            "AUTH-07",
            "Back navigation after invalid login",
            "OBSERVED",
            f"Destination={driver.current_url}; "
            f"same host={urlparse(driver.current_url).netloc == BASE_HOST}"
        )
    except Exception as error:
        report("AUTH-07", "Back navigation", "ERROR", str(error))

    # AUTH-08: Check available role controls without changing privileges
    try:
        open_login(driver)

        role_controls = driver.find_elements(
            By.CSS_SELECTOR, "select, input[type='radio']"
        )

        role_buttons = [
            e for e in driver.find_elements(By.TAG_NAME, "button")
            if e.is_displayed()
            and any(
                role in e.text.lower()
                for role in ("admin", "doctor", "super admin")
            )
        ]

        details = {
            "select_or_radio_controls": len(role_controls),
            "visible_role_buttons": [
                b.text.strip() for b in role_buttons
            ],
        }

        report(
            "AUTH-08",
            "Role selector inventory",
            "OBSERVED",
            str(details)
        )
    except Exception as error:
        report("AUTH-08", "Role selector inventory", "ERROR", str(error))

    # AUTH-09: Check password field is not rendered as plain text
    try:
        open_login(driver)

        password = driver.find_element(
            By.CSS_SELECTOR, "input[type='password']"
        )

        report(
            "AUTH-09",
            "Password masking",
            "PASS" if password.get_attribute("type") == "password"
            else "FAIL",
            f"Input type={password.get_attribute('type')}"
        )
    except Exception as error:
        report("AUTH-09", "Password masking", "ERROR", str(error))

    # AUTH-10: Look for exposed stack traces or server error details
    try:
        result = attempt_login(
            driver,
            "invalid-test@example.com",
            "WrongPassword123!"
        )

        text = (result["body"] + " " + " ".join(result["messages"])).lower()

        indicators = [
            "traceback (most recent call last)",
            "sql syntax",
            "stack trace",
            "internal server error",
            "exception at",
        ]

        found = [item for item in indicators if item in text]

        if found:
            report(
                "AUTH-10",
                "Error response disclosure",
                "INVESTIGATE",
                f"Possible indicators={found}"
            )
        else:
            report(
                "AUTH-10",
                "No common stack-trace indicators detected",
                "OBSERVED",
                "This does not prove that server errors are handled securely."
            )
    except Exception as error:
        report("AUTH-10", "Error response inspection", "ERROR", str(error))

finally:
    driver.quit()

    print("\n=== SUMMARY ===")
    for test_id, name, status, evidence in results:
        print(f"{test_id} | {status} | {name}")

    print("\nTotal checks:", len(results))
    print("PASS:", sum(r[2] == "PASS" for r in results))
    print("FAIL:", sum(r[2] == "FAIL" for r in results))
    print("INVESTIGATE:", sum(r[2] == "INVESTIGATE" for r in results))
    print("OBSERVED:", sum(r[2] == "OBSERVED" for r in results))
    print("ERROR:", sum(r[2] == "ERROR" for r in results))
