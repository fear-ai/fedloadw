import json
import logging
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event

import requests
import schedule
from bs4 import BeautifulSoup
from config_log import setup_logging
from config_manager import ConfigManager
from hasher import hash_content

# Configuration
CONFIG_FILE = "config.json"

# Setup logging and config
config_manager = ConfigManager(CONFIG_FILE)
logger = setup_logging(config_manager=config_manager)

# Get configuration
config = config_manager.config

# Get monitoring configuration
monitoring_config = config.get("monitoring", {})
timeout_seconds = monitoring_config.get("timeout_seconds", 10)
user_agent = monitoring_config.get("user_agent", "FedLoad Monitor/1.0")

logger.info("Monitoring configuration: timeout_seconds=%s, user_agent=%s", timeout_seconds, user_agent)

# File paths
SITES_FILE = "tracked_sites.json"
LOG_FILE = "change_log.json"
ENTITY_STORE = "entity_store.json"
FED_ENTITIES_FILE = "fed_entities.json"
DAILY_REPORT = "daily_report.html"
WEEKLY_SUMMARY = "weekly_summary.html"

# Default values
DEFAULT_CHECK_FREQUENCY = config.get("monitoring", {}).get("check_frequency_minutes", 30)  # minutes

# Load configuration
try:
    logger.info("Loading configuration from %s...", CONFIG_FILE)
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    # Get check frequency from config
    check_frequency = config.get("scheduling", {}).get("check_frequency_minutes", DEFAULT_CHECK_FREQUENCY)
    logger.info("Check frequency set to %s minutes", check_frequency)

    # Get report generation settings
    daily_report_config = config.get("scheduling", {}).get("report_generation", {}).get("daily_report", {})
    daily_report_enabled = daily_report_config.get("enabled", True)
    daily_report_time = daily_report_config.get("time", "00:00")

    weekly_summary_config = config.get("scheduling", {}).get("report_generation", {}).get("weekly_summary", {})
    weekly_summary_enabled = weekly_summary_config.get("enabled", False)
    weekly_summary_day = weekly_summary_config.get("day", "Monday")
    weekly_summary_time = weekly_summary_config.get("time", "06:00")

    logger.info("Daily report generation: %s, time: %s",
                "enabled" if daily_report_enabled else "disabled",
                daily_report_time)
    logger.info("Weekly summary generation: %s, day: %s, time: %s",
                "enabled" if weekly_summary_enabled else "disabled",
                weekly_summary_day,
                weekly_summary_time)

except (requests.exceptions.RequestException, json.JSONDecodeError, IOError) as e:
    logger.error("Error loading configuration: %s", str(e))
    logger.warning("Using default values due to configuration error")
    check_frequency = DEFAULT_CHECK_FREQUENCY
    daily_report_enabled = True
    daily_report_time = "00:00"
    weekly_summary_enabled = False
    weekly_summary_day = "Monday"
    weekly_summary_time = "06:00"

# Initialize NLP pipeline
try:
    import spacy
    logger.info("Loading spaCy model 'en_core_web_sm'...")
    nlp = spacy.load("en_core_web_sm")
    logger.info("spaCy model loaded successfully")
    spacy_available = True
except Exception as e:
    logger.error("Could not load spaCy model: %s", str(e))
    logger.warning("Please run 'python -m spacy download en_core_web_sm' to enable full functionality")
    logger.warning("Continuing with limited functionality - entity recognition will be simplified")
    spacy_available = False

# Graceful exit flag
exit_event = Event()

# Load tracked sites
def load_sites():
    try:
        with open(SITES_FILE, 'r') as f:
            data = json.load(f)
            # The tracked_sites.json file has a "sites" array of URL strings
            sites = data.get("sites", [])
            logger.info("Loaded %s sites to monitor", len(sites))
            return sites
    except (IOError, json.JSONDecodeError) as e:
        logger.error("Error loading sites: %s", str(e))
        return []

