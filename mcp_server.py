import os
from typing import Any, Dict, List
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from fastmcp import FastMCP
import requests
from db_adapter import get_db

# ---------------------------------
# Setup & Database Initialization
# ---------------------------------
mcp = FastMCP("HR MCP Server")
db = get_db()
db.init_db()


# ---------------------------------
# TOOL 1: Get Weather
# ---------------------------------
@mcp.tool()
def get_weather(city: str) -> str:
    """Get current weather forecast for a given city."""
    try:
        weather_api_key = os.getenv("WEATHER_API_KEY")
        if weather_api_key:
            weather_api_url = os.getenv(
                "WEATHER_API_URL",
                "https://api.openweathermap.org/data/2.5/weather",
            )
            response = requests.get(
                weather_api_url,
                params={
                    "q": city,
                    "appid": weather_api_key,
                    "units": "metric",
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            main = payload.get("main", {})
            wind = payload.get("wind", {})
            description = payload.get("weather", [{}])[0].get("description")

            return (
                f"Weather in {city}:\n"
                f"Temperature: {main.get('temp')}°C\n"
                f"Feels Like: {main.get('feels_like')}°C\n"
                f"Condition: {description}\n"
                f"Humidity: {main.get('humidity')}%\n"
                f"Wind Speed: {wind.get('speed')} m/s"
            )

        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_response = requests.get(geo_url, timeout=10).json()

        if "results" not in geo_response:
            return f"Could not find location for {city}"

        lat = geo_response["results"][0]["latitude"]
        lon = geo_response["results"][0]["longitude"]

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true"
        )

        weather_response = requests.get(weather_url, timeout=10).json()
        current = weather_response.get("current_weather", {})

        return (
            f"Weather in {city}:\n"
            f"Temperature: {current.get('temperature')}°C\n"
            f"Wind Speed: {current.get('windspeed')} km/h"
        )

    except Exception as e:
        return f"Error fetching weather: {str(e)}"


# ---------------------------------
# TOOL 2: Get Employee Status
# ---------------------------------
@mcp.tool()
def get_employee_status(name: str) -> Dict[str, Any]:
    """Return employee availability status (e.g. Available, In Meeting, On Leave)."""
    result = db.get_employee_status(name)
    if result:
        return result
    return {"error": f"Employee '{name}' not found"}


# ---------------------------------
# TOOL 3: Get Policy
# ---------------------------------
@mcp.tool()
def get_policy(policy_name: str) -> Dict[str, Any]:
    """Return company policy details such as Leave Policy, WFH Policy, or Medical Policy."""
    result = db.get_policy(policy_name)
    if result:
        return result
    return {"error": f"Policy '{policy_name}' not found"}


# ---------------------------------
# TOOL 4: Get Leave Balance
# ---------------------------------
@mcp.tool()
def get_leave_balance(name: str) -> Dict[str, Any]:
    """Return remaining paid leave balance days for an employee."""
    result = db.get_leave_balance(name)
    if result:
        return result
    return {"error": f"Employee '{name}' not found"}


# ---------------------------------
# TOOL 5: Get Detailed Employee Leave Status
# ---------------------------------
@mcp.tool()
def get_employee_leave_status(name: str) -> Dict[str, Any]:
    """Return comprehensive employee profile including role, status, department, leave balance, and manager approver."""
    result = db.get_employee_leave_status(name)
    if result:
        return result
    return {"error": f"Employee '{name}' not found"}


# ---------------------------------
# TOOL 6: List All Employees
# ---------------------------------
@mcp.tool()
def list_employees() -> List[Dict[str, Any]]:
    """Return list of all registered employees with their role, department, status, and leave balance."""
    return db.list_employees()


# ---------------------------------
# TOOL 7: Get Approver
# ---------------------------------
@mcp.tool()
def get_approver(name: str) -> Dict[str, Any]:
    """Return the direct reporting manager / approver for an employee."""
    result = db.get_approver(name)
    if result:
        return result
    return {"error": f"Employee '{name}' not found"}


# ---------------------------------
# TOOL 8: Get Department Contact
# ---------------------------------
@mcp.tool()
def get_department_contact(department: str) -> Dict[str, Any]:
    """Return department contact lead and email address."""
    result = db.get_department_contact(department)
    if result:
        return result
    return {"error": f"Department '{department}' not found"}


# ---------------------------------
# TOOL 9: Scrape Webpage
# ---------------------------------
@mcp.tool()
def scrape_webpage(url: str) -> Dict[str, Any]:
    """Scrape a static webpage and return title, meta description, headings, and links."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        title = soup.title.get_text(strip=True) if soup.title else "No title found"
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = (
            meta_desc_tag["content"].strip()
            if meta_desc_tag and meta_desc_tag.get("content")
            else "No meta description"
        )

        headings = [tag.get_text(strip=True) for tag in soup.find_all(["h1", "h2", "h3"])]

        links = []
        seen = set()
        for link in soup.find_all("a", href=True):
            full_url = urljoin(url, link["href"])
            text = link.get_text(strip=True)
            if (text, full_url) not in seen:
                seen.add((text, full_url))
                links.append({"text": text, "url": full_url})

        return {
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "total_headings": len(headings),
            "total_links": len(links),
            "headings": headings[:20],
            "links": links[:30],
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------
# Run FastMCP Server
# ---------------------------------
if __name__ == "__main__":
    mcp.run(transport="http", port=int(os.getenv("MCP_PORT", "8080")))
