from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome()
driver.get("https://checkout.stripe.com/c/pay/cs_live_a14H0EzIFyRfZWgTHuAI3CIyiJwjFaG93J8jyyeCfvMQMMvZaXG2EO8Ued#fidkdWxOYHwnPyd1blppbHNgWjA0SFExVn1Jb3cwVVJUVnx2cDZGT2g2VFN%2Fcl8zSGlER3VLaHN1NEdcQF12NDBMR2hvaDBHRlRMQzEwU39SQnxkR0x9Xz1dV108dWNpdUZsdkh0QXFpRzZXNTUzdVZxc1djRycpJ2N3amhWYHdzYHcnP3F3cGApJ2lkfGpwcVF8dWAnPyd2bGtiaWBabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic%2FcXdwYHgl")  # Replace with the actual checkout URL

# Fill in card details (if fields are accessible)
driver.find_element(By.NAME, "cardnumber").send_keys("5154620044527255")
driver.find_element(By.NAME, "exp-date").send_keys("0939")
driver.find_element(By.NAME, "cvc").send_keys("574")
driver.find_element(By.NAME, "email").send_keys("shjaat@gmail.com")

# Submit the form (if no CAPTCHA/3D Secure)
driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