# Load entity store or create if not exists
def load_entity_store():
    try:
        with open(ENTITY_STORE, 'r') as f:
            data = json.load(f)
            # Ensure the data has the required structure
            if "entities" not in data:
                data["entities"] = {}
            return data
    except (IOError, json.JSONDecodeError) as e:
        logger.info("Creating new entity store (no existing file or error: %s)", str(e))
        return {"entities": {}}

# Save entity store
def save_entity_store(entity_store):
    with open(ENTITY_STORE, 'w', encoding='utf-8', newline='') as f:
        json.dump(entity_store, f, indent=2)

# Load change log or create if not exists
def load_change_log():
    try:
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return []

# Load Fed entities
def load_fed_entities():
    try:
        with open(FED_ENTITIES_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.error("Error loading Fed entities: %s", str(e))
        return {"people": [], "organizations": [], "publications": [], "events": [], "topics": []}

# Signal handler for graceful exit
def signal_handler(sig, frame):
    logger.info("Received shutdown signal. Saving data and stopping scheduler...")
    exit_event.set()
    # Force exit after 10 seconds if graceful shutdown doesn't complete
    time.sleep(10)
    logger.info("Forcing exit...")
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Fetch content from a URL
def fetch_url(url):
    try:
        from fetcher import extract_main_content
        logger.info("Fetching content from %s", url)

        # Use the enhanced content extraction
        content_data = extract_main_content(url)
        if not content_data["text"]:
            logger.warning("No content extracted from %s - may indicate site issues", url)
            return None

        # Return the extracted text content
        return content_data["text"]
    except (requests.exceptions.RequestException, ImportError) as e:
        # Log error but don't exit program - continue with other sites
        logger.error("Error fetching %s: %s", url, str(e))

        # Fall back to basic fetching if the enhanced fetcher fails
        try:
            headers = {
                "User-Agent": config.get("monitoring", {}).get("user_agent", "FedLoad Monitor/1.0")
            }
            timeout = config.get("monitoring", {}).get("timeout_seconds", 30)  # Increased default timeout
            logger.info("Using fallback fetcher with timeout=%ss", timeout)
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract text content
            for script in soup(["script", "style"]):
                script.extract()

            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)

            return text
        except requests.exceptions.Timeout:
            timestamp = datetime.now().isoformat()
            error_msg = f"{timestamp} - ERROR - Error fetching HTTP URL {url}: Read timed out. (read timeout={timeout})"
            logger.error(error_msg)
            return None
        except requests.exceptions.RequestException as re:
            timestamp = datetime.now().isoformat()
            logger.error("Error with fallback fetching %s: %s", url, str(re))
            return None
        except Exception as e:
            timestamp = datetime.now().isoformat()
            logger.error("Unexpected error fetching %s: %s", url, str(e))
            return None

# Calculate hash of content
def calculate_content_hash(content):
    """Calculate hash of content using configured algorithm and optimizations."""
    try:
        # Load monitoring configuration
        monitoring_config = config.get("monitoring", {})
        algorithm = monitoring_config.get("content_hash_algorithm", "md5")
        initial_bytes = monitoring_config.get("hash_check_initial_bytes", 512)
        max_size_mb = monitoring_config.get("max_content_size_mb", 2)

        return hash_content(
            content,
            algorithm=algorithm,
            initial_bytes=initial_bytes,
            max_size_mb=max_size_mb
        )
    except Exception as e:
        logger.error("Error calculating content hash: %s", e)
        return None

# Simple entity extraction if spaCy is not available
def extract_entities_simple(text):
    """Simple entity extraction if spaCy is not available."""
    # A simple regex pattern to find title-cased words (names, organizations, etc.)
    pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
    entities = re.findall(pattern, text)
    return list(set(entities))  # Remove duplicates

