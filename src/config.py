"""
Central configuration — loads environment variables and defines constants.
All other modules import from here instead of reading .env directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Serper.dev Google Jobs Search Queries ---
# 30 structured queries covering all O&G role categories in Nigeria.
# Each is passed verbatim to the Serper.dev /jobs endpoint.
SEARCH_QUERIES = [
    # Supply chain and procurement
    "supply chain procurement oil and gas Nigeria",
    "logistics materials management upstream Nigeria",
    "vendor management contracts oil and gas Nigeria",
    # Engineering and technical
    "drilling reservoir production engineer Nigeria",
    "facilities subsurface engineer upstream Nigeria",
    "geoscience geophysics petroleum engineer Nigeria",
    "instrumentation automation control oil and gas Nigeria",
    # Finance and commercial
    "oil and gas finance commercial analyst Nigeria",
    "petroleum economics project finance upstream Nigeria",
    "trading commodity analyst energy Nigeria",
    # Project management and contracts
    "project manager engineer oil and gas Nigeria",
    "contracts administrator legal counsel upstream Nigeria",
    # HSE and sustainability
    "HSE QHSE safety officer oil and gas Nigeria",
    "community relations sustainability environment oil and gas Nigeria",
    # HR and people
    "HR human resources talent management oil and gas Nigeria",
    "learning development organisational development upstream Nigeria",
    # IT and digital
    "IT digital SAP data analytics oil and gas Nigeria",
    "technology systems engineer upstream Nigeria",
    # Marine and offshore
    "marine offshore operations engineer Nigeria",
    # Graduate and early career
    "oil and gas graduate trainee programme Nigeria",
    "upstream internship entry level petroleum Nigeria",
    "graduate engineer analyst oil and gas Nigeria",
    # IOCs and major operators
    "NNPC TotalEnergies Shell Chevron ExxonMobil Dangote Nigeria careers",
    "Seplat Oando Sahara Heirs Energies Aradel Nigeria jobs",
    # Indigenous operators
    "Eroton Neconde Aiteo Renaissance Midwestern Nigeria oil gas jobs",
    "NPDC Belemaoil Platform Petroleum Famfa Pan Ocean Nigeria careers",
    # Service companies
    "SLB Halliburton Baker Hughes Saipem Weatherford Nigeria jobs",
    "Bell Oil Gas Dakotelin Sinopec NAOC NLNG Nigeria careers",
    # Location specific
    "oil and gas jobs Port Harcourt Rivers State Nigeria",
    "oil and gas jobs Lagos Victoria Island Nigeria",
]

# --- Scraper Settings ---
REQUEST_DELAY_SECONDS = 2       # Delay between Serper queries (rate-limit respect)
MAX_PAGES_PER_QUERY = 3         # Pagination depth per query
LOG_DIR = "logs"                # Directory for daily scrape logs
