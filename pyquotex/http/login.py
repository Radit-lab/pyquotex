import re
import json
import sys
import asyncio
from pathlib import Path
from pyquotex.http.navigator import Browser


class Login(Browser):
    """Class for Quotex login resource."""

    url = ""
    cookies = None
    ssid = None
    # Updated base domain to match what you see in the browser
    base_url = 'market-qx.trade'
    https_base_url = f'https://{base_url}'

    def __init__(self, api, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api = api
        self.html = None
        self.headers = self.get_headers()
        self.full_url = f"{self.https_base_url}/{api.lang}"

    def get_token(self):
        self.headers["Connection"] = "keep-alive"
        self.headers["Accept-Encoding"] = "gzip, deflate, br"
        self.headers["Accept-Language"] = "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3"
        self.headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        )
        self.headers["Referer"] = f"{self.full_url}/sign-in"
        self.headers["Upgrade-Insecure-Requests"] = "1"
        self.headers["Sec-Ch-Ua-Mobile"] = "?0"
        self.headers["Sec-Ch-Ua-Platform"] = '"Linux"'
        self.headers["Sec-Fetch-Site"] = "same-origin"
        self.headers["Sec-Fetch-User"] = "?1"
        self.headers["Sec-Fetch-Dest"] = "document"
        self.headers["Sec-Fetch-Mode"] = "navigate"
        self.headers["Dnt"] = "1"
        self.send_request(
            "GET",
            f"{self.full_url}/sign-in/modal/"
        )
        html = self.get_soup()
        match = html.find(
            "input", {"name": "_token"}
        )
        token = None if not match else match.get("value")
        return token

    async def awaiting_pin(self, data, input_message):
        self.headers["Content-Type"] = "application/x-www-form-urlencoded"
        self.headers["Referer"] = f"{self.full_url}/sign-in/modal"
        data["keep_code"] = 1
        try:
            code = input(input_message)
            if not code.isdigit():
                print("Please enter a valid code.")
                await self.awaiting_pin(data, input_message)
            data["code"] = code
        except KeyboardInterrupt:
            print("\nClosing program.")
            sys.exit()

        await asyncio.sleep(1)
        self.send_request(
            method="POST",
            url=f"{self.full_url}/sign-in/modal",
            data=data
        )

    def get_profile(self):
        self.response = self.send_request(
            method="GET",
            url=f"{self.full_url}/trade"
        )
        if self.response:
            soup = self.get_soup()
            settings = {}

            # 1) Search all <script> tags for a block starting with window.settings =
            script_tags = soup.find_all("script")
            for tag in script_tags:
                try:
                    text = tag.get_text() or ""
                    if "window.settings" in text:
                        # Extract after the assignment
                        cleaned = re.sub(
                            r"^\s*window\.settings\s*=\s*",
                            "",
                            text.strip().replace(";", ""),
                            flags=re.MULTILINE
                        )
                        try:
                            candidate = json.loads(cleaned)
                            if isinstance(candidate, dict) and candidate:
                                settings = candidate
                                break
                        except json.JSONDecodeError:
                            # Try to find a JSON object inside the script via regex
                            pass
                except Exception:
                    pass

            # 2) If not found, regex-scan the entire HTML for a JSON containing "token"
            if not settings:
                try:
                    html_text = str(soup)
                    # crude regex to capture a JSON object containing "token"
                    match = re.search(r"\{[^\}]*\"token\"\s*:\s*\"([^\"]+)\"[^\}]*\}", html_text)
                    if match:
                        # Best effort: parse the full object if possible
                        obj_start = html_text.rfind("{", 0, match.start())
                        obj_end = html_text.find("}", match.end()-1)
                        snippet = html_text[obj_start:obj_end+1] if (obj_start != -1 and obj_end != -1) else match.group(0)
                        try:
                            candidate = json.loads(snippet)
                            if isinstance(candidate, dict):
                                settings = candidate
                            else:
                                # fallback minimal settings with token
                                settings = {"token": match.group(1)}
                        except Exception:
                            settings = {"token": match.group(1)}
                except Exception:
                    pass

            # Collect cookies
            self.cookies = self.get_cookies()

            # 3) Fallback: try to obtain token from cookies if still missing
            token = settings.get("token") if isinstance(settings, dict) else None
            if not token and self.cookies:
                try:
                    # parse cookie string into dict-like pairs
                    cookie_pairs = [c.strip() for c in self.cookies.split(';') if '=' in c]
                    cookie_map = {}
                    for pair in cookie_pairs:
                        k, v = pair.split('=', 1)
                        cookie_map[k.strip().lower()] = v.strip()
                    for key in [
                        'ssid', 'session', 'token', 'authorization', 'auth', 'jwt', 'access_token']:
                        if key in cookie_map and cookie_map[key]:
                            token = cookie_map[key]
                            break
                except Exception:
                    pass

            self.ssid = token

            # Update session_data and persist
            self.api.session_data["cookies"] = self.cookies
            self.api.session_data["token"] = self.ssid
            self.api.session_data["user_agent"] = self.headers["User-Agent"]

            output_file = Path(f"{self.api.resource_path}/session.json")
            output_file.parent.mkdir(exist_ok=True, parents=True)
            output_file.write_text(
                json.dumps({
                    "cookies": self.cookies,
                    "token": self.ssid,
                    "user_agent": self.headers["User-Agent"]
                }, indent=4)
            )
            return self.response, (settings if isinstance(settings, dict) else {})

        return None, None

    def _get(self):
        return self.send_request(
            method="GET",
            url=f"f{self.full_url}/trade"
        )

    async def _post(self, data):
        """Send get request for Quotex API login http resource.
        :returns: The instance of :class:`requests.Response`.
        """
        self.response = self.send_request(
            method="POST",
            url=f"{self.full_url}/sign-in/",
            data=data
        )
        required_keep_code = self.get_soup().find(
            "input", {"name": "keep_code"}
        )
        if required_keep_code:
            auth_body = self.get_soup().find(
                "main", {"class": "auth__body"}
            )
            input_message = (
                f'{auth_body.find("p").text}: ' if auth_body.find("p")
                else "Insira o código PIN que acabamos "
                     "de enviar para o seu e-mail: "
            )
            await self.awaiting_pin(data, input_message)
        await asyncio.sleep(1)
        success = self.success_login()
        return success

    def success_login(self):
        if "trade" in self.response.url:
            return True, "Login successful."
        html = self.get_soup()
        match = html.find(
            "div", {"class": "hint--danger"}
        ) or html.find(
            "div", {"class": "input-control-cabinet__hint"}
        )
        message_in_match = match.text.strip() if match else ""
        return False, f"Login failed. {message_in_match}"

    async def __call__(self, username, password, user_data_dir=None):
        """Method to get Quotex API login http request.
        :param str username: The username of a Quotex server.
        :param str password: The password of a Quotex server.
        :param str user_data_dir: The optional value for path userdata.
        :returns: The instance of :class:`requests.Response`.
        """
        data = {
            "_token": self.get_token(),
            "email": username,
            "password": password,
            "remember": 1,

        }
        status, msg = await self._post(data)
        if not status:
            print(msg)
            exit(0)

        self.get_profile()

        return status, msg
