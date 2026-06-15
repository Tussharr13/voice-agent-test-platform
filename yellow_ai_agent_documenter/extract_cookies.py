import json
import os

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

def get_cookies():
    if browser_cookie3 is None:
        print("browser-cookie3 is not installed. Run: pip install browser-cookie3")
        return

    print("Extracting cookies from Chrome...")
    print("NOTE: You may see a macOS prompt asking for your keychain password to read Chrome's cookies. This is normal.")
    
    # Extract cookies for yellow.ai domain
    cj = browser_cookie3.chrome(domain_name='yellow.ai')
    
    cookies = []
    for cookie in cj:
        cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "secure": cookie.secure
        })
        
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "yellow_ai_cookies.json")

    with open(output_path, 'w') as f:
        json.dump(cookies, f, indent=2)
        
    print(f"Extracted {len(cookies)} cookies to {output_path}.")

if __name__ == "__main__":
    get_cookies()
