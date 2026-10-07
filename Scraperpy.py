import requests
from bs4 import BeautifulSoup

def get_offers():
    
    url = "https://member.wusa.ca/your_offers"
    
    response = requests.get(
        url, headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=10
    )
    
    response.raise_for_status()