from pathlib import Path

import bs4
import requests

_URL = "https://www.oclc.org/en/worldcat/library100/top500.html"


if __name__ == "__main__":
    raw_list = ""
    # Get the content of the page
    html = requests.get(_URL).text
    soup = bs4.BeautifulSoup(html, "html.parser")
    # Find the body of the table with id lib500list
    table = soup.find("table", {"id": "lib500list"})
    if table is None:
        raise ValueError("Could not find table with id 'lib500list'")
    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("Could not find tbody in table with id 'lib500list'")
    # For each row, get the elements with class ti (title) and au (author)
    # and add an entry to raw_list
    for row in tbody.find_all("tr"):
        title = row.find("td", {"class": "ti"})
        author = row.find("td", {"class": "au"})
        if title is not None and author is not None:
            raw_list += f"{title.text.strip()} - {author.text.strip()}\n"
    # Save path (relative to this file)
    target_path = Path(__file__).parents[1] / "genlists/novels500.txt"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _ = target_path.write_text(raw_list)
