import json
import re
import urllib.parse
import urllib.request
import urllib.error

from getpass import getpass


API_URL = "https://fastshare.cz/api/api_kodi.php"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FastShareClient:

    def __init__(self):
        self.token = None
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, **params):
        query = urllib.parse.urlencode(params)

        request = urllib.request.Request(
            f"{API_URL}?{query}",
            headers={"Accept": "application/json"},
        )

        with self.opener.open(request, timeout=30) as response:
            return json.load(response)

    def login(self, username, password):
        result = self.request(
            process="login",
            login=username,
            password=password,
        )

        user = result.get("user", {})
        self.token = user.get("hash")

        if not self.token:
            raise RuntimeError("FastShare authentication failed")

        return {
            "authenticated": True,
            "unlimited": user.get("unlimited"),
            "credit": user.get("data", {}).get("value"),
        }

    def search(self, term, pagination=20):
        result = self.request(
            process="search",
            pagination=pagination,
            term=term,
            adult=0,
        )

        return result.get("search", {}).get("file", [])

    def probe_download(self, url):
        if not self.token:
            raise RuntimeError("Authentication required")

        parsed = urllib.parse.urlsplit(url)

        if (
            parsed.scheme != "https"
            or not re.fullmatch(
                r"(?:data[0-9]*|s[0-9]+)\.fastshare\.cloud",
                parsed.hostname or "",
            )
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.path != "/download.php"
        ):
            raise RuntimeError("Unexpected download URL")

        if any(c in self.token for c in ';\r\n \t,"\\'):
            raise RuntimeError("Unexpected token format")

        request = urllib.request.Request(
            url,
            headers={
                "Cookie": f"FASTSHARE={self.token}",
                "Range": "bytes=0-65535",
            },
        )

        with self.opener.open(request, timeout=30) as response:
            sample = response.read(65536)

            return {
                "status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length"),
                "content_range": response.headers.get("Content-Range"),
                "bytes_received": len(sample),
            }


if __name__ == "__main__":
    client = FastShareClient()

    try:
        username = input("FastShare username: ")
        password = getpass("FastShare password: ")

        print("\nAuthenticating...")
        account = client.login(username, password)
        del password

        print(json.dumps(account, indent=2))

        print("\nSearching for Big Buck Bunny...")
        results = client.search("Big Buck Bunny")

        for item in results:
            print(
                item.get("filename"),
                item.get("resolution"),
                item.get("data", {}).get("value"),
            )

        movie = next(
            (
                item for item in results
                if item.get("id") == "8066239"
            ),
            None,
        )

        if movie:
            print("\nTesting authenticated download...")
            result = client.probe_download(movie["download_url"])
            print(json.dumps(result, indent=2))

    except urllib.error.HTTPError as error:
        print(f"HTTP error: {error.code}")

    except Exception as error:
        print(f"Operation failed: {type(error).__name__}")