# Check a site for changes
def check_site(url, entity_store):
    """Check a single site for changes and extract entities."""
    try:
        # Fetch content
        content = fetch_url(url)
        if not content:
            return False, None, None, [], []

        # Calculate hash
        new_hash = calculate_content_hash(content)

        # Check if content has changed
        old_hash = entity_store.get("entities", {}).get(url, {}).get("hash")
        if old_hash == new_hash:
            return False, old_hash, new_hash, [], []

        # Extract entities
        if spacy_available:
            doc = nlp(content)
            entities = [ent.text for ent in doc.ents]
        else:
            entities = extract_entities_simple(content)

        # Extract Fed-specific entities
        fed_entities = extract_fed_entities(content)

        # Update entity store
        if "entities" not in entity_store:
            entity_store["entities"] = {}
        entity_store["entities"][url] = {
            "hash": new_hash,
            "entities": entities,
            "fed_entities": fed_entities,
            "last_checked": datetime.now().isoformat()
        }

        return True, old_hash, new_hash, entities, fed_entities

    except (requests.exceptions.RequestException, json.JSONDecodeError, IOError) as e:
        logger.error("Error checking site %s: %s", url, str(e))
        return False, None, None, [], []

# Extract Fed-specific entities from text
def extract_fed_entities(text):
    """Extract Federal Reserve specific entities from text."""
    fed_entities = []
    try:
        fed_data = load_fed_entities()

        # Check for people
        for person in fed_data.get("people", []):
            if person["name"].lower() in text.lower():
                fed_entities.append({
                    "type": "person",
                    "name": person["name"],
                    "title": person.get("title"),
                    "organization": person.get("organization")
                })

        # Check for organizations
        for org in fed_data.get("organizations", []):
            if org["name"].lower() in text.lower():
                fed_entities.append({
                    "type": "organization",
                    "name": org["name"],
                    "acronym": org.get("acronym"),
                    "description": org.get("description")
                })

        # Check for publications
        for pub in fed_data.get("publications", []):
            if pub["name"].lower() in text.lower():
                fed_entities.append({
                    "type": "publication",
                    "name": pub["name"],
                    "publishing_body": pub.get("publishing_body"),
                    "frequency": pub.get("frequency")
                })

    except (IOError, json.JSONDecodeError) as e:
        logger.error("Error extracting Fed entities: %s", str(e))

    return fed_entities

# Check all sites
def check_all_sites():
    logger.info("Starting site checks...")
    sites = load_sites()
    entity_store = load_entity_store()
    log_data = load_change_log()

    # Ensure entity_store has the proper structure
    if "entities" not in entity_store:
        entity_store["entities"] = {}

    changes_detected = 0
    sites_checked = 0
    sites_errored = 0

    for url in sites:
        if not url:
            continue

        try:
            sites_checked += 1
            logger.info(f"Checking {url}")
            changed, old_hash, new_hash, matched_entities, fed_entities_found = check_site(url, entity_store)

            if changed:
                changes_detected += 1
                logger.info(f"Changes detected on {url}")
                logger.info(f"Found {len(matched_entities)} basic entities and {len(fed_entities_found)} Fed-specific entities")

                # Log the change
                log_entry = {
                    "url": url,
                    "time": datetime.now().isoformat(),
                    "changed": True,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                    "entities_found": {
                        "basic": matched_entities,
                        "fed_people": [e["text"] for e in fed_entities_found if e["type"] == "person"],
                        "fed_organizations": [e["text"] for e in fed_entities_found if e["type"] == "organization"],
                        "fed_publications": [e["text"] for e in fed_entities_found if e["type"] == "publication"]
                    }
                }
                log_data.append(log_entry)
        except Exception as e:
            sites_errored += 1
            logger.error(f"Error checking {url}: {str(e)}")
            # Log the error
            log_entry = {
                "url": url,
                "time": datetime.now().isoformat(),
                "changed": False,
                "error": str(e)
            }
            log_data.append(log_entry)
            continue

    # Save entity store
    save_entity_store(entity_store)

    # Save log
    with open(LOG_FILE, 'w', encoding='utf-8', newline='') as f:
        json.dump(log_data, f, indent=2)

    logger.info("Site check summary:")
    logger.info(f"- Total sites checked: {sites_checked}")
    logger.info(f"- Sites with changes: {changes_detected}")
    logger.info(f"- Sites with errors: {sites_errored}")
    logger.info("Completed site checks.")
    return changes_detected

# Generate daily report
def generate_daily_report():
    logger.info("Generating daily report...")
    log_data = load_change_log()
    entity_store = load_entity_store()

    # Ensure entity_store has the proper structure
    if "entities" not in entity_store:
        entity_store["entities"] = {}

    # Filter logs for the last 24 hours
    now = datetime.now()
    recent_logs = [log for log in log_data if (now - datetime.fromisoformat(log["time"].replace("Z", ""))).days < 1]

    # Count mentions of Fed entities
    people_mentions = {}
    org_mentions = {}
    pub_mentions = {}

    for log in recent_logs:
        for person in log["entities_found"].get("fed_people", []):
            people_mentions[person] = people_mentions.get(person, 0) + 1

        for org in log["entities_found"].get("fed_organizations", []):
            org_mentions[org] = org_mentions.get(org, 0) + 1

        for pub in log["entities_found"].get("fed_publications", []):
            pub_mentions[pub] = pub_mentions.get(pub, 0) + 1

    # Sort by frequency
    people_sorted = sorted(people_mentions.items(), key=lambda x: x[1], reverse=True)
    pub_sorted = sorted(pub_mentions.items(), key=lambda x: x[1], reverse=True)

    # Generate HTML report with LF line endings
    template = """<!DOCTYPE html>
<html>
<head>
    <title>FED Website Changes Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; color: #333; }
        h1, h2, h3 { color: #00395b; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; }
        th { background-color: #f4f4f4; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .change-type { font-weight: bold; }
        .entity-list { margin-left: 20px; }
        .entity-item { margin-bottom: 5px; }
        .entity-count { color: #666; font-size: 0.9em; }
        .timestamp { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>FED Website Changes Report</h1>
    <p class="timestamp">Generated: <!-- GENERATION_TIME --></p>

    <h2>Changes Detected</h2>
    <table>
        <thead>
            <tr>
                <th>URL</th>
                <th>Change Type</th>
                <th>Entities Found</th>
                <th>Timestamp</th>
            </tr>
        </thead>
        <tbody>
            <!-- CHANGES_TABLE -->
        </tbody>
    </table>

    <h2>Fed-Specific Entities</h2>
    <div class="entity-list">
        <h3>People</h3>
        <!-- PEOPLE_LIST -->
        <h3>Organizations</h3>
        <!-- ORG_LIST -->
        <h3>Publications</h3>
        <!-- PUB_LIST -->
    </div>
</body>
</html>"""

    # Replace placeholders with data
    changes_html = ""
    if recent_logs:
        changes_html = "<ul>"
        for log in recent_logs:
            changes_html += f"<li><a href='{log['url']}'>{log['url']}</a> - {datetime.fromisoformat(log['time'].replace('Z', '')).strftime('%Y-%m-%d %H:%M:%S')}</li>"
        changes_html += "</ul>"
    else:
        changes_html = "<p>No changes detected in the last 24 hours.</p>"

    people_html = ""
    if people_sorted:
        people_html = "<ul>"
        for person, count in people_sorted[:10]:  # Top 10
            people_html += f"<li>{person} - {count} mentions</li>"
        people_html += "</ul>"
    else:
        people_html = "<p>No FED officials mentioned in the last 24 hours.</p>"

    pub_html = ""
    if pub_sorted:
        pub_html = "<ul>"
        for pub, count in pub_sorted[:10]:  # Top 10
            pub_html += f"<li>{pub} - {count} mentions</li>"
        pub_html += "</ul>"
    else:
        pub_html = "<p>No FED publications mentioned in the last 24 hours.</p>"

    # Update the template with actual data
    template = template.replace("<!-- CHANGES_CONTENT -->", changes_html)
    template = template.replace("<!-- OFFICIALS_CONTENT -->", people_html)
    template = template.replace("<!-- PUBLICATIONS_CONTENT -->", pub_html)
    template = template.replace("<!-- GENERATION_TIME -->", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Write the report
    with open(DAILY_REPORT, 'w', encoding='utf-8', newline='') as f:
        f.write(template)

    logger.info("Daily report generated successfully.")

# Generate weekly summary
def generate_weekly_summary():
    if not weekly_summary_enabled:
        return

    logger.info("Generating weekly summary...")
    log_data = load_change_log()
    entity_store = load_entity_store()

    # Ensure entity_store has the proper structure
    if "entities" not in entity_store:
        entity_store["entities"] = {}

    # Filter logs for the last 7 days
    now = datetime.now()
    recent_logs = [log for log in log_data if (now - datetime.fromisoformat(log["time"].replace("Z", ""))).days < 7]

    # Count stats
    total_changes = len(recent_logs)
    sites_with_changes = set([log["url"] for log in recent_logs])
    total_sites_changed = len(sites_with_changes)

    # Count mentions of Fed entities
    people_mentions = {}
    pub_mentions = {}
    site_activity = {}

    for log in recent_logs:
        site_url = log["url"]
        site_activity[site_url] = site_activity.get(site_url, 0) + 1

        for person in log["entities_found"].get("fed_people", []):
            people_mentions[person] = people_mentions.get(person, 0) + 1

        for pub in log["entities_found"].get("fed_publications", []):
            pub_mentions[pub] = pub_mentions.get(pub, 0) + 1

    # Sort by frequency
    people_sorted = sorted(people_mentions.items(), key=lambda x: x[1], reverse=True)
    pub_sorted = sorted(pub_mentions.items(), key=lambda x: x[1], reverse=True)
    sites_sorted = sorted(site_activity.items(), key=lambda x: x[1], reverse=True)

    # Generate HTML report
    try:
        with open(WEEKLY_SUMMARY, 'r') as f:
            template = f.read()
    except Exception as e:
        logger.error("Error generating weekly summary: %s", str(e))
        return

    # Create overview section
    overview_html = f"""
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">{total_changes}</div>
            <div class="stat-label">Total Changes</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{total_sites_changed}</div>
            <div class="stat-label">Active Sites</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(people_mentions)}</div>
            <div class="stat-label">Officials Mentioned</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(pub_mentions)}</div>
            <div class="stat-label">Publications Referenced</div>
        </div>
    </div>
    """

    # Create active sites section
    sites_html = ""
    if sites_sorted:
        sites_html = "<ol>"
        for site, count in sites_sorted[:5]:  # Top 5
            sites_html += f"<li><a href='{site}'>{site}</a> - {count} changes</li>"
        sites_html += "</ol>"
    else:
        sites_html = "<p>No site activity this week.</p>"

    # Create officials section
    officials_html = ""
    if people_sorted:
        officials_html = "<ol>"
        for person, count in people_sorted[:5]:  # Top 5
            officials_html += f"<li>{person} - {count} mentions</li>"
        officials_html += "</ol>"
    else:
        officials_html = "<p>No FED officials mentioned this week.</p>"

    # Create publications section
    pubs_html = ""
    if pub_sorted:
        pubs_html = "<ol>"
        for pub, count in pub_sorted[:5]:  # Top 5
            pubs_html += f"<li>{pub} - {count} mentions</li>"
        pubs_html += "</ol>"
    else:
        pubs_html = "<p>No FED publications mentioned this week.</p>"

    # Update the template with actual data
    template = template.replace("<!-- OVERVIEW_CONTENT -->", overview_html)
    template = template.replace("<!-- ACTIVE_SITES_CONTENT -->", sites_html)
    template = template.replace("<!-- OFFICIALS_CONTENT -->", officials_html)
    template = template.replace("<!-- PUBLICATIONS_CONTENT -->", pubs_html)
    template = template.replace("<!-- GENERATION_TIME -->", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Write the report
    with open(WEEKLY_SUMMARY, 'w', encoding='utf-8', newline='') as f:
        f.write(template)

    logger.info("Weekly summary generated successfully.")

# Main function
def main():
    """Main function to run the scheduler."""
    try:
        # Schedule site checks
        schedule.every(check_frequency).minutes.do(check_all_sites)

        # Schedule reports if enabled
        if daily_report_enabled:
            schedule.every().day.at(daily_report_time).do(generate_daily_report)
        if weekly_summary_enabled:
            schedule.every().monday.at(weekly_summary_time).do(generate_weekly_summary)

        # Run initial check
        check_all_sites()

        # Main loop
        while not exit_event.is_set():
            schedule.run_pending()
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error("Error in main loop: %s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
